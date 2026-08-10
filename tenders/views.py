from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Case, CharField, Count, F, Q, Sum, Value, When
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST

from .models import LPSEWatchlist, Tender, TenderBookmark
from .services import lpse_analytics
from .services.matching import calculate_tender_match
from .services.notifications import get_notifications, get_unread_count, mark_all_read, mark_notification_read
from .year_utils import extract_budget_years


PROCUREMENT_TYPE_OPTIONS = [
    "Pekerjaan Konstruksi",
    "Pengadaan Barang",
    "Jasa Konsultansi",
    "Jasa Lainnya",
]
SPSE_SOURCE_VALUES = [Tender.SOURCE_SPSE, Tender.SOURCE_MIXED]
ACTIVE_STATUSES = ["OPEN", "ONGOING"]
FINISHED_STATUSES = ["FINISH"]
SOURCE_FILTER_OPTIONS = {
    "operational": "SPSE + Mixed",
    "all": "Semua",
    Tender.SOURCE_SPSE: "SPSE",
    Tender.SOURCE_REALISASI: "Realisasi",
    Tender.SOURCE_MIXED: "Mixed",
    Tender.SOURCE_LKPP_API: "LKPP API",
}

SORT_OPTIONS = {
    "created_desc": "Terbaru",
    "created_asc": "Terlama",
    "match_desc": "AI Match Tertinggi",
    "match_asc": "AI Match Terendah",
    "hps_desc": "Nilai HPS Tertinggi",
    "hps_asc": "Nilai HPS Terendah",
    "participants_desc": "Peserta Terbanyak",
    "participants_asc": "Peserta Tersedikit",
}

LPSE_TENDER_SORT_OPTIONS = {
    "created_desc": "Terbaru",
    "hps_desc": "HPS tertinggi",
    "hps_asc": "HPS terendah",
    "match_desc": "AI Match tertinggi",
    "name_asc": "Nama Paket A-Z",
}


def get_spse_operational_filter():
    spse_signal = (
        Q(lpse_slug__gt="")
        | Q(lpse_detail_url__contains="spse.inaproc.id")
        | Q(detail_url__contains="spse.inaproc.id")
    )
    return Q(data_source__in=SPSE_SOURCE_VALUES) | spse_signal


def get_operational_queryset():
    return Tender.objects.filter(get_spse_operational_filter())


def apply_source_filter(queryset, source):
    if source == "all":
        return Tender.objects.all()
    if source == Tender.SOURCE_SPSE:
        return queryset.filter(data_source=Tender.SOURCE_SPSE)
    if source == Tender.SOURCE_REALISASI:
        return Tender.objects.filter(data_source=Tender.SOURCE_REALISASI)
    if source == Tender.SOURCE_MIXED:
        return queryset.filter(data_source=Tender.SOURCE_MIXED)
    if source == Tender.SOURCE_LKPP_API:
        return Tender.objects.filter(data_source=Tender.SOURCE_LKPP_API)
    return queryset.filter(get_spse_operational_filter())

ALLOWED_PER_PAGE = [15, 25, 50, 100]
DEFAULT_PER_PAGE = 25
LPSE_WATCHLIST_LIMIT = 5


LOGIN_REQUIRED_MATCH = {
    "score": None,
    "level": "Low",
    "label": "Masuk untuk melihat AI Match",
    "reasons": [],
    "missing": [
        "Masuk untuk melihat AI Match.",
    ],
    "requires_login": True,
    "requires_profile": False,
}


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    tenders = Tender.objects.order_by("-created_at", "-id")[:6]
    attach_match_data(request, tenders)
    return render(request, "index.html", {"tenders": tenders})


def get_vendor_profile(user):
    if not user.is_authenticated:
        return None

    try:
        return user.vendor_profile
    except ObjectDoesNotExist:
        return None


def get_match_data(request, tender):
    if not request.user.is_authenticated:
        return LOGIN_REQUIRED_MATCH.copy()

    return calculate_tender_match(tender, get_vendor_profile(request.user))


