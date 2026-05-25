from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.http import urlencode

from .models import Tender, TenderBookmark
from .services import lpse_analytics
from .services.matching import calculate_tender_match


PROCUREMENT_TYPE_OPTIONS = [
    "Pekerjaan Konstruksi",
    "Pengadaan Barang",
    "Jasa Konsultansi",
    "Jasa Lainnya",
]

SORT_OPTIONS = {
    "created_desc": "Terbaru",
    "created_asc": "Terlama",
    "match_desc": "AI Match Tertinggi",
    "match_asc": "AI Match Terendah",
    "hps_desc": "Nilai HPS Tertinggi",
    "hps_asc": "Nilai HPS Terendah",
}

LPSE_TENDER_SORT_OPTIONS = {
    "created_desc": "Terbaru",
    "hps_desc": "HPS tertinggi",
    "hps_asc": "HPS terendah",
    "match_desc": "AI Match tertinggi",
    "name_asc": "Nama Paket A-Z",
}

ALLOWED_PER_PAGE = [15, 25, 50, 100]
DEFAULT_PER_PAGE = 25


LOGIN_REQUIRED_MATCH = {
    "score": None,
    "level": "Low",
    "label": "Login untuk melihat AI Match",
    "reasons": [],
    "missing": [
        "Login untuk melihat AI Match.",
    ],
    "requires_login": True,
    "requires_profile": False,
}


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    return render(request, "index.html")


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
    klpd_values = set(
        Tender.objects.exclude(klpd_instansi="")
        .values_list("klpd_instansi", flat=True)
        .distinct()
    )
    klpd_values.update(
        Tender.objects.filter(klpd_instansi="")
        .exclude(instansi="")
        .values_list("instansi", flat=True)
        .distinct()
    )

    return {
        "jenis_pengadaan": PROCUREMENT_TYPE_OPTIONS,
        "klpd_instansi": sorted(value for value in klpd_values if value)[:150],
        "sort": SORT_OPTIONS,
    }


def get_lpse_tender_filter_options(queryset):
    jenis_values = (
        queryset.exclude(jenis_pengadaan="")
        .values_list("jenis_pengadaan", flat=True)
        .distinct()
    )
    tahun_values = (
        queryset.exclude(tahun_anggaran="")
        .values_list("tahun_anggaran", flat=True)
        .distinct()
    )
    return {
        "jenis_pengadaan": sorted(value for value in jenis_values if value),
        "tahun_anggaran": sorted((value for value in tahun_values if value), reverse=True),
        "sort": LPSE_TENDER_SORT_OPTIONS,
    }


