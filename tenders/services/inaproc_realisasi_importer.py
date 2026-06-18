from django.db import transaction

from tenders.models import Tender


MAIN_SOURCE = "inaproc_realisasi_csv"
DETAIL_SOURCE = "inaproc_realisasi_detail_csv"
DETAIL_REQUIRED_FIELDS = ("nilai_hps", "nilai_pagu", "lokasi_pekerjaan", "detail_url")


def clean_text(value):
    if value in (None, ""):
        return ""
    return str(value).strip()


def set_if_value(defaults, field_name, value):
    if value in (None, ""):
        return
    defaults[field_name] = value


def set_if_empty(defaults, tender, field_name, value):
    if value in (None, ""):
        return
    if not getattr(tender, field_name, None):
        defaults[field_name] = value


def merge_raw_data(existing, key, value):
    if isinstance(existing, dict):
        merged = existing.copy()
    elif existing:
        merged = {"previous": existing}
    else:
        merged = {}
    merged[key] = value
    return merged


def find_tender(kode_paket="", kode_tender=""):
    kode_paket = clean_text(kode_paket)
    kode_tender = clean_text(kode_tender)

    if kode_paket:
        tender = Tender.objects.filter(kode_paket=kode_paket).first()
        if tender:
            return tender

    if kode_tender:
        tender = Tender.objects.filter(kode_tender=kode_tender).first()
        if tender:
            return tender

    if kode_paket:
        return Tender.objects.filter(kode_tender=kode_paket).first()
    return None


def build_main_defaults(row, existing=None):
    defaults = {}
    kode_paket = clean_text(row.get("kode_paket"))
    kode_tender = clean_text(row.get("kode_tender")) or kode_paket
    status_paket = clean_text(row.get("status_paket"))
    total_nilai = row.get("total_nilai")

    set_if_value(defaults, "kode_paket", kode_paket)
    set_if_value(defaults, "kode_tender", kode_tender)
    set_if_value(defaults, "kode_rup", row.get("kode_rup"))
    set_if_value(defaults, "nama_paket", row.get("nama_paket"))
    set_if_value(defaults, "nama_instansi", row.get("nama_instansi"))
    set_if_value(defaults, "nama_satuan_kerja", row.get("nama_satuan_kerja"))
    set_if_value(defaults, "instansi", row.get("nama_instansi"))
    set_if_value(defaults, "klpd_instansi", row.get("nama_instansi"))
    set_if_value(defaults, "satuankerja", row.get("nama_satuan_kerja"))
    set_if_value(defaults, "sumber_transaksi", row.get("sumber_transaksi"))
    set_if_value(defaults, "sumber_dana", row.get("sumber_dana"))
    set_if_value(defaults, "nama_penyedia", row.get("nama_penyedia"))
    set_if_value(defaults, "metode_pengadaan", row.get("metode_pengadaan"))
    set_if_value(defaults, "jenis_pengadaan", row.get("jenis_pengadaan"))
    set_if_value(defaults, "status_paket", status_paket)
    set_if_value(defaults, "status", status_paket)
    set_if_value(defaults, "tahapan", status_paket)
    set_if_value(defaults, "tahun_anggaran", row.get("tahun_anggaran"))
    set_if_value(defaults, "total_nilai", total_nilai)
    set_if_value(defaults, "nilai_pdn", row.get("nilai_pdn"))
    set_if_value(defaults, "data_source", MAIN_SOURCE)

    if total_nilai is not None and (existing is None or existing.nilai_hps is None):
        defaults["nilai_hps"] = total_nilai
    if total_nilai is not None and (existing is None or existing.nilai_pagu is None):
        defaults["nilai_pagu"] = total_nilai

    defaults["raw_data"] = merge_raw_data(
        getattr(existing, "raw_data", None) if existing else None,
        "realisasi",
        row,
    )
    return defaults


