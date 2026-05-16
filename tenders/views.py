from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import Tender, TenderBookmark
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


def get_selected_filters(request):
    sort = request.GET.get("sort") or "created_desc"
    if sort not in SORT_OPTIONS:
        sort = "created_desc"

    return {
        "q": request.GET.get("q", request.GET.get("tender", "")).strip(),
        "status": request.GET.get("status", "").strip(),
        "jenis_pengadaan": request.GET.get("jenis_pengadaan", "").strip(),
        "klpd_instansi": request.GET.get("klpd_instansi", "").strip(),
        "sort": sort,
    }


def get_filtered_tenders(request):
    selected = get_selected_filters(request)
    tenders = Tender.objects.all()

    if selected["q"]:
        tenders = tenders.filter(nama_paket__icontains=selected["q"])

    if selected["status"]:
        tenders = tenders.filter(status=selected["status"])

    if selected["jenis_pengadaan"]:
        tenders = tenders.filter(jenis_pengadaan=selected["jenis_pengadaan"])

    if selected["klpd_instansi"]:
        tenders = tenders.filter(
            Q(klpd_instansi=selected["klpd_instansi"])
            | (Q(klpd_instansi="") & Q(instansi=selected["klpd_instansi"]))
        )

    sort = selected["sort"]
    if sort == "created_asc":
        tenders = tenders.order_by(F("tanggal_pembuatan").asc(nulls_last=True), "id")
    elif sort == "hps_desc":
        tenders = tenders.order_by(F("nilai_hps").desc(nulls_last=True), "-id")
    elif sort == "hps_asc":
        tenders = tenders.order_by(F("nilai_hps").asc(nulls_last=True), "id")
    else:
        tenders = tenders.order_by(F("tanggal_pembuatan").desc(nulls_last=True), "-id")

    tenders = list(tenders)
    attach_match_data(request, tenders)

    if sort == "match_desc":
        tenders.sort(
            key=lambda tender: tender.match_data.get("score") or 0,
            reverse=True,
        )
    elif sort == "match_asc":
        tenders.sort(key=lambda tender: tender.match_data.get("score") or 0)

    return tenders, selected


def dashboard(request):
    tenders, selected_filters = get_filtered_tenders(request)
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

    return render(request, "dashboard/index.html", {
        "tenders": tenders,
        "saved_ids": saved_ids,
        "filter_options": get_filter_options(),
        "selected_filters": selected_filters,
        "best_match_score": max(match_scores) if match_scores else None,
    })


def tender_list(request):
    tenders, selected_filters = get_filtered_tenders(request)

    saved_ids = []
    if request.user.is_authenticated:
        saved_ids = list(TenderBookmark.objects.filter(
            user=request.user
        ).values_list("tender_id", flat=True))

    return render(request, "dashboard/tender_list.html", {
        "tenders": tenders,
        "saved_ids": saved_ids,
        "selected_filters": selected_filters,
    })


def tender_detail(request, pk):
    tender = get_object_or_404(Tender, id=pk)
    tender.match_data = get_match_data(request, tender)
    return render(request, "dashboard/tender_detail.html", {"t": tender})


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