def get_selected_filters(request, sort_options=None):
    sort_options = sort_options or SORT_OPTIONS
    sort = request.GET.get("sort") or "created_desc"
    if sort not in sort_options:
        sort = "created_desc"

    return {
        "q": request.GET.get("q", request.GET.get("tender", "")).strip(),
        "status": request.GET.get("status", "").strip(),
        "jenis_pengadaan": request.GET.get("jenis_pengadaan", "").strip(),
        "klpd_instansi": request.GET.get("klpd_instansi", "").strip(),
        "tahun_anggaran": request.GET.get("tahun_anggaran", "").strip(),
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
    params["per_page"] = str(per_page)
    return params.urlencode()


def get_filtered_queryset(request, base_queryset=None, sort_options=None):
    selected = get_selected_filters(request, sort_options)
    tenders = base_queryset if base_queryset is not None else Tender.objects.all()

    if selected["q"]:
        tenders = tenders.filter(
            Q(nama_paket__icontains=selected["q"])
            | Q(kode_tender__icontains=selected["q"])
            | Q(instansi__icontains=selected["q"])
            | Q(klpd_instansi__icontains=selected["q"])
        )

    if selected["status"]:
        tenders = tenders.filter(status=selected["status"])

    if selected["jenis_pengadaan"]:
        tenders = tenders.filter(jenis_pengadaan=selected["jenis_pengadaan"])

    if selected["klpd_instansi"]:
        tenders = tenders.filter(
            Q(klpd_instansi=selected["klpd_instansi"])
            | (Q(klpd_instansi="") & Q(instansi=selected["klpd_instansi"]))
        )

    if selected["tahun_anggaran"]:
        tenders = tenders.filter(tahun_anggaran=selected["tahun_anggaran"])

    return tenders, selected


def apply_db_sort(tenders, sort):
    if sort == "created_asc":
        return tenders.order_by(F("tanggal_pembuatan").asc(nulls_last=True), "id")
    if sort == "hps_desc":
        return tenders.order_by(F("nilai_hps").desc(nulls_last=True), "-id")
    if sort == "hps_asc":
        return tenders.order_by(F("nilai_hps").asc(nulls_last=True), "id")
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


def dashboard(request):
    tender_context = get_paginated_tenders(request)
    tenders = tender_context["tenders"]
    match_scores = [
        tender.match_data.get("score")
        for tender in tenders
        if tender.match_data.get("score") is not None
    ]

    saved_ids = []
    if request.user.is_authenticated:
        saved_ids = list(TenderBookmark.objects.filter(
            user=request.user
        ).values_list("tender_id", flat=True))

    context = {
        "tenders": tenders,
        "saved_ids": saved_ids,
        "filter_options": get_filter_options(),
        "selected_filters": tender_context["selected_filters"],
        "best_match_score": max(match_scores) if match_scores else None,
        **{key: value for key, value in tender_context.items() if key not in {"tenders", "selected_filters"}},
    }
    return render(request, "dashboard/index.html", context)


def tender_list(request):
    tender_context = get_paginated_tenders(request)
    tenders = tender_context["tenders"]

    saved_ids = []
    if request.user.is_authenticated:
        saved_ids = list(TenderBookmark.objects.filter(
            user=request.user
        ).values_list("tender_id", flat=True))

    context = {
        "tenders": tenders,
        "saved_ids": saved_ids,
        "selected_filters": tender_context["selected_filters"],
        **{key: value for key, value in tender_context.items() if key not in {"tenders", "selected_filters"}},
    }
    return render(request, "dashboard/tender_list.html", context)


def tender_detail(request, pk):
    tender = get_object_or_404(Tender, id=pk)
    tender.match_data = get_match_data(request, tender)
    return render(request, "dashboard/tender_detail.html", {"t": tender})


def lpse_list_view(request):
    entries = build_lpse_entries()
    query = request.GET.get("q", "").strip().casefold()
    sort = request.GET.get("sort") or "total_desc"
    per_page = get_per_page(request)
    page = get_page_number(request)

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
    params = request.GET.copy()
    params.pop("page", None)
    params["per_page"] = str(per_page)

    context = {
        "lpse_entries": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "per_page": per_page,
        "allowed_per_page": ALLOWED_PER_PAGE,
        "pagination_query": params.urlencode(),
        "total_count": paginator.count,
        "selected": {"q": request.GET.get("q", ""), "sort": sort},
        "sort_options": {
            "total_desc": "Total Paket terbanyak",
            "hps_desc": "Total HPS tertinggi",
            "open_desc": "Paket OPEN terbanyak",
            "name_asc": "Nama LPSE A-Z",
        },
    }

    template = "lpse/list_partial.html" if request.headers.get("HX-Request") else "lpse/list.html"
    return render(request, template, context)


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

    for tender in Tender.objects.values(*values):
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
    summary = lpse_analytics.calculate_lpse_summary(queryset)
    tender_list_url = reverse("lpse_detail", kwargs={"slug": slug})
    tender_context = get_paginated_tenders(
        request,
        base_queryset=queryset,
        sort_options=LPSE_TENDER_SORT_OPTIONS,
        tender_list_url=tender_list_url,
        tender_list_target="#lpse-tender-list",
    )

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
        "summary": summary,
        "top_procurement_types": lpse_analytics.get_top_procurement_types(queryset),
        "top_instansi": lpse_analytics.get_top_instansi(queryset),
        "top_active_tenders": lpse_analytics.get_top_active_tenders(queryset),
        "latest_tenders": lpse_analytics.get_latest_tenders(queryset),
        "quality": lpse_analytics.get_data_quality_metrics(queryset),
        "filter_options": get_lpse_tender_filter_options(queryset),
        "saved_ids": saved_ids,
        "selected_filters": tender_context["selected_filters"],
        **{key: value for key, value in tender_context.items() if key not in {"selected_filters", "saved_ids"}},
    }

    if request.headers.get("HX-Request"):
        return render(request, "dashboard/tender_list.html", context)
    return render(request, "lpse/detail.html", context)


def open_lpse_detail(request, kode_tender):
    tender = get_object_or_404(Tender, kode_tender=str(kode_tender))
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
def toggle_bookmark(request, pk):
    tender = get_object_or_404(Tender, id=pk)

    bookmark, created = TenderBookmark.objects.get_or_create(
        user=request.user,
        tender=tender
    )

    if not created:
        bookmark.delete()

        # Kalau dari halaman saved -> hapus card.
        if request.headers.get("HX-Current-URL", "").endswith("/dashboard/saved/"):
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
