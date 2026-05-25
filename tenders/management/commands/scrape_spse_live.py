import json
import platform
import random
import re
import subprocess
import time
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from django.db.models import Q
from django.utils.dateparse import parse_date as django_parse_date

from tenders.models import Tender


BASE_URL = "https://spse.inaproc.id"
DEFAULT_PAGE_LENGTH = 25
DEFAULT_SLEEP_MIN_SECONDS = 1
DEFAULT_SLEEP_MAX_SECONDS = 3
REQUEST_TIMEOUT_SECONDS = 60
MAX_RETRIES = 3
TOKEN_RE = re.compile(r"authenticityToken\s*=\s*['\"]([^'\"]+)['\"]")
EXCLUDED_SLUGS = {"latihan", "dpd"}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def model_has_field(model, field_name):
    try:
        model._meta.get_field(field_name)
        return True
    except Exception:
        return False


def set_if_exists(defaults, field_name, value):
    if not model_has_field(Tender, field_name):
        return
    if value in (None, ""):
        return
    defaults[field_name] = value


def clean_html(value):
    if value in (None, ""):
        return ""

    text = str(value)
    if "<" not in text:
        return re.sub(r"\s+", " ", unescape(text)).strip()

    soup = BeautifulSoup(text, "html.parser")
    for span in soup.find_all("span"):
        span.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def clean_html_text(value):
    return clean_html(value)


def parse_jenis_pengadaan_tahun(value):
    text = clean_html(value)
    if not text:
        return "", ""

    years = re.findall(r"\b(20\d{2}|19\d{2})\b", text)
    tahun_anggaran = years[-1] if years else ""
    jenis_pengadaan = re.sub(r"\s*-\s*TA\s*[\d,\s]+", "", text, flags=re.IGNORECASE).strip()
    return jenis_pengadaan, tahun_anggaran


def parse_year_and_type(value):
    return parse_jenis_pengadaan_tahun(value)


def parse_money(value):
    text = clean_html(value)
    if not text or "belum dibuat" in text.lower():
        return None

    normalized = text.lower().replace("rp.", "").replace("rp", "").strip()
    multiplier = 1

    if re.search(r"(?<![a-z])jt(?![a-z])|juta", normalized):
        multiplier = 1_000_000
        normalized = re.sub(r"(?<![a-z])jt(?![a-z])|juta", "", normalized).strip()
    elif re.search(r"(?<![a-z])m(?![a-z])|miliar|milyar", normalized):
        multiplier = 1_000_000_000
        normalized = re.sub(r"(?<![a-z])m(?![a-z])|miliar|milyar", "", normalized).strip()

    normalized = re.sub(r"[^\d,.\-]", "", normalized)
    if not normalized or normalized == "-":
        return None

    if multiplier > 1:
        number_text = normalized.replace(".", "").replace(",", ".")
        try:
            return int(float(number_text) * multiplier)
        except ValueError:
            return None

    if "," in normalized and "." in normalized:
        number_text = normalized.replace(".", "").split(",", 1)[0]
    elif "," in normalized:
        left, right = normalized.rsplit(",", 1)
        if len(right) == 2:
            number_text = left.replace(".", "")
        else:
            number_text = normalized.replace(",", "")
    else:
        number_text = normalized.replace(".", "")

    try:
        return int(number_text)
    except ValueError:
        return None


def parse_rupiah(value):
    return parse_money(value)


def parse_int(value):
    text = clean_html(value)
    if not text:
        return None

    digits = re.sub(r"[^\d-]", "", text)
    if not digits or digits == "-":
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def parse_peserta_count(value):
    return parse_int(value)


def normalize_status(tahapan):
    text = tahapan.lower()
    if "tender batal" in text:
        return "FAILED"
    if "tender sudah selesai" in text:
        return "FINISH"
    if "surat penunjukan" in text:
        return "FINISH"
    if "penetapan pemenang" in text:
        return "ONGOING"
    if "download dokumen" in text:
        return "OPEN"
    if "pengumuman" in text:
        return "OPEN"
    if "tidak ada jadwal" in text:
        return "ONGOING"
    return "ONGOING"


def normalize_status_from_tahapan(value):
    return normalize_status(clean_html_text(value))


