import csv
import io
import json
import re
from datetime import date, datetime
from types import SimpleNamespace

import requests
from django.utils.dateparse import parse_date as django_parse_date
from django.utils.dateparse import parse_datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_URL = "https://data.inaproc.id"
SIGNATURE_PATH = "/dashboard-api/export/signature"
REALISASI_DATA_PATH = "/dashboard-api/realisasi/data"
REALISASI_EXPORT_PATH = "/dashboard-api/realisasi/export"
DETAIL_EXPORT_PATH = "/dashboard-api/realisasi/detail/export"
VALID_STATUS = ["BERLANGSUNG", "SELESAI"]
VALID_JENIS_KLPD = ["1", "2", "3", "4", "5"]
JENIS_KLPD_LABELS = {
    "1": "Kementerian",
    "2": "Lembaga",
    "3": "Provinsi",
    "4": "Kabupaten",
    "5": "Kota",
}
RETRY_STATUS_CODES = [429, 500, 502, 503, 504]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)
SEC_CH_UA = '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"'
ACCEPT_LANGUAGE = "id,en-US;q=0.9,en;q=0.8"

MAIN_CSV_MAPPING = {
    "Nama Instansi": "nama_instansi",
    "Nama Satuan Kerja": "nama_satuan_kerja",
    "Kode Paket": "kode_paket",
    "Kode RUP": "kode_rup",
    "Tahun Anggaran": "tahun_anggaran",
    "Sumber Transaksi": "sumber_transaksi",
    "Sumber Dana": "sumber_dana",
    "Nama Penyedia": "nama_penyedia",
    "Metode Pengadaan": "metode_pengadaan",
    "Jenis Pengadaan": "jenis_pengadaan",
    "Nama Paket": "nama_paket",
    "Status Paket": "status_paket",
    "Total Nilai (Rp)": "total_nilai",
    "Nilai PDN (Rp)": "nilai_pdn",
}

DETAIL_CSV_MAPPING = {
    "Nama Tender": "nama_tender",
    "Tanggal Tender": "tanggal_tender",
    "Kode Tender": "kode_tender",
    "Nilai HPS": "nilai_hps",
    "Nilai Pagu": "nilai_pagu",
    "Instansi": "instansi",
    "Kategori": "kategori",
    "Metode Tender": "metode_tender",
    "Tahun Anggaran": "tahun_anggaran",
    "Metode Evaluasi": "metode_evaluasi",
    "Cara Pembayaran": "cara_pembayaran",
    "Sumber Dana": "sumber_dana",
    "Lokasi Pekerjaan": "lokasi_pekerjaan",
    "Tautan Detail Tender": "detail_url",
    "Satuan Kerja": "satuan_kerja",
}

RUPIAH_FIELDS = {"total_nilai", "nilai_pdn", "nilai_hps", "nilai_pagu"}
DATE_FIELDS = {"tanggal_tender"}


class InaprocRequestError(Exception):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response


class InaprocForbiddenError(InaprocRequestError):
    pass


def clean_text(value):
    if value in (None, ""):
        return ""
    return str(value).strip()


def parse_rupiah(value):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip()
    if not text:
        return None

    text = re.sub(r"(?i)rp\.?", "", text)
    text = re.sub(r"\s+", "", text)
    negative = text.startswith("-")
    text = text.lstrip("-")

    if "," in text and "." in text:
        text = text.replace(".", "").split(",", 1)[0]
    elif "," in text:
        parts = text.split(",")
        if len(parts[-1]) == 2 and len(parts) == 2:
            text = parts[0]
        else:
            text = "".join(parts)
    else:
        text = text.replace(".", "")

    digits = re.sub(r"\D", "", text)
    if not digits:
        return None

    amount = int(digits)
    return -amount if negative else amount


