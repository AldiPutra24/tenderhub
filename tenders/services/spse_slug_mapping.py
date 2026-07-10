import json
import re
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


PORTAL_URL = "https://spse.inaproc.id/"
REQUEST_TIMEOUT_SECONDS = 60
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
EXCLUDED_SLUGS = {"latihan", "dpd"}
PORTAL_ENTRY_RE = re.compile(
    r'\{name:"(?P<name>(?:\\.|[^"\\])*)",oldUrl:"(?P<old_url>(?:\\.|[^"\\])*)",newUrlPath:"(?P<slug>(?:\\.|[^"\\])*)"\}'
)
SAFE_SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def default_mapping_path():
    return Path(__file__).resolve().parents[1] / "data" / "lpse_slug_mapping.json"


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def decode_js_string(value):
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace('\\"', '"').replace("\\/", "/").replace("\\\\", "\\")


def normalize_slug(value):
    slug = clean_text(value).strip("/")
    if slug.startswith("https://spse.inaproc.id/"):
        slug = slug.split("https://spse.inaproc.id/", 1)[1].split("/", 1)[0]
    if "/" in slug:
        slug = slug.split("/", 1)[0]
    if not slug or slug in EXCLUDED_SLUGS or not SAFE_SLUG_RE.match(slug):
        return ""
    return slug


def clean_lpse_name(value, slug):
    name = clean_text(value)
    return name or slug


def load_slug_mapping(path=None):
    mapping_path = Path(path) if path else default_mapping_path()
    if not mapping_path.exists():
        return OrderedDict()

    with mapping_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    mapping = OrderedDict()
    if isinstance(data, dict):
        iterable = data.items()
    elif isinstance(data, list):
        iterable = (
            (
                item.get("slug") or item.get("lpse_slug"),
                item.get("name") or item.get("lpse_name") or item.get("nama_lpse"),
            )
            for item in data
            if isinstance(item, dict)
        )
    else:
        return mapping

    for slug, name in iterable:
        slug = normalize_slug(slug)
        if slug and slug not in mapping:
            mapping[slug] = clean_lpse_name(name, slug)
    return mapping


def write_slug_mapping(mapping, path=None):
    mapping_path = Path(path) if path else default_mapping_path()
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = mapping_path.with_suffix(f"{mapping_path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(dict(mapping), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp_path.replace(mapping_path)


def parse_portal_entries(*script_texts):
    mapping = OrderedDict()
    for script_text in script_texts:
        for match in PORTAL_ENTRY_RE.finditer(script_text or ""):
            slug = normalize_slug(decode_js_string(match.group("slug")))
            if not slug or slug in mapping:
                continue
            old_url = decode_js_string(match.group("old_url"))
            if "test.local" in old_url or "eproc.dev" in old_url:
                continue
            mapping[slug] = clean_lpse_name(decode_js_string(match.group("name")), slug)
    return mapping


def fetch_portal_script_texts(session=None, portal_url=PORTAL_URL):
    session = session or requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    response = session.get(portal_url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    scripts = []
    for script in soup.find_all("script", src=True):
        src = script.get("src") or ""
        if "/_next/static/chunks/" not in src:
            continue
        scripts.append(urljoin(portal_url, src))

    script_texts = []
    for script_url in scripts:
        script_response = session.get(script_url, timeout=REQUEST_TIMEOUT_SECONDS)
        script_response.raise_for_status()
        script_texts.append(script_response.text)
    return script_texts


def discover_portal_slug_mapping(session=None):
    return parse_portal_entries(*fetch_portal_script_texts(session=session))


def merge_slug_mapping(existing_mapping, discovered_mapping, update_existing=True):
    merged = OrderedDict(existing_mapping)
    added = OrderedDict()
    updated = OrderedDict()
    unchanged = 0

    for slug, name in discovered_mapping.items():
        if slug not in merged:
            merged[slug] = name
            added[slug] = name
            continue
        if update_existing and name and merged[slug] != name:
            updated[slug] = {"old": merged[slug], "new": name}
            merged[slug] = name
        else:
            unchanged += 1

    return {
        "mapping": merged,
        "added": added,
        "updated": updated,
        "unchanged": unchanged,
    }


def sync_slug_mapping(path=None, session=None, update_existing=True, dry_run=False):
    existing = load_slug_mapping(path)
    discovered = discover_portal_slug_mapping(session=session)
    result = merge_slug_mapping(existing, discovered, update_existing=update_existing)
    if not dry_run and (result["added"] or result["updated"]):
        write_slug_mapping(result["mapping"], path)
    result["existing_count"] = len(existing)
    result["discovered_count"] = len(discovered)
    result["final_count"] = len(result["mapping"])
    return result
