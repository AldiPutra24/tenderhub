import csv
import io
import json
import re
import time
from datetime import date, datetime

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from django.utils.dateparse import parse_date as django_parse_date
from django.utils.dateparse import parse_datetime

from tenders.models import Tender


MASTER_LPSE_URL = "https://isb.lkpp.go.id/isb-2/api/satudata/MasterLPSE"
TENDER_UMUM_URL = "https://isb.lkpp.go.id/isb-2/api/satudata/TenderUmumPublik/{tahun}/{kd_lpse}"
REQUEST_TIMEOUT_SECONDS = 60
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2


def model_has_field(model, field_name):
    try:
        model._meta.get_field(field_name)
        return True
    except Exception:
        return False


def get_any(row, keys, default=None):
    if not isinstance(row, dict):
        return default

    for key in keys:
        if key in row:
            return row[key]

    return default


def clean_text(value):
    if value in (None, ""):
        return ""
    return str(value).strip()


def parse_number(value):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip()
    if not text:
        return None

    if "," in text and "." in text:
        text = text.split(",", 1)[0]
    elif "," in text:
        text = text.split(",", 1)[0]

    digits = re.sub(r"[^\d-]", "", text)
    if not digits or digits == "-":
        return None

    try:
        return int(digits)
    except ValueError:
        return None


def parse_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    parsed_datetime = parse_datetime(text)
    if parsed_datetime:
        return parsed_datetime.date()

    parsed_date = django_parse_date(text)
    if parsed_date:
        return parsed_date

    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def first_item(value):
    if isinstance(value, list):
        return value[0] if value else {}
    if isinstance(value, dict):
        return value
    return {}


def extract_instansi_satker(value):
    item = first_item(value)
    return {
        "rup_id": clean_text(item.get("rup_id")),
        "nama_instansi": clean_text(item.get("nama_instansi")),
        "stk_nama": clean_text(item.get("stk_nama")),
        "jenis_instansi": clean_text(item.get("jenis_instansi")),
    }


def extract_anggaran(value):
    item = first_item(value)
    return {
        "sbd_id": clean_text(item.get("sbd_id")),
        "ang_tahun": clean_text(item.get("ang_tahun")),
    }


def extract_lokasi(value):
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()

    lokasi_items = value if isinstance(value, list) else [value]
    labels = []

    for item in lokasi_items:
        if isinstance(item, dict) and isinstance(item.get("lokasi"), dict):
            item = item["lokasi"]

        if not isinstance(item, dict):
            text = clean_text(item)
            if text:
                labels.append(text)
            continue

        label = " - ".join(
            part
            for part in (
                clean_text(item.get("prp_nama")),
                clean_text(item.get("kbp_nama")),
                clean_text(item.get("pkt_lokasi")),
            )
            if part
        )
        if label:
            labels.append(label)

    return "; ".join(labels)