def parse_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = clean_text(value)
    if not text:
        return None

    parsed_datetime = parse_datetime(text)
    if parsed_datetime:
        return parsed_datetime.date()

    parsed_date = django_parse_date(text)
    if parsed_date:
        return parsed_date

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
    for indonesia, english in bulan_map.items():
        normalized = normalized.replace(indonesia, english)

    for date_format in ("%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(normalized, date_format).date()
        except ValueError:
            continue
    return None


def normalize_status(value):
    status = clean_text(value).upper()
    if status not in VALID_STATUS:
        raise ValueError(f"Invalid status '{value}'. Valid status: {', '.join(VALID_STATUS)}")
    return status


class InaprocRealisasiClient:
    def __init__(
        self,
        session=None,
        timeout=30,
        retries=3,
        backoff_factor=1,
        referer_tahun=None,
        debug_callback=None,
    ):
        self.timeout = timeout
        self.session = session or requests.Session()
        self.referer_tahun = referer_tahun or date.today().year
        self.debug_callback = debug_callback
        self._warmed_referers = set()
        self._configure_retries(retries, backoff_factor)

    def _configure_retries(self, retries, backoff_factor):
        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=backoff_factor,
            status_forcelist=RETRY_STATUS_CODES,
            allowed_methods=frozenset(["GET", "POST"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get_signature(self, path, body):
        body_text = self._body_text(body)
        self.warmup_realisasi_page()
        request_body = {"path": path, "body": body_text}
        response = self.session.post(
            self._url(SIGNATURE_PATH),
            headers=self._signature_headers(),
            data=self._body_text(request_body).encode("utf-8"),
            timeout=self.timeout,
        )
        self._debug_response(
            "POST",
            self._url(SIGNATURE_PATH),
            response,
            request_body=self._body_text(request_body),
        )
        self._raise_for_status(response, "signature")
        signature = response.json()
        for key in ("time", "nonce", "signature"):
            if not signature.get(key):
                raise ValueError(f"Signature response missing '{key}'")
        return signature

    def warmup_realisasi_page(self, tahun=None):
        if tahun is not None:
            self.referer_tahun = tahun
        referer = self.realisasi_page_url()
        if referer in self._warmed_referers:
            return

        response = self.session.get(
            referer,
            headers=self._warmup_headers(),
            timeout=self.timeout,
        )
        self._debug_response("GET", referer, response)
        self._raise_for_status(response, "warmup")
        self._warmed_referers.add(referer)

    def download_realisasi_csv(
        self,
        tahun,
        status=None,
        all_status=False,
        instansi="",
        jenis_klpd=None,
        search_kode="",
        search_paket="",
        search_penyedia="",
        browser_fallback=False,
    ):
        self.referer_tahun = tahun
        jenis_klpd_values = self._list_value(jenis_klpd)
        if not jenis_klpd_values or not clean_text(instansi):
            raise ValueError(
                "Export CSV wajib memakai --jenis-klpd dan --instansi. "
                "Jalankan discover_inaproc_instansi dulu untuk melihat kode instansi."
            )
        payload = self.build_export_payload(
            tahun=tahun,
            status=status,
            all_status=all_status,
            instansi=instansi,
            jenis_klpd=jenis_klpd,
            search_kode=search_kode,
            search_paket=search_paket,
            search_penyedia=search_penyedia,
        )
        return self._download_csv(
            REALISASI_EXPORT_PATH,
            payload,
            browser_fallback=browser_fallback,
        )

    def fetch_realisasi_data(
        self,
        tahun,
        jenis_klpd=None,
        instansi="",
        sumber="Tender",
        status=None,
        limit=20,
    ):
        self.referer_tahun = tahun
        params = {
            "tahun": int(tahun),
            "sumber": clean_text(sumber),
            "limit": int(limit),
        }
        for value in self._list_value(jenis_klpd):
            params.setdefault("jenis_klpd", [])
            params["jenis_klpd"].append(value)
        if clean_text(instansi):
            params["instansi"] = clean_text(instansi)
        if status:
            params["status_paket"] = normalize_status(status)

        self.warmup_realisasi_page(tahun=tahun)
        response = self.session.get(
            self._url(REALISASI_DATA_PATH),
            headers=self._dashboard_json_headers(),
            params=params,
            timeout=self.timeout,
        )
        self._debug_response("GET", response.url, response)
        self._raise_for_status(response, "realisasi data")
        return response.json()

    def fetch_instansi_options(self, tahun, jenis_klpd):
        jenis_klpd = clean_text(jenis_klpd)
        if jenis_klpd not in VALID_JENIS_KLPD:
            raise ValueError(f"jenis_klpd must be one of: {', '.join(VALID_JENIS_KLPD)}")
        payload = self.fetch_realisasi_data(
            tahun=tahun,
            jenis_klpd=[jenis_klpd],
            sumber="Tender",
            limit=20,
        )
        options = payload.get("instansiOptions") or []
        return [
            {
                "kode": clean_text(item.get("kode")),
                "nama": clean_text(item.get("nama")),
                "jenis_klpd": jenis_klpd,
            }
            for item in options
            if isinstance(item, dict) and clean_text(item.get("kode")) and clean_text(item.get("nama"))
        ]

    def download_detail_csv(self, kode, browser_fallback=False):
        payload = {"kode": clean_text(kode), "type": "detail"}
        if not payload["kode"]:
            raise ValueError("kode is required")
        return self._download_csv(
            DETAIL_EXPORT_PATH,
            payload,
            browser_fallback=browser_fallback,
        )

    def parse_csv(self, csv_content, mapping=None):
        text = self._decode_csv_content(csv_content)
        if not text.strip():
            return []

        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        rows = []
        for row in reader:
            cleaned = {
                clean_text(key).lstrip("\ufeff"): clean_text(value)
                for key, value in (row or {}).items()
                if key
            }
            rows.append(self._map_row(cleaned, mapping) if mapping else cleaned)
        return rows

    def build_export_payload(
        self,
        tahun,
        status=None,
        all_status=False,
        instansi="",
        jenis_klpd=None,
        sumber_dana=None,
        search_kode="",
        search_paket="",
        search_penyedia="",
    ):
        if all_status:
            statuses = VALID_STATUS
        elif status:
            statuses = [normalize_status(status)]
        else:
            statuses = []
        return {
            "filters": {
                "tahun": int(tahun),
                "jenisKlpd": self._list_value(jenis_klpd),
                "instansi": clean_text(instansi),
                "eselon": "",
                "satker": "",
                "sumber": "Tender",
                "sumberDana": self._list_value(sumber_dana),
                "statusPaket": statuses,
            },
            "table": {
                "searchKode": clean_text(search_kode),
                "searchPaket": clean_text(search_paket),
                "searchPenyedia": clean_text(search_penyedia),
            },
        }

    def build_payload(self, *args, **kwargs):
        return self.build_export_payload(*args, **kwargs)

    def _download_csv(self, path, payload, browser_fallback=False):
        body_text = self._body_text(payload)
        try:
            signature = self.get_signature(path, body_text)
            headers = self._export_headers(path, signature)
            response = self.session.post(
                self._url(path),
                headers=headers,
                data=body_text.encode("utf-8"),
                timeout=self.timeout,
            )
            self._debug_response("POST", self._url(path), response, request_body=body_text)
            self._raise_for_status(response, "export")
            return response.text
        except InaprocForbiddenError:
            if not browser_fallback:
                raise
            return self._download_csv_with_browser(path, body_text)

    def _download_csv_with_browser(self, path, body_text):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise InaprocForbiddenError(
                "Requests tetap 403 dan Playwright belum terpasang. "
                "Install dengan `pip install playwright` lalu `python -m playwright install chromium`.",
            ) from exc

        page_url = self.realisasi_page_url()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                locale="id-ID",
                user_agent=USER_AGENT,
                extra_http_headers={
                    "accept-language": ACCEPT_LANGUAGE,
                    "sec-ch-ua": SEC_CH_UA,
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                },
            )
            page = context.new_page()
            page.goto(page_url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
            self._debug_event("GET", page_url, 200, "browser/page", "")
            result = page.evaluate(
                """
                async ({ signatureUrl, exportUrl, path, bodyText }) => {
                    const signatureResponse = await fetch(signatureUrl, {
                        method: "POST",
                        credentials: "include",
                        headers: {
                            "accept": "*/*",
                            "content-type": "application/json",
                            "sec-fetch-site": "same-origin",
                            "sec-fetch-mode": "cors",
                            "sec-fetch-dest": "empty"
                        },
                        body: JSON.stringify({ path, body: bodyText })
                    });
                    const signatureText = await signatureResponse.text();
                    if (!signatureResponse.ok) {
                        return {
                            ok: false,
                            stage: "signature",
                            status: signatureResponse.status,
                            contentType: signatureResponse.headers.get("content-type") || "",
                            body: signatureText
                        };
                    }
                    const signature = JSON.parse(signatureText);
                    const exportResponse = await fetch(exportUrl, {
                        method: "POST",
                        credentials: "include",
                        headers: {
                            "accept": "text/csv, application/json",
                            "content-type": "application/json",
                            "x-auth-time": signature.time,
                            "x-auth-path": path,
                            "x-auth-nonce": signature.nonce,
                            "x-auth-signature": signature.signature,
                            "sec-fetch-site": "same-origin",
                            "sec-fetch-mode": "cors",
                            "sec-fetch-dest": "empty"
                        },
                        body: bodyText
                    });
                    const exportText = await exportResponse.text();
                    return {
                        ok: exportResponse.ok,
                        stage: "export",
                        status: exportResponse.status,
                        contentType: exportResponse.headers.get("content-type") || "",
                        body: exportText
                    };
                }
                """,
                {
                    "signatureUrl": self._url(SIGNATURE_PATH),
                    "exportUrl": self._url(path),
                    "path": path,
                    "bodyText": body_text,
                },
            )
            browser.close()

        self._debug_event(
            "POST",
            self._url(SIGNATURE_PATH if result.get("stage") == "signature" else path),
            result.get("status"),
            result.get("contentType", ""),
            result.get("body", ""),
            error=not result.get("ok"),
        )
        if not result.get("ok"):
            response = SimpleNamespace(
                status_code=result.get("status"),
                headers={"content-type": result.get("contentType", "")},
                text=result.get("body", ""),
            )
            self._raise_for_status(response, result.get("stage") or "browser fallback")
        return result.get("body", "")

    def _map_row(self, row, mapping):
        mapped = {}
        for csv_key, field_name in mapping.items():
            value = row.get(csv_key, "")
            if field_name in RUPIAH_FIELDS:
                mapped[field_name] = parse_rupiah(value)
            elif field_name in DATE_FIELDS:
                mapped[field_name] = parse_date(value)
            else:
                mapped[field_name] = clean_text(value)
        return mapped

    def _decode_csv_content(self, csv_content):
        if isinstance(csv_content, bytes):
            for encoding in ("utf-8-sig", "utf-8", "cp1252"):
                try:
                    return csv_content.decode(encoding)
                except UnicodeDecodeError:
                    continue
            return csv_content.decode("utf-8", errors="replace")
        return str(csv_content or "")

    def _body_text(self, body):
        if isinstance(body, str):
            return body
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"))

    def _signature_headers(self):
        return {
            "accept": "*/*",
            "content-type": "application/json",
            "origin": BASE_URL,
            "referer": self.realisasi_page_url(),
            "user-agent": USER_AGENT,
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "sec-ch-ua": SEC_CH_UA,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "accept-language": ACCEPT_LANGUAGE,
        }

    def _export_headers(self, path, signature):
        headers = self._signature_headers()
        headers.update(
            {
                "accept": "text/csv, application/json",
                "x-auth-time": signature["time"],
                "x-auth-path": path,
                "x-auth-nonce": signature["nonce"],
                "x-auth-signature": signature["signature"],
            }
        )
        return headers

    def _warmup_headers(self):
        return {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "user-agent": USER_AGENT,
            "sec-fetch-site": "none",
            "sec-fetch-mode": "navigate",
            "sec-fetch-dest": "document",
            "sec-ch-ua": SEC_CH_UA,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "accept-language": ACCEPT_LANGUAGE,
        }

    def _dashboard_json_headers(self):
        headers = self._signature_headers()
        headers.update(
            {
                "accept": "application/json,*/*",
                "content-type": "application/json",
            }
        )
        return headers

    def _list_value(self, value):
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [clean_text(item) for item in value if clean_text(item)]

    def _url(self, path):
        return f"{BASE_URL}{path}"

    def realisasi_page_url(self):
        return f"{BASE_URL}/realisasi?tahun={int(self.referer_tahun)}&sumber=Tender"

    def _raise_for_status(self, response, stage):
        status_code = getattr(response, "status_code", None)
        if status_code and status_code < 400:
            return

        if status_code == 403:
            raise InaprocForbiddenError(
                "403 dari data.inaproc.id signature endpoint. "
                "Kemungkinan Cloudflare/header/session. Coba buka data.inaproc.id "
                "di browser atau gunakan mode browser fallback."
            )

        body = clean_text(getattr(response, "text", ""))[:300]
        content_type = ""
        headers = getattr(response, "headers", {}) or {}
        if hasattr(headers, "get"):
            content_type = headers.get("content-type", "")
        raise InaprocRequestError(
            f"INAPROC {stage} request failed: status={status_code} "
            f"content_type={content_type} body={body}",
            response=response,
        )

    def _debug_response(self, method, url, response, error=None, request_body=""):
        if error is None:
            error = getattr(response, "status_code", 0) >= 400
        headers = getattr(response, "headers", {}) or {}
        content_type = headers.get("content-type", "") if hasattr(headers, "get") else ""
        self._debug_event(
            method,
            url,
            getattr(response, "status_code", None),
            content_type,
            getattr(response, "text", ""),
            error=error,
            request_body=request_body,
        )

    def _debug_event(self, method, url, status_code, content_type, body, error=False, request_body=""):
        if not self.debug_callback:
            return
        preview = clean_text(body)[:300] if error else ""
        self.debug_callback(
            {
                "method": method,
                "url": url,
                "status_code": status_code,
                "content_type": content_type,
                "body_preview": preview,
                "request_body": clean_text(request_body)[:1000],
            }
        )
