from django import template
import re


register = template.Library()


MONTHS_ID = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}


@register.filter
def tanggal_indonesia(value):
    if not value:
        return "-"

    return f"{value.day} {MONTHS_ID.get(value.month, '')} {value.year}"


@register.filter
def rupiah(value):
    if value in (None, ""):
        return "Rp 0"
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return "Rp 0"
    return "Rp " + f"{amount:,}".replace(",", ".")


@register.filter
def rupiah_compact(value):
    if value in (None, ""):
        return "Rp 0"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "Rp 0"

    units = [
        (1_000_000_000_000, "T"),
        (1_000_000_000, "M"),
        (1_000_000, "Jt"),
    ]
    for divisor, suffix in units:
        if abs(amount) >= divisor:
            number = amount / divisor
            formatted = f"{number:.1f}".rstrip("0").rstrip(".").replace(".", ",")
            return f"Rp {formatted} {suffix}"
    return "Rp " + f"{int(amount):,}".replace(",", ".")


@register.filter
def percent_id(value):
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "-"


@register.filter
def sumber_dana_tahun(sumber_dana, tahun_anggaran):
    if not sumber_dana:
        return "-"

    value = str(sumber_dana).strip()
    tahun = str(tahun_anggaran or "").strip()
    if not tahun:
        return value
    if re.search(rf"\b{re.escape(tahun)}\b", value):
        return value
    return f"{value} {tahun}"
