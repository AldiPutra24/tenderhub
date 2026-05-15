from django.contrib import admin
from django.utils.html import format_html
from .models import Tender
from .models import Tender, TenderBookmark

@admin.register(Tender)
class TenderAdmin(admin.ModelAdmin):
    list_display = (
        "kode_tender",
        "nama_paket",
        "instansi",
        "status",
        "tahapan",
        "jenis_pengadaan",
        "metode_pengadaan",
        "sumber_dana",
        "nilai_hps",
        "nilai_pagu",
        "peserta_count",
        "uraian_file_link",
    )

    list_filter = (
        "status",
        "jenis_pengadaan",
        "metode_pengadaan",
        "sumber_dana",
        "tahun_anggaran",
        "instansi",
    )

    search_fields = (
        "kode_tender",
        "kode_rup",
        "nama_paket",
        "nama_paket_rup",
        "instansi",
        "satuankerja",
        "lokasi_pekerjaan",
    )

    readonly_fields = (
        "uraian_file_link",
    )

    fieldsets = (
        ("Informasi Utama", {
            "fields": (
                "kode_tender",
                "nama_paket",
                "instansi",
                "tahapan",
                "status",
            )
        }),
        ("RUP & Sumber Dana", {
            "fields": (
                "kode_rup",
                "nama_paket_rup",
                "sumber_dana",
                "tahun_anggaran",
            )
        }),
        ("Detail Pengadaan", {
            "fields": (
                "satuankerja",
                "jenis_pengadaan",
                "metode_pengadaan",
                "jenis_kontrak",
                "lokasi_pekerjaan",
                "peserta_count",
            )
        }),
        ("Nilai", {
            "fields": (
                "nilai_pagu",
                "nilai_hps",
            )
        }),
        ("Dokumen", {
            "fields": (
                "uraian_pekerjaan",
                "uraian_pekerjaan_nama_file",
                "uraian_file_link",
            )
        }),
        ("Tanggal", {
            "fields": (
                "tanggal_pembuatan",
            )
        }),
    )

    def uraian_file_link(self, obj):
        if obj.uraian_pekerjaan:
            label = obj.uraian_pekerjaan_nama_file or "Buka dokumen"
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>',
                obj.uraian_pekerjaan,
                label
            )
        return "-"

    uraian_file_link.short_description = "Uraian Singkat Pekerjaan"

admin.site.register(TenderBookmark)