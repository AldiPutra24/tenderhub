import logging
import re

import requests
from django.core.cache import cache


logger = logging.getLogger(__name__)

LOCATION_CACHE_SECONDS = 7 * 24 * 60 * 60
PROVINCES_CACHE_KEY = "locations:indonesia:provinces"
REGENCIES_CACHE_KEY_PREFIX = "locations:indonesia:regencies"
PROVIDER_BASE_URL = "https://www.emsifa.com/api-wilayah-indonesia/api"
REQUEST_TIMEOUT_SECONDS = 8

FALLBACK_PROVINCES = [
    {"id": "35", "name": "Jawa Timur"},
    {"id": "34", "name": "DI Yogyakarta"},
]

FALLBACK_REGENCIES = {
    "35": [
        {"id": "3501", "name": "Kab. Pacitan"},
        {"id": "3502", "name": "Kab. Ponorogo"},
        {"id": "3503", "name": "Kab. Trenggalek"},
        {"id": "3504", "name": "Kab. Tulungagung"},
        {"id": "3505", "name": "Kab. Blitar"},
        {"id": "3571", "name": "Kota Kediri"},
        {"id": "3572", "name": "Kota Blitar"},
        {"id": "3573", "name": "Kota Malang"},
        {"id": "3578", "name": "Kota Surabaya"},
    ],
    "34": [
        {"id": "3401", "name": "Kab. Kulon Progo"},
        {"id": "3402", "name": "Kab. Bantul"},
        {"id": "3403", "name": "Kab. Gunungkidul"},
        {"id": "3404", "name": "Kab. Sleman"},
        {"id": "3471", "name": "Kota Yogyakarta"},
    ],
}


class LocationProviderError(Exception):
    pass


def normalize_location_item(item):
    return {
        "id": str(item.get("id", "")).strip(),
        "name": str(item.get("name", "")).strip().title(),
    }


def get_regencies_cache_key(province_id):
    return f"{REGENCIES_CACHE_KEY_PREFIX}:{province_id}"


def fetch_provider_json(path):
    url = f"{PROVIDER_BASE_URL}/{path.lstrip('/')}"
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise LocationProviderError("Provider returned invalid location payload.")
    return [normalize_location_item(item) for item in data if item.get("id") and item.get("name")]


def get_provinces():
    try:
        provinces = fetch_provider_json("provinces.json")
    except Exception as exc:
        logger.warning("Failed to fetch provinces from location provider: %s", exc)
        cached = cache.get(PROVINCES_CACHE_KEY)
        if cached:
            return cached, "cache"
        return FALLBACK_PROVINCES, "fallback"

    cache.set(PROVINCES_CACHE_KEY, provinces, LOCATION_CACHE_SECONDS)
    return provinces, "provider"


def get_regencies(province_id):
    province_id = str(province_id or "").strip()
    cache_key = get_regencies_cache_key(province_id)

    if not province_id:
        return [], "empty"

    try:
        regencies = fetch_provider_json(f"regencies/{province_id}.json")
    except Exception as exc:
        logger.warning("Failed to fetch regencies from location provider province_id=%s: %s", province_id, exc)
        cached = cache.get(cache_key)
        if cached:
            return cached, "cache"
        fallback = FALLBACK_REGENCIES.get(province_id)
        if fallback:
            return fallback, "fallback"
        raise LocationProviderError("Data kota/kabupaten belum tersedia. Silakan coba lagi.")

    cache.set(cache_key, regencies, LOCATION_CACHE_SECONDS)
    return regencies, "provider"


def get_location_name(items, location_id):
    location_id = str(location_id or "").strip()
    for item in items:
        if item["id"] == location_id:
            return item["name"]
    return ""


def normalize_location_name(value):
    value = str(value or "").strip().casefold()
    value = re.sub(r"^(kabupaten|kab\.|kota)\s+", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def find_location_by_name(items, location_name):
    normalized_name = normalize_location_name(location_name)
    if not normalized_name:
        return None

    for item in items:
        if normalize_location_name(item["name"]) == normalized_name:
            return item
    return None


def validate_indonesia_location(province_id, city_id, province_name="", city_name=""):
    province_id = str(province_id or "").strip()
    city_id = str(city_id or "").strip()
    submitted_province_name = province_name
    submitted_city_name = city_name
    provinces, _ = get_provinces()
    province_name = get_location_name(provinces, province_id)
    if not province_name:
        province = find_location_by_name(provinces, submitted_province_name)
        if not province:
            return None
        province_id = province["id"]
        province_name = province["name"]

    try:
        regencies, _ = get_regencies(province_id)
    except LocationProviderError:
        return None

    city_name = get_location_name(regencies, city_id)
    if not city_name:
        city = find_location_by_name(regencies, submitted_city_name)
        if not city:
            return None
        city_id = city["id"]
        city_name = city["name"]

    return {
        "province_id": str(province_id).strip(),
        "province_name": province_name,
        "city_id": str(city_id).strip(),
        "city_name": city_name,
    }
