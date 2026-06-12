import re


def extract_budget_years(value):
    years = re.findall(r"\b(20\d{2}|19\d{2})\b", str(value or ""))
    return sorted(set(years), key=int)


def normalize_budget_years(value):
    return ", ".join(extract_budget_years(value))
