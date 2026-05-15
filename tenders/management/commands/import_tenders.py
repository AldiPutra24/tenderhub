import json
import pandas as pd
from datetime import datetime

from django.core.management.base import BaseCommand
from tenders.models import Tender


def clean_value(value, default=""):
    if pd.isna(value):
        return default
    return value


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def clean_num(value):
    if pd.isna(value) or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def clean_int(value):
    if pd.isna(value) or value == "":
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def clean_json(value):
    if pd.isna(value) or value == "":
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {"raw": str(value)}

def clean_date(value):
    if pd.isna(value) or value == "":
        return None

    if isinstance(value, datetime):
        return value.date()

    value = str(value).strip()

    bulan_map = {
        "Januari": "January",
        "Februari": "February",
        "Maret": "March",
        "April": "April",
        "Mei": "May",
        "Juni": "June",
        "Juli": "July",
        "Agustus": "August",
        "September": "September",
        "Oktober": "October",
        "November": "November",
        "Desember": "December",
    }

    for indo, eng in bulan_map.items():
        value = value.replace(indo, eng)

    try:
        return datetime.strptime(value, "%d %B %Y").date()
    except Exception:
        return None

class Command(BaseCommand):
    help = "Import tender data from Excel or CSV"

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)

    def handle(self, *args, **options):
        file_path = options["file_path"]

        if file_path.endswith(".xlsx"):
            df = pd.read_excel(file_path)
        else:
            df = pd.read_csv(file_path)

        # penting: bersihkan spasi nama kolom
        df.columns = df.columns.str.strip()

        total = 0
        created_count = 0
        updated_count = 0

        for _, row in df.iterrows():
            kode = clean_text(row.get("Kode Tender") or row.get("Kode"))

            if not kode:
                continue

            tender, created = Tender.objects.update_or_create(
                kode_tender=kode,
                defaults={
                    "nama_paket": clean_text(row.get("Nama Paket")),
                    "instansi": clean_text(row.get("Instansi")),
                    "tahapan": clean_text(row.get("Tahapan")),
                    "status": clean_text(row.get("Status")),

                    "kode_rup": clean_text(row.get("Kode RUP")),
                    "nama_paket_rup": clean_text(row.get("Nama Paket RUP")),
                    "sumber_dana": clean_text(row.get("Sumber Dana")),

                    "uraian_pekerjaan": clean_text(row.get("Uraian Singkat Pekerjaan(pdf link)")),
                    "uraian_pekerjaan_nama_file": clean_text(row.get("Uraian Singkat Pekerjaan Nama File")),

                    "tanggal_pembuatan": clean_date(row.get("Tanggal Pembuatan")),

                    "satuankerja": clean_text(row.get("Satuan Kerja")),
                    "jenis_pengadaan": clean_text(row.get("Jenis Pengadaan")),
                    "metode_pengadaan": clean_text(row.get("Metode Pengadaan")),
                    "tahun_anggaran": clean_text(row.get("Tahun Anggaran")),

                    "nilai_pagu": clean_num(row.get("Nilai Pagu Num") or row.get("Nilai Pagu Paket")),
                    "nilai_hps": clean_num(row.get("Nilai HPS Num") or row.get("Nilai HPS Paket")),

                    "jenis_kontrak": clean_text(row.get("Jenis Kontrak")),
                    "lokasi_pekerjaan": clean_text(row.get("Lokasi Pekerjaan")),
                    "peserta_count": clean_int(row.get("Peserta Tender Count") or row.get("Peserta Tender")),

                    "detail_url": clean_text(row.get("Detail URL") or row.get("List Detail URL")),

                    # # jika model kamu punya JSONField ini
                    # "rup_json": clean_json(row.get("Rencana Umum Pengadaan JSON")),
                    # "syarat_kualifikasi_json": clean_json(row.get("Syarat Kualifikasi JSON")),
                    # "detail_json": clean_json(row.get("Detail JSON")),
                },
            )

            total += 1

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Import selesai: {total} tender | Baru: {created_count} | Update: {updated_count}"
            )
        )