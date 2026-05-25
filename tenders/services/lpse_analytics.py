import re
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.template.defaultfilters import slugify

from tenders.models import Tender


SPSE_DETAIL_RE = re.compile(r"spse\.inaproc\.id/([^/]+)/lelang/")


def model_has_field(model, field_name):
    try:
        model._meta.get_field(field_name)
        return True
    except Exception:
        return False


def format_currency_idr(value):
    if value in (None, ""):
        return "Rp 0"
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return "Rp 0"
    return "Rp " + f"{amount:,}".replace(",", ".")


def infer_slug_from_tender(tender):
    if model_has_field(Tender, "lpse_slug") and tender.lpse_slug:
        return tender.lpse_slug

    for url in (tender.detail_url, tender.lpse_detail_url):
        match = SPSE_DETAIL_RE.search(url or "")
        if match:
            return match.group(1)
    return ""


def get_lpse_queryset(slug_or_name):
    slug_or_name = str(slug_or_name or "").strip()
    queryset = Tender.objects.all()

    filters = Q(lpse_name__iexact=slug_or_name)
    if model_has_field(Tender, "lpse_slug"):
        filters |= Q(lpse_slug=slug_or_name)

    filters |= Q(detail_url__icontains=f"/{slug_or_name}/lelang/")
    filters |= Q(lpse_detail_url__icontains=f"/{slug_or_name}/lelang/")

    result = queryset.filter(filters)
    if result.exists():
        return result

    matching_ids = [
        tender.id
        for tender in queryset.only("id", "lpse_name")
        if tender.lpse_name and slugify(tender.lpse_name) == slug_or_name
    ]
    return queryset.filter(id__in=matching_ids)


def calculate_lpse_summary(queryset):
    aggregate_fields = {
        "total_paket": Count("id"),
        "total_hps": Sum("nilai_hps"),
        "total_pagu": Sum("nilai_pagu"),
        "hps_finished": Sum("nilai_hps", filter=Q(status="FINISH")),
        "paket_open": Count("id", filter=Q(status="OPEN")),
        "paket_ongoing": Count("id", filter=Q(status="ONGOING")),
        "paket_finish": Count("id", filter=Q(status="FINISH")),
        "paket_failed": Count("id", filter=Q(status="FAILED")),
        "avg_hps": Avg("nilai_hps"),
        "avg_peserta": Avg("peserta_count"),
    }
    if model_has_field(Tender, "nilai_kontrak"):
        aggregate_fields["total_nilai_kontrak"] = Sum("nilai_kontrak")

    summary = queryset.aggregate(**aggregate_fields)
    summary = {key: value or 0 for key, value in summary.items()}

    total_kontrak = summary.get("total_nilai_kontrak")
    hps_finished = summary.get("hps_finished")
    if total_kontrak and hps_finished:
        summary["efisiensi_kontrak_hps"] = (Decimal(total_kontrak) / Decimal(hps_finished)) * 100
    else:
        summary["efisiensi_kontrak_hps"] = None

    return summary


def get_top_procurement_types(queryset):
    return list(
        queryset.exclude(jenis_pengadaan="")
        .values("jenis_pengadaan")
        .annotate(count=Count("id"), total_hps=Sum("nilai_hps"))
        .order_by("-count", "-total_hps")[:5]
    )


def get_top_instansi(queryset):
    field_name = "klpd_instansi"
    if not queryset.exclude(klpd_instansi="").exists():
        field_name = "instansi"

    rows = list(
        queryset.exclude(**{field_name: ""})
        .values(field_name)
        .annotate(count=Count("id"), total_hps=Sum("nilai_hps"))
        .order_by("-count", "-total_hps")[:5]
    )
    for row in rows:
        row["name"] = row.get(field_name) or "-"
    return rows


def get_top_active_tenders(queryset):
    return list(
        queryset.filter(status__in=["OPEN", "ONGOING"])
        .order_by("-nilai_hps", "-id")[:5]
    )


def get_latest_tenders(queryset):
    if queryset.exclude(tanggal_pembuatan__isnull=True).exists():
        return list(queryset.order_by("-tanggal_pembuatan", "-id")[:5])
    return list(queryset.order_by("-id")[:5])


def get_data_quality_metrics(queryset):
    total = queryset.count()
    failed = queryset.filter(status="FAILED").count()
    without_location = queryset.filter(Q(lokasi_pekerjaan__isnull=True) | Q(lokasi_pekerjaan="")).count()
    without_funding = queryset.filter(Q(sumber_dana__isnull=True) | Q(sumber_dana="")).count()

    return {
        "failed_count": failed,
        "failed_percentage": (failed / total * 100) if total else 0,
        "without_location": without_location,
        "without_funding": without_funding,
    }
