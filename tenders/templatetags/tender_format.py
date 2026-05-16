from django import template


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