class Command(BaseCommand):
    help = "Sync official public tender data from LKPP ISB Satu Data API"

    def add_arguments(self, parser):
        parser.add_argument("--tahun", type=int, required=True, help="Tender year, for example 2024")

        lpse_group = parser.add_mutually_exclusive_group(required=True)
        lpse_group.add_argument("--kd-lpse", type=int, help="Fetch one LPSE code only")
        lpse_group.add_argument("--limit-lpse", type=int, help="Fetch the first N LPSE codes from MasterLPSE")
        lpse_group.add_argument("--all-lpse", action="store_true", help="Fetch all LPSE codes from MasterLPSE")

    def handle(self, *args, **options):
        tahun = options["tahun"]
        lpse_rows = self.resolve_lpse_rows(options)

        total_created = 0
        total_updated = 0
        total_skipped = 0
        total_failed = 0

        self.stdout.write(f"LKPP ISB sync started: tahun={tahun}, lpse_count={len(lpse_rows)}")

        for lpse in lpse_rows:
            kd_lpse = lpse["kd_lpse"]
            master_lpse_name = lpse.get("nama_lpse", "")
            label = f"{kd_lpse} - {master_lpse_name}".rstrip(" -")
            self.stdout.write(f"Fetching LPSE {label}")

            url = TENDER_UMUM_URL.format(tahun=tahun, kd_lpse=kd_lpse)
            self.stdout.write(f"GET {url}")

            try:
                rows = self.fetch_payload(url)
            except Exception as exc:
                total_failed += 1
                self.stderr.write(self.style.WARNING(f"Failed LPSE {label}: {exc}"))
                self.stdout.write("Created: 0, Updated: 0, Skipped: 0, Failed: 1")
                continue

            if rows in (None, ""):
                rows = []

            if not isinstance(rows, list):
                total_failed += 1
                self.stderr.write(self.style.WARNING(f"Failed LPSE {label}: expected JSON array, got {type(rows).__name__}"))
                self.stdout.write("Created: 0, Updated: 0, Skipped: 0, Failed: 1")
                continue

            created, updated, skipped, failed = self.import_rows(rows, kd_lpse, master_lpse_name)

            total_created += created
            total_updated += updated
            total_skipped += skipped
            total_failed += failed

            self.stdout.write(f"Created: {created}, Updated: {updated}, Skipped: {skipped}, Failed: {failed}")

        self.stdout.write(
            self.style.SUCCESS(
                "LKPP ISB sync finished: "
                f"Created: {total_created}, Updated: {total_updated}, "
                f"Skipped: {total_skipped}, Failed: {total_failed}"
            )
        )

    def resolve_lpse_rows(self, options):
        if options.get("kd_lpse"):
            return [{"kd_lpse": options["kd_lpse"], "nama_lpse": ""}]

        self.stdout.write("Fetching MasterLPSE")
        self.stdout.write(f"GET {MASTER_LPSE_URL}")
        payload = self.fetch_payload(MASTER_LPSE_URL)

        if payload in (None, ""):
            return []
        if not isinstance(payload, list):
            raise CommandError(f"MasterLPSE expected JSON array, got {type(payload).__name__}")

        lpse_rows = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            kd_lpse = parse_number(row.get("kd_lpse"))
            if kd_lpse is None:
                continue
            lpse_rows.append(
                {
                    "kd_lpse": kd_lpse,
                    "nama_lpse": clean_text(row.get("nama_lpse")),
                }
            )

        if options.get("limit_lpse"):
            lpse_rows = lpse_rows[: options["limit_lpse"]]

        return lpse_rows

    def fetch_payload(self, url):
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
                response.raise_for_status()
                return self.decode_response(response)
            except requests.RequestException as exc:
                last_error = exc
            except ValueError as exc:
                last_error = exc

            if attempt < MAX_RETRIES:
                self.stderr.write(self.style.WARNING(f"Retry {attempt}/{MAX_RETRIES} for {url}: {last_error}"))
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

        raise CommandError(f"Request failed after {MAX_RETRIES} attempts: {last_error}")

    def decode_response(self, response):
        try:
            return response.json()
        except ValueError:
            pass

        text = response.text.strip()
        if not text:
            return []

        try:
            return json.loads(text)
        except ValueError:
            pass

        return self.decode_csv_like_text(text)

    def decode_csv_like_text(self, text):
        sample = text[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            raise ValueError("Response is not valid JSON array or CSV-like text")

        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        return [dict(row) for row in reader]

    def import_rows(self, rows, kd_lpse, master_lpse_name):
        created = 0
        updated = 0
        skipped = 0
        failed = 0

        for row in rows:
            try:
                result = self.upsert_tender(row, kd_lpse, master_lpse_name)
            except DatabaseError as exc:
                failed += 1
                self.stderr.write(self.style.WARNING(f"Database row failed: {exc}"))
                continue
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.WARNING(f"Row failed: {exc}"))
                continue

            if result == "created":
                created += 1
            elif result == "updated":
                updated += 1
            else:
                skipped += 1

        return created, updated, skipped, failed

    def upsert_tender(self, row, requested_kd_lpse, master_lpse_name):
        if not isinstance(row, dict):
            return "skipped"

        kode_tender = clean_text(row.get("Kode Tender"))
        if not kode_tender:
            return "skipped"

        instansi_satker = extract_instansi_satker(row.get("Instansi dan Satker"))
        anggaran = extract_anggaran(row.get("anggaran"))
        repo_lpse = parse_number(row.get("Repo id LPSE"))
        lpse_kd = repo_lpse if repo_lpse is not None else requested_kd_lpse
        lpse_name = clean_text(row.get("LPSE")) or master_lpse_name
        tahun_anggaran = clean_text(get_any(row, ["Tahun Anggaran"])) or anggaran["ang_tahun"]

        defaults = {}
        self.set_if_exists(defaults, "lpse_kd", lpse_kd)
        self.set_if_exists(defaults, "lpse_name", lpse_name)
        self.set_if_exists(defaults, "status", clean_text(get_any(row, ["Status_Tender", "Status Tender"])))
        self.set_if_exists(defaults, "nama_paket", clean_text(row.get("Nama Paket")))
        self.set_if_exists(defaults, "nilai_pagu", parse_number(row.get("Pagu")))
        self.set_if_exists(defaults, "nilai_hps", parse_number(row.get("HPS")))
        self.set_if_exists(defaults, "tanggal_pembuatan", parse_date(row.get("tanggal paket dibuat")))
        self.set_if_exists(defaults, "jenis_pengadaan", clean_text(row.get("Kategori Pekerjaan")))
        self.set_if_exists(defaults, "metode_pemilihan", clean_text(row.get("Metode Pemilihan")))
        self.set_if_exists(defaults, "metode_pengadaan", clean_text(row.get("Metode Pengadaan")))
        self.set_if_exists(defaults, "metode_evaluasi", clean_text(row.get("Metode Evaluasi")))
        self.set_if_exists(defaults, "cara_pembayaran", clean_text(row.get("Cara Pembayaran")))
        self.set_if_exists(defaults, "jenis_penetapan_pemenang", clean_text(row.get("Jenis Penetapan Pemenang")))
        self.set_if_exists(defaults, "kode_rup", instansi_satker["rup_id"])
        self.set_if_exists(defaults, "instansi", instansi_satker["nama_instansi"])
        self.set_if_exists(defaults, "klpd_instansi", instansi_satker["nama_instansi"])
        self.set_if_exists(defaults, "satuankerja", instansi_satker["stk_nama"])
        self.set_if_exists(defaults, "jenis_instansi", instansi_satker["jenis_instansi"])
        self.set_if_exists(defaults, "sumber_dana", anggaran["sbd_id"])
        self.set_if_exists(defaults, "tahun_anggaran", tahun_anggaran)
        self.set_if_exists(defaults, "lokasi_pekerjaan", extract_lokasi(row.get("lokasi_paket")))
        self.set_if_exists(defaults, "peserta_count", parse_number(row.get("Jumlah Pendaftar")))
        self.set_if_exists(defaults, "jumlah_penawar", parse_number(row.get("Jumlah Penawar")))
        self.set_if_exists(defaults, "jumlah_kirim_kualifikasi", parse_number(row.get("jumlah_kirim_kualifikasi")))
        self.set_if_exists(defaults, "durasi_tender", parse_number(row.get("Durasi Tender")))
        self.set_if_exists(defaults, "versi_spse", clean_text(row.get("Versi_spse_paket")))
        self.set_if_exists(defaults, "jadwal_pengumuman_json", row.get("jadwal_pengumuman"))
        self.set_if_exists(defaults, "jadwal_penawaran_json", row.get("jadwal_penawaran"))

        if model_has_field(Tender, "raw_data"):
            self.set_if_exists(defaults, "raw_data", row)
        elif model_has_field(Tender, "detail_json"):
            self.set_if_exists(defaults, "detail_json", row)
        self.set_if_exists(defaults, "data_source", Tender.SOURCE_LKPP_API)

        # TenderUmumPublik does not provide a real detail URL. Keep existing detail_url
        # and lpse_detail_url untouched; new rows use the model default blank URL.

        _, created = Tender.objects.update_or_create(
            kode_tender=kode_tender,
            defaults=defaults,
        )
        return "created" if created else "updated"

    def set_if_exists(self, defaults, field_name, value):
        if not model_has_field(Tender, field_name):
            return
        if value in (None, ""):
            return
        defaults[field_name] = value
