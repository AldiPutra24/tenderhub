import re
from decimal import Decimal, InvalidOperation


PROFILE_INCOMPLETE_MATCH = {
    "score": 0,
    "level": "Low",
    "label": "Lengkapi Profil",
    "reasons": [],
    "missing": [
        "Lengkapi profil vendor untuk AI Match yang lebih akurat.",
    ],
    "requires_profile": True,
}


def normalize_text(value):
    if value is None:
        return ""

    text = str(value).casefold()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def safe_list(value):
    if not value:
        return []

    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[\n,;|]+", value) if item.strip()]

    return [str(value).strip()]


def safe_number(value):
    if value in (None, ""):
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        cleaned = re.sub(r"[^0-9.,-]+", "", str(value))
        if not cleaned:
            return None

        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif cleaned.count(".") > 1:
            cleaned = cleaned.replace(".", "")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")

        try:
            return Decimal(cleaned)
        except (InvalidOperation, TypeError, ValueError):
            return None


def _keywords(value):
    stopwords = {
        "dan",
        "atau",
        "yang",
        "untuk",
        "jasa",
        "pengadaan",
        "pekerjaan",
        "bidang",
        "usaha",
        "pt",
        "cv",
    }

    text = normalize_text(value)
    if not text:
        return []

    phrases = [text]
    words = [
        word
        for word in text.split()
        if len(word) >= 3 and word not in stopwords
    ]
    return phrases + words


def keyword_match(source, target):
    target_text = normalize_text(target)
    if not target_text:
        return False

    for keyword in _keywords(source):
        if keyword and keyword in target_text:
            return True

    return False


def _list_match(values, target):
    target_text = normalize_text(target)
    if not target_text:
        return False

    return any(keyword_match(value, target_text) for value in safe_list(values))


def _level_for_score(score):
    if score >= 70:
        return "High", "High Opportunity"
    if score >= 40:
        return "Medium", "Medium Opportunity"
    return "Low", "Low Opportunity"


def calculate_tender_match(tender, vendor_profile):
    if not vendor_profile:
        return PROFILE_INCOMPLETE_MATCH.copy()

    score = 0
    reasons = []
    missing = []

    tender_title = getattr(tender, "nama_paket", "")
    tender_type = getattr(tender, "jenis_pengadaan", "")
    tender_location = getattr(tender, "lokasi_pekerjaan", "")
    tender_value = safe_number(getattr(tender, "nilai_hps", None)) or safe_number(
        getattr(tender, "nilai_pagu", None)
    )

    business_field = getattr(vendor_profile, "business_field", "")
    business_target = f"{tender_title} {tender_type}"
    if business_field and keyword_match(business_field, business_target):
        score += 35
        reasons.append("Bidang usaha cocok dengan nama paket atau jenis pengadaan.")
    else:
        missing.append("Bidang usaha belum terlalu cocok dengan nama paket.")

    preferred_types = safe_list(getattr(vendor_profile, "preferred_procurement_types", []))
    if preferred_types and _list_match(preferred_types, tender_type):
        score += 25
        reasons.append("Jenis pengadaan sesuai dengan preferensi vendor.")
    elif preferred_types:
        missing.append("Jenis pengadaan belum masuk preferensi utama vendor.")
    else:
        missing.append("Preferensi jenis pengadaan vendor belum diisi.")

    location_preferences = []
    location_preferences.extend(safe_list(getattr(vendor_profile, "preferred_locations", [])))
    for field in ("province_name", "city_name", "international_location", "province", "city_or_regency", "country"):
        location_preferences.extend(safe_list(getattr(vendor_profile, field, "")))

    if location_preferences and _list_match(location_preferences, tender_location):
        score += 20
        reasons.append("Lokasi pekerjaan sesuai dengan wilayah target vendor.")
    elif location_preferences:
        missing.append("Lokasi pekerjaan belum cocok dengan wilayah target vendor.")
    else:
        missing.append("Lokasi target vendor belum diisi.")

    min_value = safe_number(getattr(vendor_profile, "min_project_value", None))
    max_value = safe_number(getattr(vendor_profile, "max_project_value", None))

    if tender_value is None:
        missing.append("Nilai HPS atau pagu tender belum tersedia.")
    elif min_value is None and max_value is None:
        missing.append("Range nilai proyek vendor belum diisi.")
    else:
        above_min = min_value is None or tender_value >= min_value
        below_max = max_value is None or tender_value <= max_value

        if above_min and below_max:
            score += 20
            reasons.append("Nilai HPS berada dalam range proyek vendor.")
        else:
            missing.append("Nilai HPS berada di luar range proyek vendor.")

    score = min(score, 100)
    level, label = _level_for_score(score)

    return {
        "score": score,
        "level": level,
        "label": label,
        "reasons": reasons,
        "missing": missing,
        "requires_profile": False,
    }
