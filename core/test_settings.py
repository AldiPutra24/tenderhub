from core.settings import *  # noqa: F401,F403

# Nonaktifkan migrations untuk test DB (sqlite lokal < 3.31 tidak punya
# JSON_VALID yang dibutuhkan migration 0021). Tabel dibuat dari model saat ini.
MIGRATION_MODULES = {
    "tenders": None,
    "users": None,
    "vendors": None,
}