def parse_indonesian_date(value):
    text = clean_html_text(value)
    if not text:
        return None

    parsed = django_parse_date(text)
    if parsed:
        return parsed

    bulan_map = {
        "januari": "January",
        "februari": "February",
        "maret": "March",
        "april": "April",
        "mei": "May",
        "juni": "June",
        "juli": "July",
        "agustus": "August",
        "september": "September",
        "oktober": "October",
        "november": "November",
        "desember": "December",
    }
    normalized = text.lower()
    for indo, english in bulan_map.items():
        normalized = normalized.replace(indo, english)

    for date_format in ("%d %B %Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(normalized, date_format).date()
        except ValueError:
            continue
    return None


def build_detail_url(slug, kode_tender):
    return f"{BASE_URL}/{slug}/lelang/{kode_tender}/pengumumanlelang"


def absolute_url(base_url, href):
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return f"{BASE_URL}{href}"
    return f"{base_url.rstrip('/')}/{href}"


def parse_year(value):
    match = re.search(r"\b(\d{4})\b", clean_html_text(value))
    return match.group(1) if match else clean_html_text(value)


def merge_json_value(existing, key, value):
    if isinstance(existing, dict):
        merged = existing.copy()
    elif existing:
        merged = {"previous": existing}
    else:
        merged = {}
    merged[key] = value
    return merged


def clean_lpse_mapping_name(value, slug):
    name = clean_html_text(value) or slug
    if ">" in name:
        name = name.rsplit(">", 1)[-1].strip()
    return name or slug


def fetch_detail_html(session, detail_url):
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                detail_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={"Referer": detail_url.rsplit("/", 2)[0]},
            )
            response.raise_for_status()
            if "Akses Ditolak" in response.text:
                raise CommandError("detail page returned Akses Ditolak")
            return response.text
        except (requests.RequestException, CommandError) as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(attempt)
    raise CommandError(f"detail request failed after {MAX_RETRIES} attempts: {last_error}")