def attach_match_data(request, tenders):
    vendor_profile = get_vendor_profile(request.user)

    for tender in tenders:
        if request.user.is_authenticated:
            tender.match_data = calculate_tender_match(tender, vendor_profile)
        else:
            tender.match_data = LOGIN_REQUIRED_MATCH.copy()

    return tenders


def get_filter_options():
    base_queryset = get_operational_queryset()
    klpd_values = set(
        base_queryset.exclude(klpd_instansi="")
        .values_list("klpd_instansi", flat=True)
        .distinct()
    )
    klpd_values.update(
        base_queryset.filter(klpd_instansi="")
        .exclude(instansi="")
        .values_list("instansi", flat=True)
        .distinct()
    )
    lpse_values = (
        base_queryset.exclude(lpse_name="")
        .values_list("lpse_name", flat=True)
        .distinct()
    )

    # dropdown options driven by actual data, not hardcoded lists
    status_values = set(
        base_queryset.exclude(status="").values_list("status", flat=True).distinct()
    )
    jenis_values = set(
        base_queryset.exclude(jenis_pengadaan="")
        .values_list("jenis_pengadaan", flat=True)
        .distinct()
    )
    # keep familiar order first, append any extras found in data
    ordered_jenis = [
        value for value in PROCUREMENT_TYPE_OPTIONS if value in jenis_values
    ] + sorted(jenis_values - set(PROCUREMENT_TYPE_OPTIONS))
    ordered_status = [
        value
        for value in ("OPEN", "ONGOING", "FINISH", "FAILED", "SELESAI")
        if value in status_values
    ] + sorted(status_values - {"OPEN", "ONGOING", "FINISH", "FAILED", "SELESAI"})

    return {
        "jenis_pengadaan": ordered_jenis,
        "status": ordered_status,
        "klpd_instansi": sorted(value for value in klpd_values if value),
        "lpse": sorted(value for value in lpse_values if value),
        "tahun": get_year_options(base_queryset),
        "sort": SORT_OPTIONS,
    }


def get_year_options(queryset=None):
    queryset = queryset if queryset is not None else Tender.objects.all()
    values = (
        queryset.exclude(tahun_anggaran__isnull=True)
        .exclude(tahun_anggaran="")
        .values_list("tahun_anggaran", flat=True)
        .distinct()
    )
    years = {
        year
        for value in values
        for year in extract_budget_years(value)
    }
    years.add(str(timezone.localdate().year))
    return sorted(years, reverse=True)


def get_selected_year_filter(request):
    selected_year = request.GET.get("tahun")
    if selected_year is None:
        selected_year = request.GET.get("tahun_anggaran", str(timezone.localdate().year))
    return selected_year.strip() or str(timezone.localdate().year)


def get_lpse_tender_filter_options(queryset):
    jenis_values = (
        queryset.exclude(jenis_pengadaan="")
        .values_list("jenis_pengadaan", flat=True)
        .distinct()
    )
    return {
        "jenis_pengadaan": sorted(value for value in jenis_values if value),
        "tahun": get_year_options(queryset),
        "sort": LPSE_TENDER_SORT_OPTIONS,
    }


def get_multi_param(request, key):
    return [v.strip() for v in request.GET.getlist(key) if v.strip()]

def get_selected_filters(request, sort_options=None):
    sort_options = sort_options or SORT_OPTIONS
    sort = request.GET.get("sort") or "created_desc"
    if sort not in sort_options:
        sort = "created_desc"

    return {
        "q": request.GET.get("q", request.GET.get("tender", "")).strip(),
        "status": request.GET.get("status", "").strip(),
        "jenis_pengadaan": request.GET.get("jenis_pengadaan", "").strip(),
        "klpd_instansi": get_multi_param(request, "klpd_instansi"),
        "lpse": get_multi_param(request, "lpse"),
        "source": "operational",
        "tahun": get_selected_year_filter(request),
        "sort": sort,
    }


def get_per_page(request):
    try:
        per_page = int(request.GET.get("per_page", DEFAULT_PER_PAGE))
    except (TypeError, ValueError):
        return DEFAULT_PER_PAGE
    return per_page if per_page in ALLOWED_PER_PAGE else DEFAULT_PER_PAGE