def upsert_realisasi_row(row, dry_run=False):
    kode_paket = clean_text(row.get("kode_paket"))
    kode_tender = clean_text(row.get("kode_tender")) or kode_paket
    if not kode_paket and not kode_tender:
        return "skipped", None

    existing = find_tender(kode_paket=kode_paket, kode_tender=kode_tender)
    defaults = build_main_defaults(row, existing=existing)

    if dry_run:
        return ("updated" if existing else "created"), existing

    with transaction.atomic():
        if existing:
            tender, created = Tender.objects.update_or_create(
                pk=existing.pk,
                defaults=defaults,
            )
        elif kode_paket:
            tender, created = Tender.objects.update_or_create(
                kode_paket=kode_paket,
                defaults=defaults,
            )
        else:
            tender, created = Tender.objects.update_or_create(
                kode_tender=kode_tender,
                defaults=defaults,
            )
    return ("created" if created else "updated"), tender


def tender_missing_detail(tender):
    return any(not getattr(tender, field_name, None) for field_name in DETAIL_REQUIRED_FIELDS)


def build_missing_detail_filter():
    from django.db.models import Q

    missing_filter = Q(pk__isnull=True)
    for field_name in ("lokasi_pekerjaan", "detail_url"):
        missing_filter |= Q(**{f"{field_name}__isnull": True}) | Q(**{field_name: ""})
    for field_name in ("nilai_hps", "nilai_pagu"):
        missing_filter |= Q(**{f"{field_name}__isnull": True})
    return missing_filter


def build_detail_defaults(tender, row):
    defaults = {}
    new_kode_tender = clean_text(row.get("kode_tender"))
    if new_kode_tender and new_kode_tender != tender.kode_tender:
        conflict = Tender.objects.filter(kode_tender=new_kode_tender).exclude(pk=tender.pk).first()
        if conflict:
            raise ValueError(f"kode_tender {new_kode_tender} already exists on Tender id={conflict.pk}")
        defaults["kode_tender"] = new_kode_tender

    set_if_empty(defaults, tender, "nama_paket", row.get("nama_tender"))
    set_if_empty(defaults, tender, "tanggal_tender", row.get("tanggal_tender"))
    set_if_empty(defaults, tender, "tanggal_pembuatan", row.get("tanggal_tender"))
    set_if_empty(defaults, tender, "nilai_hps", row.get("nilai_hps"))
    set_if_empty(defaults, tender, "nilai_pagu", row.get("nilai_pagu"))
    set_if_empty(defaults, tender, "instansi", row.get("instansi"))
    set_if_empty(defaults, tender, "klpd_instansi", row.get("instansi"))
    set_if_empty(defaults, tender, "nama_instansi", row.get("instansi"))
    set_if_empty(defaults, tender, "kategori", row.get("kategori"))
    set_if_empty(defaults, tender, "jenis_pengadaan", row.get("kategori"))
    set_if_empty(defaults, tender, "metode_tender", row.get("metode_tender"))
    set_if_empty(defaults, tender, "metode_pengadaan", row.get("metode_tender"))
    set_if_empty(defaults, tender, "metode_evaluasi", row.get("metode_evaluasi"))
    set_if_empty(defaults, tender, "cara_pembayaran", row.get("cara_pembayaran"))
    set_if_empty(defaults, tender, "tahun_anggaran", row.get("tahun_anggaran"))
    set_if_empty(defaults, tender, "sumber_dana", row.get("sumber_dana"))
    set_if_empty(defaults, tender, "lokasi_pekerjaan", row.get("lokasi_pekerjaan"))
    set_if_empty(defaults, tender, "detail_url", row.get("detail_url"))
    set_if_empty(defaults, tender, "lpse_detail_url", row.get("detail_url"))
    set_if_empty(defaults, tender, "satuankerja", row.get("satuan_kerja"))
    set_if_empty(defaults, tender, "nama_satuan_kerja", row.get("satuan_kerja"))

    defaults["data_source"] = DETAIL_SOURCE
    defaults["raw_data"] = merge_raw_data(getattr(tender, "raw_data", None), "realisasi_detail", row)
    return defaults


def apply_detail_row(tender, row, dry_run=False):
    defaults = build_detail_defaults(tender, row)
    update_fields = [field for field in defaults if field != "raw_data"]
    if update_fields == ["data_source"] or not update_fields:
        return "skipped", tender

    if dry_run:
        return "enriched", tender

    for field_name, value in defaults.items():
        setattr(tender, field_name, value)
    tender.save(update_fields=list(defaults.keys()) + ["updated_at"])
    return "enriched", tender