def parse_detail_html(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    parsed = {"detail_url": base_url, "labels": {}}

    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if len(cells) < 2:
            continue

        label = clean_html_text(cells[0].get_text(" ", strip=True))
        if not label:
            continue

        if label == "Nilai Pagu Paket" and len(cells) >= 4:
            parsed["nilai_pagu"] = parse_rupiah(cells[1].get_text(" ", strip=True))
            parsed["nilai_hps"] = parse_rupiah(cells[3].get_text(" ", strip=True))
            parsed["labels"]["Nilai Pagu Paket"] = clean_html_text(cells[1].get_text(" ", strip=True))
            parsed["labels"]["Nilai HPS Paket"] = clean_html_text(cells[3].get_text(" ", strip=True))
            continue

        value_cell = cells[1]
        value_text = clean_html_text(value_cell.get_text(" ", strip=True))
        parsed["labels"][label] = value_text

        if label == "Kode Tender":
            parsed["kode_tender"] = value_text
        elif label == "Nama Tender":
            parsed["nama_paket"] = value_text
        elif label == "Rencana Umum Pengadaan":
            parsed.update(parse_rup_table(value_cell))
        elif label == "Uraian Singkat Pekerjaan":
            link = value_cell.find("a", href=True)
            if link:
                parsed["uraian_pekerjaan"] = absolute_url(base_url, link["href"])
                parsed["uraian_pekerjaan_nama_file"] = clean_html_text(link.get_text(" ", strip=True))
            else:
                parsed["uraian_pekerjaan_nama_file"] = value_text
        elif label == "Tanggal Pembuatan":
            parsed["tanggal_pembuatan"] = parse_indonesian_date(value_text)
        elif label == "Tahap Tender Saat Ini":
            parsed["tahapan"] = value_text
            parsed["status"] = normalize_status_from_tahapan(value_text)
        elif label == "K/L/PD/Instansi Lainnya":
            parsed["klpd_instansi"] = value_text
            parsed["instansi"] = value_text
        elif label == "Satuan Kerja":
            parsed["satuankerja"] = value_text
        elif label == "Jenis Pengadaan":
            parsed["jenis_pengadaan"] = value_text
        elif label == "Metode Pengadaan":
            parsed["metode_pengadaan"] = value_text
        elif label == "Tahun Anggaran":
            parsed["tahun_anggaran"] = parse_year(value_text)
        elif label == "Jenis Kontrak":
            parsed["jenis_kontrak"] = value_text
        elif label == "Lokasi Pekerjaan":
            locations = [
                clean_html_text(li.get_text(" ", strip=True))
                for li in value_cell.find_all("li")
                if clean_html_text(li.get_text(" ", strip=True))
            ]
            parsed["lokasi_pekerjaan"] = "; ".join(locations) if locations else value_text
        elif label == "Syarat Kualifikasi":
            parsed["syarat_kualifikasi"] = value_text
        elif label == "Peserta Tender":
            parsed["peserta_count"] = parse_peserta_count(value_text)

    return parsed


def parse_rup_table(value_cell):
    result = {}
    table = value_cell.find("table")
    if not table:
        return result

    rows = table.find_all("tr")
    if len(rows) < 2:
        return result

    headers = [clean_html_text(cell.get_text(" ", strip=True)) for cell in rows[0].find_all(["th", "td"])]
    values = [clean_html_text(cell.get_text(" ", strip=True)) for cell in rows[1].find_all(["th", "td"])]
    row = dict(zip(headers, values))

    result["kode_rup"] = row.get("Kode RUP", "")
    result["nama_paket_rup"] = row.get("Nama Paket", "")
    result["sumber_dana"] = row.get("Sumber Dana", "")
    return result


def apply_detail_to_tender(tender, parsed):
    defaults = {}
    set_if_exists(defaults, "nama_paket", parsed.get("nama_paket"))
    set_if_exists(defaults, "tanggal_pembuatan", parsed.get("tanggal_pembuatan"))
    set_if_exists(defaults, "tahapan", parsed.get("tahapan"))
    set_if_exists(defaults, "status", parsed.get("status"))
    set_if_exists(defaults, "klpd_instansi", parsed.get("klpd_instansi"))
    set_if_exists(defaults, "instansi", parsed.get("instansi"))
    set_if_exists(defaults, "satuankerja", parsed.get("satuankerja"))
    set_if_exists(defaults, "jenis_pengadaan", parsed.get("jenis_pengadaan"))
    set_if_exists(defaults, "metode_pengadaan", parsed.get("metode_pengadaan"))
    set_if_exists(defaults, "tahun_anggaran", parsed.get("tahun_anggaran"))
    set_if_exists(defaults, "nilai_pagu", parsed.get("nilai_pagu"))
    set_if_exists(defaults, "nilai_hps", parsed.get("nilai_hps"))
    set_if_exists(defaults, "jenis_kontrak", parsed.get("jenis_kontrak"))
    set_if_exists(defaults, "lokasi_pekerjaan", parsed.get("lokasi_pekerjaan"))
    set_if_exists(defaults, "peserta_count", parsed.get("peserta_count"))
    set_if_exists(defaults, "kode_rup", parsed.get("kode_rup"))
    set_if_exists(defaults, "nama_paket_rup", parsed.get("nama_paket_rup"))
    set_if_exists(defaults, "sumber_dana", parsed.get("sumber_dana"))
    set_if_exists(defaults, "uraian_pekerjaan", parsed.get("uraian_pekerjaan"))
    set_if_exists(defaults, "uraian_pekerjaan_nama_file", parsed.get("uraian_pekerjaan_nama_file"))

    if not tender.detail_url:
        set_if_exists(defaults, "detail_url", parsed.get("detail_url"))
    set_if_exists(defaults, "lpse_detail_url", parsed.get("detail_url"))

    detail_payload = {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in parsed.items()
        if key != "labels"
    }
    detail_payload["labels"] = parsed.get("labels", {})

    if model_has_field(Tender, "detail_json"):
        defaults["detail_json"] = merge_json_value(getattr(tender, "detail_json", None), "spse_detail", detail_payload)
    elif model_has_field(Tender, "raw_data"):
        defaults["raw_data"] = merge_json_value(getattr(tender, "raw_data", None), "spse_detail", detail_payload)

    for field_name, value in defaults.items():
        setattr(tender, field_name, value)
    tender.save(update_fields=list(defaults.keys()) + ["updated_at"])


class Command(BaseCommand):
    help = "Scrape live SPSE INAPROC tenders using the frontend DataTables endpoint"

    def add_arguments(self, parser):
        parser.add_argument("--slug", help="Single SPSE slug, for example pertanian")
        parser.add_argument("--all-slugs", action="store_true", help="Scrape every slug in tenders/data/lpse_slug_mapping.json")
        parser.add_argument("--kode-tender", help="Enrich one existing tender by kode_tender")

        parser.add_argument("--tahun", type=int, help="Tender year, for example 2026")
        parser.add_argument("--max-pages", type=int, help="Maximum DataTables pages per slug")
        parser.add_argument("--limit-slugs", type=int, help="Limit number of slugs when using --all-slugs")
        parser.add_argument("--offset-slugs", type=int, default=0, help="Skip this many slugs when using --all-slugs")
        parser.add_argument("--sleep-min", type=float, default=DEFAULT_SLEEP_MIN_SECONDS, help="Minimum random sleep between pages and slugs")
        parser.add_argument("--sleep-max", type=float, default=DEFAULT_SLEEP_MAX_SECONDS, help="Maximum random sleep between pages and slugs")
        parser.add_argument("--length", type=int, default=DEFAULT_PAGE_LENGTH, help="DataTables page length")
        parser.add_argument("--enrich-detail", action="store_true", help="Fetch each tender detail page after list scrape")
        parser.add_argument("--detail-only", action="store_true", help="Enrich existing Tender rows without scraping DataTables")
        parser.add_argument("--limit-details", type=int, help="Limit detail enrichment count")
        parser.add_argument("--browser-session", action="store_true", help="Warm requests session with undetected headless Chrome before scraping each slug")

    def handle(self, *args, **options):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

        slug_mapping = self.load_slug_mapping()
        self.validate_options(options)
        tahun = options.get("tahun")
        max_pages = options.get("max_pages")
        length = options["length"]
        sleep_min = options["sleep_min"]
        sleep_max = options["sleep_max"]
        self.browser_session_enabled = options.get("browser_session")

        if length <= 0:
            raise CommandError("--length must be greater than 0")
        if length > 100:
            self.stderr.write(self.style.WARNING("Warning: --length > 100 may be unstable on SPSE DataTables endpoints"))
        if sleep_min < 0 or sleep_max < 0:
            raise CommandError("--sleep-min and --sleep-max must be zero or greater")
        if sleep_min > sleep_max:
            raise CommandError("--sleep-min cannot be greater than --sleep-max")

        if options.get("kode_tender"):
            created, updated, skipped, failed = self.enrich_single_kode(
                options["kode_tender"],
                options.get("slug"),
                sleep_min,
                sleep_max,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"TOTAL slugs_processed=0 created={created} updated={updated} "
                    f"skipped={skipped} failed={failed}"
                )
            )
            return

        if options.get("detail_only"):
            created, updated, skipped, failed = self.enrich_existing_details(
                options["slug"],
                tahun,
                options.get("limit_details"),
                sleep_min,
                sleep_max,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"TOTAL slugs_processed=1 created={created} updated={updated} "
                    f"skipped={skipped} failed={failed}"
                )
            )
            return

        slugs = self.resolve_slugs(options, slug_mapping)

        total_created = 0
        total_updated = 0
        total_skipped = 0
        total_failed = 0
        failed_slugs = []

        for slug in slugs:
            lpse_name = slug_mapping.get(slug, slug)
            created, updated, skipped, failed = self.scrape_slug(
                slug,
                lpse_name,
                tahun,
                max_pages,
                length,
                sleep_min,
                sleep_max,
                options.get("enrich_detail"),
                options.get("limit_details"),
                self.browser_session_enabled,
            )
            total_created += created
            total_updated += updated
            total_skipped += skipped
            total_failed += failed
            if failed:
                failed_slugs.append(slug)
            time.sleep(random.uniform(sleep_min, sleep_max))

        self.stdout.write(
            self.style.SUCCESS(
                f"TOTAL slugs_processed={len(slugs)} created={total_created} "
                f"updated={total_updated} skipped={total_skipped} failed={total_failed}"
            )
        )
        if failed_slugs:
            self.stderr.write(self.style.WARNING(f"FAILED_SLUGS {', '.join(failed_slugs)}"))

    def validate_options(self, options):
        if options.get("kode_tender"):
            if options.get("all_slugs"):
                raise CommandError("--kode-tender cannot be combined with --all-slugs")
            if not options.get("enrich_detail"):
                raise CommandError("--kode-tender requires --enrich-detail")
            return

        if options.get("detail_only"):
            if options.get("all_slugs"):
                raise CommandError("--detail-only currently requires --slug, not --all-slugs")
            if not options.get("slug") or not options.get("tahun"):
                raise CommandError("--detail-only requires --slug and --tahun")
            return

        if bool(options.get("slug")) == bool(options.get("all_slugs")):
            raise CommandError("Use exactly one of --slug or --all-slugs")
        if not options.get("tahun"):
            raise CommandError("--tahun is required for list scraping")

    def resolve_slugs(self, options, slug_mapping):
        if options.get("slug"):
            return [options["slug"].strip()]

        if not slug_mapping:
            raise CommandError("--all-slugs requires tenders/data/lpse_slug_mapping.json")

        slugs = list(slug_mapping.keys())
        offset = options.get("offset_slugs") or 0
        limit = options.get("limit_slugs")
        if offset < 0:
            raise CommandError("--offset-slugs must be zero or greater")
        if limit is not None and limit < 0:
            raise CommandError("--limit-slugs must be zero or greater")

        slugs = slugs[offset:]
        if limit is not None:
            slugs = slugs[:limit]
        return slugs

    def load_slug_mapping(self):
        mapping_path = Path(__file__).resolve().parents[2] / "data" / "lpse_slug_mapping.json"
        if not mapping_path.exists():
            return {}

        with mapping_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        if isinstance(data, dict):
            mapping = {}
            for slug, name in data.items():
                slug = str(slug).strip()
                if slug and slug not in EXCLUDED_SLUGS and slug not in mapping:
                    mapping[slug] = clean_lpse_mapping_name(name, slug)
            return mapping

        if isinstance(data, list):
            mapping = {}
            for item in data:
                if not isinstance(item, dict):
                    continue
                slug = item.get("slug") or item.get("lpse_slug")
                name = item.get("name") or item.get("lpse_name") or item.get("nama_lpse")
                slug = str(slug).strip() if slug else ""
                if slug and slug not in EXCLUDED_SLUGS and slug not in mapping:
                    mapping[slug] = clean_lpse_mapping_name(name, slug)
            return mapping

        return {}

    def scrape_slug(self, slug, lpse_name, tahun, max_pages, length, sleep_min, sleep_max, enrich_detail=False, limit_details=None, browser_session=False):
        self.stdout.write(f"START slug={slug} tahun={tahun}")
        list_url = self.build_list_url(slug, tahun)
        try:
            if browser_session:
                token = self.browser_warmup(slug, list_url)
            else:
                token = self.fetch_authenticity_token(list_url, slug=slug)
        except Exception as exc:
            self.stderr.write(self.style.WARNING(f"Failed slug={slug}: {exc}"))
            return 0, 0, 0, 1

        created = 0
        updated = 0
        skipped = 0
        failed = 0
        detail_count = 0
        previous_first_code = None
        seen_page_codes = set()
        page = 1
        start = 0

        while True:
            if max_pages and page > max_pages:
                break

            self.stdout.write(f"Fetching slug={slug} tahun={tahun} page={page} start={start}")

            try:
                payload = self.fetch_datatables_page(slug, tahun, list_url, token, page, start, length)
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.WARNING(f"Failed slug={slug} page={page}: {exc}"))
                break

            rows = payload.get("data") if isinstance(payload, dict) else None
            if not rows:
                break

            page_codes = self.extract_page_codes(rows)
            first_code = page_codes[0] if page_codes else ""
            if first_code and first_code == previous_first_code:
                self.stderr.write(self.style.WARNING(f"Repeated consecutive first tender code detected: {first_code}"))
                break
            if page_codes in seen_page_codes:
                self.stderr.write(self.style.WARNING("Repeated page tender code tuple detected"))
                break

            previous_first_code = first_code
            seen_page_codes.add(page_codes)
            page_created = 0
            page_updated = 0
            page_skipped = 0
            page_failed = 0

            for row in rows:
                try:
                    result = self.upsert_row(row, slug, lpse_name)
                except DatabaseError as exc:
                    failed += 1
                    page_failed += 1
                    self.stderr.write(self.style.WARNING(f"Database row failed: {exc}"))
                    continue
                except Exception as exc:
                    failed += 1
                    page_failed += 1
                    self.stderr.write(self.style.WARNING(f"Row failed: {exc}"))
                    continue

                if result == "created":
                    created += 1
                    page_created += 1
                elif result == "updated":
                    updated += 1
                    page_updated += 1
                else:
                    skipped += 1
                    page_skipped += 1

                if enrich_detail and result in {"created", "updated"}:
                    if limit_details is None or detail_count < limit_details:
                        kode_tender = clean_html(row[0])
                        detail_result = self.enrich_tender_by_kode(kode_tender, slug, sleep_min, sleep_max)
                        detail_count += 1
                        if detail_result == "failed":
                            failed += 1
                            page_failed += 1
                        elif detail_result == "skipped":
                            skipped += 1
                            page_skipped += 1

            page += 1
            self.stdout.write(
                f"PAGE slug={slug} start={start} count={len(rows)} "
                f"created={page_created} updated={page_updated} "
                f"skipped={page_skipped} failed={page_failed}"
            )
            start += length
            time.sleep(random.uniform(sleep_min, sleep_max))

        self.stdout.write(
            f"DONE slug={slug} pages={page - 1} created={created} "
            f"updated={updated} skipped={skipped} failed={failed}"
        )
        return created, updated, skipped, failed

    def extract_page_codes(self, rows):
        codes = []
        for row in rows:
            if isinstance(row, list) and row:
                codes.append(clean_html(row[0]))
            else:
                codes.append("")
        return tuple(codes)

    def build_list_url(self, slug, tahun):
        query = urlencode(
            {
                "kategoriId": "",
                "tahun": tahun,
                "instansiId": "",
                "rekanan": "",
                "kontrak_status": "",
                "kontrak_tipe": "",
            }
        )
        return f"{BASE_URL}/{slug}/lelang?{query}"

    def build_dt_url(self, slug, tahun):
        query = urlencode({"rekanan": "", "tahun": tahun, "instansiId": ""})
        return f"{BASE_URL}/{slug}/dt/lelang?{query}"

    def fetch_authenticity_token(self, list_url, slug=""):
        self.stdout.write(f"GET {list_url}")
        response = self.request_with_retry("GET", list_url)
        match = TOKEN_RE.search(response.text)
        if not match:
            raise CommandError("authenticityToken not found on list page")
        self.stdout.write("Extracted authenticityToken")
        return match.group(1)

    def browser_warmup(self, slug, list_url):
        self.stdout.write(f"BROWSER WARMUP slug={slug}")
        try:
            import undetected_chromedriver as uc
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError as exc:
            raise CommandError(
                "Browser session requires undetected-chromedriver and selenium. "
                "Install requirements.txt first."
            ) from exc

        options = uc.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1365,900")
        options.add_argument("--lang=id-ID,id,en-US,en")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--user-agent={USER_AGENT}")

        driver = None
        try:
            chrome_major = self.get_chrome_major_version()
            driver_kwargs = {"options": options, "use_subprocess": True}
            if chrome_major:
                driver_kwargs["version_main"] = chrome_major
            driver = uc.Chrome(**driver_kwargs)
            driver.execute_cdp_cmd("Network.setUserAgentOverride", {
                "userAgent": USER_AGENT,
                "acceptLanguage": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
                "platform": "Windows",
            })
            driver.set_window_size(1365, 900)
            driver.get(list_url)

            WebDriverWait(driver, 30).until(
                lambda browser: browser.execute_script("return document.readyState") == "complete"
            )
            WebDriverWait(driver, 30).until(
                lambda browser: TOKEN_RE.search(browser.page_source)
            )

            page_source = driver.page_source
            token_match = TOKEN_RE.search(page_source)
            if not token_match:
                raise CommandError("authenticityToken not found after browser warm-up")

            user_agent = driver.execute_script("return navigator.userAgent") or USER_AGENT
            self.session.headers.update({
                "User-Agent": user_agent,
                "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            })

            for cookie in driver.get_cookies():
                self.session.cookies.set(
                    cookie.get("name"),
                    cookie.get("value"),
                    domain=cookie.get("domain"),
                    path=cookie.get("path") or "/",
                )

            self.stdout.write(f"SESSION READY slug={slug}")
            self.stdout.write("USING REQUESTS SESSION")
            return token_match.group(1)
        finally:
            if driver:
                driver.quit()

    def get_chrome_major_version(self):
        commands = []
        if platform.system() == "Windows":
            commands = [
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-Item 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe').VersionInfo.ProductVersion",
                ],
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-Item 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe').VersionInfo.ProductVersion",
                ],
            ]
        else:
            commands = [
                ["google-chrome", "--version"],
                ["google-chrome-stable", "--version"],
                ["chromium-browser", "--version"],
                ["chromium", "--version"],
            ]

        for command in commands:
            try:
                output = subprocess.check_output(command, stderr=subprocess.DEVNULL, text=True, timeout=10)
            except Exception:
                continue
            match = re.search(r"(\d+)\.", output)
            if match:
                return int(match.group(1))
        return None

    def fetch_datatables_page(self, slug, tahun, list_url, token, draw, start, length):
        dt_url = self.build_dt_url(slug, tahun)
        headers = {
            "Referer": list_url,
            "Origin": BASE_URL,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "draw": draw,
            "start": start,
            "length": length,
            "authenticityToken": token,
        }
        self.stdout.write(f"POST {dt_url}")
        response = self.request_with_retry("POST", dt_url, headers=headers, data=data)
        return response.json()

    def enrich_single_kode(self, kode_tender, slug, sleep_min, sleep_max):
        result = self.enrich_tender_by_kode(kode_tender, slug, sleep_min, sleep_max)
        if result == "updated":
            return 0, 1, 0, 0
        if result == "skipped":
            return 0, 0, 1, 0
        return 0, 0, 0, 1

    def enrich_tender_by_kode(self, kode_tender, slug, sleep_min, sleep_max):
        tender = Tender.objects.filter(kode_tender=str(kode_tender)).first()
        if not tender:
            self.stderr.write(self.style.WARNING(f"Tender kode_tender={kode_tender} not found"))
            return "failed"
        return self.enrich_tender_detail(tender, slug, sleep_min, sleep_max)

    def enrich_existing_details(self, slug, tahun, limit_details, sleep_min, sleep_max):
        queryset = Tender.objects.all()
        if model_has_field(Tender, "tahun_anggaran"):
            queryset = queryset.filter(tahun_anggaran=str(tahun))

        slug_filter = Q(detail_url__icontains=f"/{slug}/") | Q(lpse_detail_url__icontains=f"/{slug}/")
        if model_has_field(Tender, "lpse_slug"):
            slug_filter |= Q(lpse_slug=slug)
        queryset = queryset.filter(slug_filter).order_by("id")

        if limit_details:
            queryset = queryset[:limit_details]

        updated = 0
        skipped = 0
        failed = 0
        for tender in queryset:
            result = self.enrich_tender_detail(tender, slug, sleep_min, sleep_max)
            if result == "updated":
                updated += 1
            elif result == "skipped":
                skipped += 1
            else:
                failed += 1
        return 0, updated, skipped, failed

    def enrich_tender_detail(self, tender, slug, sleep_min, sleep_max):
        detail_url = tender.detail_url or tender.lpse_detail_url
        if not detail_url:
            if not slug:
                self.stderr.write(self.style.WARNING(f"Detail skipped kode_tender={tender.kode_tender}: missing slug/detail_url"))
                return "skipped"
            detail_url = build_detail_url(slug, tender.kode_tender)

        slug = slug or self.extract_slug_from_detail_url(detail_url)
        if slug:
            self.warm_detail_session(slug)

        self.stdout.write(f"DETAIL kode_tender={tender.kode_tender} url={detail_url}")
        try:
            html = fetch_detail_html(self.session, detail_url)
            parsed = parse_detail_html(html, detail_url)
            apply_detail_to_tender(tender, parsed)
        except Exception as exc:
            self.stderr.write(self.style.WARNING(f"Detail failed kode_tender={tender.kode_tender}: {exc}"))
            return "failed"

        time.sleep(random.uniform(max(0.5, sleep_min), max(1.5, sleep_max)))
        return "updated"

    def warm_detail_session(self, slug):
        try:
            self.session.get(f"{BASE_URL}/{slug}/lelang", timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException:
            pass

    def extract_slug_from_detail_url(self, detail_url):
        match = re.search(r"spse\.inaproc\.id/([^/]+)/lelang/", detail_url or "")
        return match.group(1) if match else ""

    def request_with_retry(self, method, url, **kwargs):
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.session.request(method, url, timeout=REQUEST_TIMEOUT_SECONDS, **kwargs)
                response.raise_for_status()
                return response
            except requests.HTTPError as exc:
                last_error = exc
                status_code = exc.response.status_code if exc.response is not None else None
                if (
                    status_code == 403
                    and getattr(self, "browser_session_enabled", False)
                    and not getattr(self, "_browser_fallback_running", False)
                ):
                    slug = self.extract_slug_from_list_or_detail_url(url)
                    if slug:
                        self._browser_fallback_running = True
                        try:
                            self.browser_warmup(slug, self.build_list_url(slug, self.extract_year_from_url(url)))
                        finally:
                            self._browser_fallback_running = False
                        continue
                if attempt < MAX_RETRIES:
                    time.sleep(attempt)
            except requests.RequestException as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    time.sleep(attempt)

        raise CommandError(f"{method} {url} failed after {MAX_RETRIES} attempts: {last_error}")

    def extract_slug_from_list_or_detail_url(self, url):
        match = re.search(r"spse\.inaproc\.id/([^/]+)/(?:lelang|dt/lelang)", url or "")
        return match.group(1) if match else ""

    def extract_year_from_url(self, url):
        match = re.search(r"[?&]tahun=(\d{4})", url or "")
        return int(match.group(1)) if match else ""

    def upsert_row(self, row, slug, lpse_name):
        if not isinstance(row, list) or len(row) < 11:
            return "skipped"

        kode_tender = clean_html(row[0])
        if not kode_tender:
            return "skipped"

        nama_paket = clean_html(row[1])
        klpd_instansi = clean_html(row[2])
        tahapan = clean_html(row[3])
        nilai_hps = parse_money(row[4])
        metode_pengadaan = clean_html(row[5])
        metode_pemilihan = clean_html(row[6])
        metode_evaluasi = clean_html(row[7])
        jenis_pengadaan, tahun_anggaran = parse_jenis_pengadaan_tahun(row[8])
        nilai_kontrak = parse_money(row[10])
        detail_url = f"{BASE_URL}/{slug}/lelang/{kode_tender}/pengumumanlelang"

        defaults = {}
        self.set_if_exists(defaults, "nama_paket", nama_paket)
        self.set_if_exists(defaults, "instansi", klpd_instansi)
        self.set_if_exists(defaults, "klpd_instansi", klpd_instansi)
        self.set_if_exists(defaults, "tahapan", tahapan)
        self.set_if_exists(defaults, "status", normalize_status(tahapan))
        self.set_if_exists(defaults, "nilai_hps", nilai_hps)
        self.set_if_exists(defaults, "jenis_pengadaan", jenis_pengadaan)
        self.set_if_exists(defaults, "metode_pengadaan", metode_pengadaan)
        self.set_if_exists(defaults, "metode_pemilihan", metode_pemilihan)
        self.set_if_exists(defaults, "metode_evaluasi", metode_evaluasi)
        self.set_if_exists(defaults, "tahun_anggaran", tahun_anggaran)
        self.set_if_exists(defaults, "lpse_slug", slug)
        self.set_if_exists(defaults, "lpse_name", lpse_name or slug)
        self.set_if_exists(defaults, "lpse_detail_url", detail_url)
        self.set_if_exists(defaults, "nilai_kontrak", nilai_kontrak)

        raw_data = {
            "source": "spse_inaproc_datatables",
            "slug": slug,
            "detail_url": detail_url,
            "spse_list_unknown": {
                "row_9": row[9] if len(row) > 9 else None,
                "row_11": row[11] if len(row) > 11 else None,
                "row_12": row[12] if len(row) > 12 else None,
                "row_13": row[13] if len(row) > 13 else None,
                "row_14": row[14] if len(row) > 14 else None,
                "row_15": row[15] if len(row) > 15 else None,
            },
            "row": row,
        }
        tender = Tender.objects.filter(kode_tender=kode_tender).first()
        if model_has_field(Tender, "raw_data"):
            existing_raw = getattr(tender, "raw_data", None) if tender else None
            self.set_if_exists(defaults, "raw_data", merge_json_value(existing_raw, "spse_list", raw_data))
        elif model_has_field(Tender, "detail_json"):
            existing_detail = getattr(tender, "detail_json", None) if tender else None
            self.set_if_exists(defaults, "detail_json", merge_json_value(existing_detail, "spse_list", raw_data))

        if tender and tender.detail_url:
            obj, created = Tender.objects.update_or_create(kode_tender=kode_tender, defaults=defaults)
        else:
            self.set_if_exists(defaults, "detail_url", detail_url)
            obj, created = Tender.objects.update_or_create(kode_tender=kode_tender, defaults=defaults)

        return "created" if created else "updated"

    def set_if_exists(self, defaults, field_name, value):
        if not model_has_field(Tender, field_name):
            return
        if value in (None, ""):
            return
        defaults[field_name] = value