def get_page_number(request):
    try:
        page = int(request.GET.get("page", 1))
    except (TypeError, ValueError):
        return 1
    return max(page, 1)


def get_pagination_query(request, per_page):
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("source", None)
    params["per_page"] = str(per_page)
    return params.urlencode()


def get_filtered_queryset(request, base_queryset=None, sort_options=None):
    selected = get_selected_filters(request, sort_options)
    tenders = base_queryset if base_queryset is not None else get_operational_queryset()
    if base_queryset is None:
        tenders = apply_source_filter(tenders, selected["source"])

    if selected["q"]:
        tenders = tenders.filter(
            Q(nama_paket__icontains=selected["q"])
            | Q(kode_tender__icontains=selected["q"])
            | Q(instansi__icontains=selected["q"])
            | Q(klpd_instansi__icontains=selected["q"])
            | Q(satuankerja__icontains=selected["q"])
            | Q(lpse_name__icontains=selected["q"])
        )

    if selected["status"]:
        tenders = tenders.filter(status=selected["status"])

    if selected["jenis_pengadaan"]:
        tenders = tenders.filter(jenis_pengadaan=selected["jenis_pengadaan"])

    if selected["klpd_instansi"]:
        q_instansi = Q()
        for value in selected["klpd_instansi"]:
            q_instansi |= Q(klpd_instansi=value) | (Q(klpd_instansi="") & Q(instansi=value))
        tenders = tenders.filter(q_instansi)

    if selected["lpse"]:
        q_lpse = Q()
        for value in selected["lpse"]:
            q_lpse |= Q(lpse_name=value) | Q(lpse_slug=value)
        tenders = tenders.filter(q_lpse)

    if selected["tahun"]:
        tenders = tenders.filter(tahun_anggaran__contains=selected["tahun"])

    return tenders, selected


def apply_db_sort(tenders, sort):
    if sort == "created_asc":
        return tenders.order_by(F("tanggal_pembuatan").asc(nulls_last=True), "id")
    if sort == "hps_desc":
        return tenders.order_by(F("nilai_hps").desc(nulls_last=True), "-id")
    if sort == "hps_asc":
        return tenders.order_by(F("nilai_hps").asc(nulls_last=True), "id")
    if sort == "participants_desc":
        return tenders.order_by(F("peserta_count").desc(nulls_last=True), "-id")
    if sort == "participants_asc":
        return tenders.order_by(F("peserta_count").asc(nulls_last=True), "id")
    if sort == "name_asc":
        return tenders.order_by("nama_paket", "id")
    return tenders.order_by(F("tanggal_pembuatan").desc(nulls_last=True), "-id")


def get_paginated_tenders(request, base_queryset=None, sort_options=None, tender_list_url="/tenders/", tender_list_target="#tender-list"):
    tenders, selected = get_filtered_queryset(request, base_queryset, sort_options)
    per_page = get_per_page(request)
    page = get_page_number(request)
    sort = selected["sort"]

    if sort in ("match_desc", "match_asc"):
        tenders = list(apply_db_sort(tenders, "created_desc"))
        attach_match_data(request, tenders)
        tenders.sort(
            key=lambda tender: tender.match_data.get("score") or 0,
            reverse=(sort == "match_desc"),
        )
        paginator = Paginator(tenders, per_page)
        page_obj = paginator.get_page(page)
        page_tenders = list(page_obj.object_list)
    else:
        tenders = apply_db_sort(tenders, sort)
        paginator = Paginator(tenders, per_page)
        page_obj = paginator.get_page(page)
        page_tenders = list(page_obj.object_list)
        attach_match_data(request, page_tenders)

    return {
        "tenders": page_tenders,
        "selected_filters": selected,
        "page_obj": page_obj,
        "paginator": paginator,
        "per_page": per_page,
        "allowed_per_page": ALLOWED_PER_PAGE,
        "pagination_query": get_pagination_query(request, per_page),
        "total_count": paginator.count,
        "tender_list_url": tender_list_url,
        "tender_list_target": tender_list_target,
    }


