from django.contrib import admin
from django.utils.html import format_html

from .models import InaprocInstansi, LPSEWatchlist, Tender, TenderBookmark, TenderNotification


@admin.register(Tender)
class TenderAdmin(admin.ModelAdmin):
    list_display = (
        "kode_tender",
        "nama_paket",
        "instansi",
        "jenis_pengadaan",
        "nilai_hps_display",
        "status_badge",
        "tanggal_pembuatan",
    )
    list_filter = (
        "jenis_pengadaan",
        "status",
        "tanggal_pembuatan",
    )
    search_fields = (
        "kode_tender",
        "nama_paket",
        "instansi",
        "klpd_instansi",
        "lpse_name",
    )
    readonly_fields = ("uraian_file_link", "created_at", "updated_at")
    list_per_page = 50
    ordering = ("-tanggal_pembuatan", "-created_at")
    date_hierarchy = "tanggal_pembuatan"
    show_full_result_count = False
    fieldsets = (
        (
            "Informasi Utama",
            {
                "fields": (
                    "kode_tender",
                    "nama_paket",
                    "instansi",
                    "klpd_instansi",
                    "lpse_kd",
                    "lpse_slug",
                    "lpse_name",
                    "tahapan",
                    "status",
                    "tender_ulang",
                    "alasan_ulang",
                    "tanggal_pembuatan",
                )
            },
        ),
        (
            "RUP & Sumber Dana",
            {
                "classes": ("collapse",),
                "fields": (
                    "kode_rup",
                    "nama_paket_rup",
                    "sumber_dana",
                    "tahun_anggaran",
                ),
            },
        ),
        (
            "Detail Pengadaan",
            {
                "classes": ("collapse",),
                "fields": (
                    "satuankerja",
                    "jenis_pengadaan",
                    "metode_pengadaan",
                    "jenis_kontrak",
                    "lokasi_pekerjaan",
                    "peserta_count",
                ),
            },
        ),
        ("Nilai", {"fields": ("nilai_pagu", "nilai_hps")}),
        (
            "Dokumen",
            {
                "classes": ("collapse",),
                "fields": (
                    "uraian_pekerjaan",
                    "uraian_pekerjaan_nama_file",
                    "uraian_file_link",
                    "detail_url",
                    "lpse_detail_url",
                ),
            },
        ),
        (
            "Metadata",
            {
                "classes": ("collapse",),
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    @admin.display(description="Nilai HPS", ordering="nilai_hps")
    def nilai_hps_display(self, obj):
        if obj.nilai_hps is None:
            return "-"
        return f"Rp {obj.nilai_hps:,.0f}".replace(",", ".")

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        status = obj.status or "-"
        normalized = status.lower()
        badge_class = "status-neutral"
        if any(value in normalized for value in ("selesai", "aktif", "berjalan")):
            badge_class = "status-success"
        elif any(value in normalized for value in ("batal", "gagal")):
            badge_class = "status-danger"
        elif any(value in normalized for value in ("evaluasi", "proses")):
            badge_class = "status-warning"
        return format_html('<span class="status-badge {}">{}</span>', badge_class, status)

    @admin.display(description="Uraian Singkat Pekerjaan")
    def uraian_file_link(self, obj):
        if obj.uraian_pekerjaan:
            label = obj.uraian_pekerjaan_nama_file or "Buka dokumen"
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>',
                obj.uraian_pekerjaan,
                label
            )
        return "-"


@admin.register(TenderBookmark)
class TenderBookmarkAdmin(admin.ModelAdmin):
    list_display = ("user", "tender_code", "tender_name", "created_at")
    list_filter = ("created_at", "tender__jenis_pengadaan")
    search_fields = (
        "user__username",
        "user__email",
        "tender__kode_tender",
        "tender__nama_paket",
        "tender__instansi",
    )
    list_select_related = ("user", "tender")
    autocomplete_fields = ("user", "tender")
    readonly_fields = ("created_at",)
    list_per_page = 50
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    @admin.display(description="Kode Tender", ordering="tender__kode_tender")
    def tender_code(self, obj):
        return obj.tender.kode_tender

    @admin.display(description="Nama Paket", ordering="tender__nama_paket")
    def tender_name(self, obj):
        return obj.tender.nama_paket or "-"


@admin.register(LPSEWatchlist)
class LPSEWatchlistAdmin(admin.ModelAdmin):
    list_display = ("user", "lpse_name", "lpse_slug", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "user__email", "lpse_name", "lpse_slug")
    list_select_related = ("user",)
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at",)
    list_per_page = 50
    ordering = ("-created_at",)
    date_hierarchy = "created_at"


@admin.register(TenderNotification)
class TenderNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "title",
        "tender",
        "notification_type",
        "is_read",
        "created_at",
        "read_at",
    )
    list_filter = ("notification_type", "is_read", "created_at", "read_at")
    search_fields = ("user__username", "user__email", "title", "tender__kode_tender", "tender__nama_paket")
    list_select_related = ("user", "tender")
    autocomplete_fields = ("user", "tender")
    readonly_fields = ("created_at", "read_at")
    list_per_page = 50
    ordering = ("-created_at",)
    date_hierarchy = "created_at"


@admin.register(InaprocInstansi)
class InaprocInstansiAdmin(admin.ModelAdmin):
    list_display = ("jenis_klpd", "kode", "nama", "is_active", "updated_at")
    list_filter = ("jenis_klpd", "is_active")
    search_fields = ("kode", "nama")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("jenis_klpd", "nama")
    list_per_page = 100
