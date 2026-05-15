from django.shortcuts import render, redirect
from django.shortcuts import get_object_or_404
from .models import Tender
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .models import TenderBookmark

def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    return render(request, "index.html")

def dashboard(request):
    tenders = Tender.objects.all()

    saved_ids = []
    if request.user.is_authenticated:
        saved_ids = TenderBookmark.objects.filter(
            user=request.user
        ).values_list("tender_id", flat=True)

    return render(request, "dashboard/index.html", {
        "tenders": tenders,
        "saved_ids": saved_ids,
    })

def tender_list(request):
    query = request.GET.get("q", "")
    status = request.GET.get("status", "")

    tenders = Tender.objects.all()

    if query:
        tenders = tenders.filter(nama_paket__icontains=query)

    if status:
        tenders = tenders.filter(status=status)

    saved_ids = []
    if request.user.is_authenticated:
        saved_ids = TenderBookmark.objects.filter(
            user=request.user
        ).values_list("tender_id", flat=True)

    return render(request, "dashboard/tender_list.html", {
        "tenders": tenders,
        "saved_ids": saved_ids,
    })

def tender_detail(request, pk):
    tender = get_object_or_404(Tender, id=pk)
    return render(request, "dashboard/tender_detail.html", {"t": tender})

@login_required
def toggle_bookmark(request, pk):
    tender = get_object_or_404(Tender, id=pk)

    bookmark, created = TenderBookmark.objects.get_or_create(
        user=request.user,
        tender=tender
    )

    # UNSAVE
    if not created:
        bookmark.delete()

        # kalau dari halaman saved → hapus card
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

    saved_ids = [t.id for t in tenders]

    return render(request, "dashboard/saved.html", {
        "tenders": tenders,
        "saved_ids": saved_ids,
    })