def get_lpse_label_expression():
    return Case(
        When(lpse_name__gt="", then=F("lpse_name")),
        When(lpse_slug__gt="", then=F("lpse_slug")),
        default=Value("LPSE Tidak Diketahui"),
        output_field=CharField(),
    )


def build_dashboard_overview(request):
    base_queryset = get_operational_queryset()
    selected_tahun = get_selected_year_filter(request)
    tahun_options = get_year_options(base_queryset)
    if selected_tahun:
        base_queryset = base_queryset.filter(tahun_anggaran__contains=selected_tahun)

    total_tender = base_queryset.count()
    total_hps = base_queryset.aggregate(total=Sum("nilai_hps"))["total"] or 0
    tender_aktif = base_queryset.filter(status__in=ACTIVE_STATUSES).count()
    total_lpse = (
        base_queryset.annotate(lpse_label=get_lpse_label_expression())
        .values("lpse_label")
        .distinct()
        .count()
    )

    top_10_lpse = list(
        base_queryset.annotate(lpse_label=get_lpse_label_expression())
        .values("lpse_label")
        .annotate(package_count=Count("id"), total_hps=Sum("nilai_hps"))
        .order_by("-package_count", "lpse_label")[:10]
    )
    max_lpse_count = max((item["package_count"] for item in top_10_lpse), default=0)
    for index, item in enumerate(top_10_lpse, start=1):
        item["rank"] = index
        item["progress"] = round((item["package_count"] / max_lpse_count) * 100) if max_lpse_count else 0

    latest_tenders = list(
        base_queryset.order_by(F("tanggal_pembuatan").desc(nulls_last=True), "-id")[:15]
    )
    attach_match_data(request, latest_tenders)

    procurement_definitions = [
        ("Pekerjaan Konstruksi", Q(jenis_pengadaan__icontains="Konstruksi")),
        ("Barang", Q(jenis_pengadaan__icontains="Barang")),
        ("Jasa Konsultansi", Q(jenis_pengadaan__icontains="Konsultansi")),
        ("Jasa Lainnya", Q(jenis_pengadaan__icontains="Jasa Lainnya")),
    ]
    procurement_type_stats = []
    for label, query in procurement_definitions:
        count = base_queryset.filter(query).count()
        procurement_type_stats.append({
            "label": label,
            "count": count,
            "percentage": round((count / total_tender) * 100, 1) if total_tender else 0,
        })

    top_lpse = top_10_lpse[0] if top_10_lpse else None
    top_procurement = max(procurement_type_stats, key=lambda item: item["count"], default=None)
    highest_hps_lpse = max(top_10_lpse, key=lambda item: item["total_hps"] or 0, default=None)
    latest_tender = latest_tenders[0] if latest_tenders else None

    return {
        "dashboard_stats": {
            "total_tender": total_tender,
            "total_hps": total_hps,
            "total_lpse": total_lpse,
            "tender_aktif": tender_aktif,
        },
        "top_10_lpse": top_10_lpse,
        "latest_tenders": latest_tenders,
        "procurement_type_stats": procurement_type_stats,
        "quick_insights": {
            "top_lpse": top_lpse,
            "top_procurement": top_procurement,
            "highest_hps_lpse": highest_hps_lpse,
            "latest_tender": latest_tender,
        },
        "tahun_options": tahun_options,
        "selected_tahun": selected_tahun,
    }


def dashboard(request):
    if request.user.is_authenticated and not request.user.is_active:
        return render(request, "dashboard/index.html", {
            "pending_approval": True,
        })

    context = {
        **build_dashboard_overview(request),
    }
    return render(request, "dashboard/index.html", context)


def settings_redirect(request):
    return redirect("vendor_profile")


def get_safe_redirect_url(request, candidate, fallback):
    if candidate and url_has_allowed_host_and_scheme(
        url=candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return fallback


def render_notification_widget(request):
    return render(request, "partials/notification_bell.html", {
        "tender_notifications": get_notifications(request.user),
        "tender_notifications_count": get_unread_count(request.user, generate=False),
    })


@login_required
@require_POST
def mark_tender_notification_read(request, notification_id):
    mark_notification_read(notification_id, request.user)
    if request.headers.get("HX-Request"):
        return render_notification_widget(request)
    return redirect(get_safe_redirect_url(request, request.META.get("HTTP_REFERER"), reverse("dashboard")))


@login_required
@require_POST
def mark_all_tender_notifications_read(request):
    mark_all_read(request.user)
    if request.headers.get("HX-Request"):
        return render_notification_widget(request)
    return redirect(get_safe_redirect_url(request, request.META.get("HTTP_REFERER"), reverse("dashboard")))


@login_required
@require_POST
def open_tender_notification(request, notification_id):
    notification = mark_notification_read(notification_id, request.user)
    if not notification:
        raise Http404("Notifikasi tidak ditemukan")
    return redirect(f"{reverse('tender_list')}?{urlencode({'tender': notification.tender.kode_tender})}")


def tender_list(request):
    tender_context = get_paginated_tenders(request)
    tenders = tender_context["tenders"]

    saved_ids = []
    if request.user.is_authenticated:
        saved_ids = list(TenderBookmark.objects.filter(
            user=request.user,
            tender__in=tenders,
        ).values_list("tender_id", flat=True))

    context = {
        "tenders": tenders,
        "saved_ids": saved_ids,
        "filter_options": get_filter_options(),
        "selected_filters": tender_context["selected_filters"],
        "explorer_meta": True,
        **{key: value for key, value in tender_context.items() if key not in {"tenders", "selected_filters"}},
    }

    if request.headers.get("HX-Request"):
        return render(request, "dashboard/tender_list.html", context)

    context["tender_list_url"] = reverse("tender_list")
    return render(request, "dashboard/tender_explorer.html", context)


def tender_detail(request, pk):
    tender = get_object_or_404(Tender, id=pk)
    tender.match_data = get_match_data(request, tender)
    return render(request, "dashboard/tender_detail.html", {"t": tender})


def get_per_page_from_params(params):
    try:
        per_page = int(params.get("per_page", DEFAULT_PER_PAGE))
    except (TypeError, ValueError):
        return DEFAULT_PER_PAGE
    return per_page if per_page in ALLOWED_PER_PAGE else DEFAULT_PER_PAGE


def get_page_number_from_params(params):
    try:
        page = int(params.get("page", 1))
    except (TypeError, ValueError):
        return 1
    return max(page, 1)


def get_lpse_request_params(request):
    return request.POST if request.method == "POST" else request.GET


def get_watchlisted_slugs(user):
    if not user.is_authenticated:
        return set()

    return set(
        LPSEWatchlist.objects.filter(user=user)
        .values_list("lpse_slug", flat=True)
    )


def build_lpse_list_context(request, params=None):
    params = params or get_lpse_request_params(request)
    entries = build_lpse_entries()
    query_value = params.get("q", "")
    query = query_value.strip().casefold()
    sort = params.get("sort") or "total_desc"
    per_page = get_per_page_from_params(params)
    page = get_page_number_from_params(params)

    if query:
        entries = [
            entry for entry in entries
            if query in entry["lpse_name"].casefold() or query in entry["slug"].casefold()
        ]

    if sort == "hps_desc":
        entries.sort(key=lambda entry: entry["total_hps"] or 0, reverse=True)
    elif sort == "open_desc":
        entries.sort(key=lambda entry: entry["paket_open"] or 0, reverse=True)
    elif sort == "name_asc":
        entries.sort(key=lambda entry: entry["lpse_name"].casefold())
    else:
        sort = "total_desc"
        entries.sort(key=lambda entry: entry["total_paket"] or 0, reverse=True)

    paginator = Paginator(entries, per_page)
    page_obj = paginator.get_page(page)
    pagination_params = {
        key: params.get(key)
        for key in ("q", "sort")
        if params.get(key)
    }
    pagination_params["per_page"] = str(per_page)

    watchlisted_slugs = get_watchlisted_slugs(request.user)
    for entry in page_obj.object_list:
        entry["is_watchlisted"] = entry["slug"] in watchlisted_slugs

    return {
        "lpse_entries": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "per_page": per_page,
        "allowed_per_page": ALLOWED_PER_PAGE,
        "pagination_query": urlencode(pagination_params),
        "total_count": paginator.count,
        "selected": {"q": query_value, "sort": sort},
        "sort_options": {
            "total_desc": "Total Paket terbanyak",
            "hps_desc": "Total HPS tertinggi",
            "open_desc": "Paket OPEN terbanyak",
            "name_asc": "Nama LPSE A-Z",
        },
        "watchlisted_slugs": watchlisted_slugs,
        "watchlist_count": len(watchlisted_slugs),
        "watchlist_limit": LPSE_WATCHLIST_LIMIT,
        "watchlist_limit_reached": len(watchlisted_slugs) >= LPSE_WATCHLIST_LIMIT,
    }


def lpse_list_view(request):
    context = build_lpse_list_context(request)
    template = "lpse/list_partial.html" if request.headers.get("HX-Request") else "lpse/list.html"
    return render(request, template, context)


def get_lpse_entry_or_404(slug):
    for entry in build_lpse_entries():
        if entry["slug"] == slug:
            return entry

    raise Http404("LPSE tidak ditemukan")


def build_lpse_watchlist_context(request):
    watchlists = list(
        LPSEWatchlist.objects.filter(user=request.user)
        .only("lpse_slug", "lpse_name", "created_at")
        .order_by("-created_at")
    )
    entries_by_slug = {entry["slug"]: entry for entry in build_lpse_entries()}
    watchlist_entries = []

    for watchlist in watchlists:
        entry = entries_by_slug.get(watchlist.lpse_slug)
        if entry:
            item = entry.copy()
        else:
            item = {
                "slug": watchlist.lpse_slug,
                "real_slug": watchlist.lpse_slug,
                "lpse_name": watchlist.lpse_name,
                "total_paket": 0,
                "total_hps": 0,
                "total_pagu": 0,
                "paket_open": 0,
                "paket_ongoing": 0,
                "paket_finish": 0,
                "paket_failed": 0,
                "latest_tender_date": None,
            }
        item["created_at"] = watchlist.created_at
        watchlist_entries.append(item)

    return {
        "watchlist_entries": watchlist_entries,
        "watchlist_count": len(watchlist_entries),
        "watchlist_limit": LPSE_WATCHLIST_LIMIT,
    }


@login_required
def lpse_watchlist_view(request):
    return render(request, "lpse/watchlist.html", build_lpse_watchlist_context(request))


def render_lpse_watchlist_mutation_response(request):
    current_url = request.headers.get("HX-Current-URL", "")
    if request.headers.get("HX-Request"):
        if "/lpse/watchlist" in current_url:
            return render(request, "lpse/watchlist_partial.html", build_lpse_watchlist_context(request))
        return render(request, "lpse/list_partial.html", build_lpse_list_context(request, request.POST))

    next_url = get_safe_redirect_url(
        request,
        request.POST.get("next") or request.META.get("HTTP_REFERER"),
        reverse("lpse_list"),
    )
    return redirect(next_url)


@login_required
@require_POST
def add_lpse_watchlist(request, slug):
    entry = get_lpse_entry_or_404(slug)

    if LPSEWatchlist.objects.filter(user=request.user, lpse_slug=entry["slug"]).exists():
        messages.info(request, f"{entry['lpse_name']} sudah ada di watchlist.")
        return render_lpse_watchlist_mutation_response(request)

    if LPSEWatchlist.objects.filter(user=request.user).count() >= LPSE_WATCHLIST_LIMIT:
        messages.error(request, "Maksimal 5 LPSE dalam watchlist untuk saat ini.")
        return render_lpse_watchlist_mutation_response(request)

    try:
        LPSEWatchlist.objects.create(
            user=request.user,
            lpse_slug=entry["slug"],
            lpse_name=entry["lpse_name"],
        )
        messages.success(request, f"{entry['lpse_name']} ditambahkan ke watchlist.")
    except IntegrityError:
        messages.info(request, f"{entry['lpse_name']} sudah ada di watchlist.")

    return render_lpse_watchlist_mutation_response(request)


@login_required
@require_POST
def remove_lpse_watchlist(request, slug):
    deleted_count, _ = LPSEWatchlist.objects.filter(
        user=request.user,
        lpse_slug=slug,
    ).delete()

    if deleted_count:
        messages.success(request, "LPSE dihapus dari watchlist.")
    else:
        messages.info(request, "LPSE tidak ditemukan dalam watchlist Anda.")

    return render_lpse_watchlist_mutation_response(request)


def build_lpse_entries():
    groups = {}
    field_names = {field.name for field in Tender._meta.get_fields()}
    values = [
        "id",
        "lpse_name",
        "detail_url",
        "lpse_detail_url",
        "status",
        "nilai_hps",
        "nilai_pagu",
        "tanggal_pembuatan",
    ]
    if "lpse_slug" in field_names:
        values.append("lpse_slug")

    for tender in get_operational_queryset().values(*values):
        slug = tender.get("lpse_slug") or infer_slug_from_urls(tender.get("detail_url"), tender.get("lpse_detail_url"))
        lpse_name = tender.get("lpse_name") or slug or "LPSE Tidak Diketahui"
        key = slug or slugify(lpse_name) or f"lpse-{tender['id']}"

        group = groups.setdefault(
            key,
            {
                "slug": key,
                "real_slug": slug,
                "lpse_name": lpse_name,
                "total_paket": 0,
                "total_hps": 0,
                "total_pagu": 0,
                "paket_open": 0,
                "paket_ongoing": 0,
                "paket_finish": 0,
                "paket_failed": 0,
                "latest_tender_date": None,
            },
        )
        if not group["real_slug"] and slug:
            group["real_slug"] = slug
            group["slug"] = slug
        if group["lpse_name"] == "LPSE Tidak Diketahui" and lpse_name:
            group["lpse_name"] = lpse_name

        group["total_paket"] += 1
        group["total_hps"] += tender.get("nilai_hps") or 0
        group["total_pagu"] += tender.get("nilai_pagu") or 0

        status = tender.get("status")
        if status == "OPEN":
            group["paket_open"] += 1
        elif status == "ONGOING":
            group["paket_ongoing"] += 1
        elif status == "FINISH":
            group["paket_finish"] += 1
        elif status == "FAILED":
            group["paket_failed"] += 1

        date_value = tender.get("tanggal_pembuatan")
        if date_value and (not group["latest_tender_date"] or date_value > group["latest_tender_date"]):
            group["latest_tender_date"] = date_value

    return list(groups.values())


def infer_slug_from_urls(*urls):
    for url in urls:
        if not url:
            continue
        match = __import__("re").search(r"spse\.inaproc\.id/([^/]+)/lelang/", url)
        if match:
            return match.group(1)
    return ""


def lpse_detail_view(request, slug):
    queryset = lpse_analytics.get_lpse_queryset(slug)
    if not queryset.exists():
        raise Http404("LPSE tidak ditemukan")

    sample = queryset.first()
    real_slug = lpse_analytics.infer_slug_from_tender(sample) or slug
    lpse_name = sample.lpse_name or real_slug or slug
    filter_options = get_lpse_tender_filter_options(queryset)
    tender_list_url = reverse("lpse_detail", kwargs={"slug": slug})
    tender_context = get_paginated_tenders(
        request,
        base_queryset=queryset,
        sort_options=LPSE_TENDER_SORT_OPTIONS,
        tender_list_url=tender_list_url,
        tender_list_target="#lpse-tender-list",
    )
    analytics_queryset = queryset
    selected_tahun = tender_context["selected_filters"]["tahun"]
    if selected_tahun:
        analytics_queryset = analytics_queryset.filter(tahun_anggaran__contains=selected_tahun)

    saved_ids = []
    if request.user.is_authenticated:
        saved_ids = list(TenderBookmark.objects.filter(
            user=request.user,
            tender__in=tender_context["tenders"],
        ).values_list("tender_id", flat=True))

    context = {
        "lpse_slug": real_slug,
        "lpse_name": lpse_name,
        "old_url": "",
        "lpse_url": f"https://spse.inaproc.id/{real_slug}/lelang" if real_slug else "",
        "summary": lpse_analytics.calculate_lpse_summary(analytics_queryset),
        "top_procurement_types": lpse_analytics.get_top_procurement_types(analytics_queryset),
        "top_instansi": lpse_analytics.get_top_instansi(analytics_queryset),
        "top_active_tenders": lpse_analytics.get_top_active_tenders(analytics_queryset),
        "latest_tenders": lpse_analytics.get_latest_tenders(analytics_queryset),
        "quality": lpse_analytics.get_data_quality_metrics(analytics_queryset),
        "filter_options": filter_options,
        "saved_ids": saved_ids,
        "selected_filters": tender_context["selected_filters"],
        **{key: value for key, value in tender_context.items() if key not in {"selected_filters", "saved_ids"}},
    }

    if request.headers.get("HX-Request"):
        return render(request, "dashboard/tender_list.html", context)
    return render(request, "lpse/detail.html", context)


def open_lpse_detail(request, kode_tender):
    tender = Tender.objects.filter(kode_tender=str(kode_tender)).order_by("-updated_at", "-id").first()
    if not tender:
        raise Http404("Tender tidak ditemukan")
    return render_open_lpse_detail(request, tender)


def open_lpse_detail_by_id(request, pk):
    tender = get_object_or_404(Tender, id=pk)
    return render_open_lpse_detail(request, tender)


def render_open_lpse_detail(request, tender):
    detail_url = tender.detail_url or tender.lpse_detail_url
    slug = get_spse_slug(tender, detail_url)

    if not detail_url and slug:
        detail_url = f"https://spse.inaproc.id/{slug}/lelang/{tender.kode_tender}/pengumumanlelang"

    if not detail_url:
        raise Http404("Detail LPSE belum tersedia")

    list_url = ""
    if slug:
        tahun = tender.tahun_anggaran or ""
        list_url = (
            f"https://spse.inaproc.id/{slug}/lelang?"
            f"kategoriId=&tahun={tahun}&instansiId=&rekanan=&kontrak_status=&kontrak_tipe="
        )

    return render(request, "dashboard/open_lpse_redirect.html", {
        "tender": tender,
        "detail_url": detail_url,
        "list_url": list_url,
    })


def get_spse_slug(tender, detail_url=""):
    if hasattr(tender, "lpse_slug") and tender.lpse_slug:
        return tender.lpse_slug

    url = detail_url or tender.detail_url or tender.lpse_detail_url or ""
    match = __import__("re").search(r"spse\.inaproc\.id/([^/]+)/lelang/", url)
    if match:
        return match.group(1)

    return ""


@login_required
@require_POST
def toggle_bookmark(request, pk):
    tender = get_object_or_404(Tender, id=pk)

    bookmark, created = TenderBookmark.objects.get_or_create(
        user=request.user,
        tender=tender
    )

    if not created:
        bookmark.delete()

        current_url = request.headers.get("HX-Current-URL", "")
        if current_url.endswith("/dashboard/saved/") or current_url.endswith("/tenders/bookmarks/"):
            return HttpResponse("")

        saved = False

    else:
        saved = True

    return render(request, "dashboard/bookmark_button.html", {
        "t": tender,
        "saved": saved
    })


@login_required
def saved_tenders(request):
    bookmarks = TenderBookmark.objects.filter(
        user=request.user
    ).select_related("tender")

    tenders = [b.tender for b in bookmarks]
    attach_match_data(request, tenders)

    saved_ids = [t.id for t in tenders]

    return render(request, "dashboard/saved.html", {
        "tenders": tenders,
        "saved_ids": saved_ids,
    })


def saved_tenders_legacy(request):
    return redirect("saved_tenders")
