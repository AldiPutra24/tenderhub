from django.db import models
from django.contrib.auth.models import User


class Tender(models.Model):
    # === IDENTITAS ===
    kode_tender = models.CharField(max_length=50, unique=True)
    kode_rup = models.CharField(max_length=100, blank=True, null=True, default="")

    # === NAMA ===
    nama_paket = models.TextField(blank=True, null=True)
    nama_paket_rup = models.TextField(blank=True, null=True)

    # === INSTANSI ===
    instansi = models.CharField(max_length=255, blank=True, null=True, default="")
    klpd_instansi = models.CharField(max_length=255, blank=True, null=True, default="")
    satuankerja = models.TextField(blank=True, null=True, default="")

    # === STATUS ===
    tahapan = models.CharField(max_length=255, blank=True, null=True, default="")
    status = models.CharField(max_length=50, blank=True, null=True, default="")
    tender_ulang = models.BooleanField(default=False)
    alasan_ulang = models.TextField(blank=True, null=True, default="")

    # === KEUANGAN ===
    sumber_dana = models.CharField(max_length=255, blank=True, null=True, default="")
    tahun_anggaran = models.CharField(max_length=50, blank=True, null=True, default="")

    nilai_hps = models.BigIntegerField(blank=True, null=True)
    nilai_pagu = models.BigIntegerField(blank=True, null=True)

    # === LOKASI ===
    lokasi_pekerjaan = models.TextField(blank=True, null=True)

    # === JENIS ===
    jenis_pengadaan = models.CharField(max_length=255, blank=True, null=True, default="")
    metode_pengadaan = models.CharField(max_length=255, blank=True, null=True, default="")
    jenis_kontrak = models.CharField(max_length=255, blank=True, null=True, default="")

    # === KOMPETISI ===
    peserta_count = models.IntegerField(blank=True, null=True)

    # === DOKUMEN ===
    uraian_pekerjaan = models.URLField(max_length=1000, blank=True, null=True, default="")
    uraian_pekerjaan_nama_file = models.TextField(blank=True, null=True)
    detail_url = models.URLField(max_length=1000, blank=True, null=True, default="")

    # === LPSE ===
    lpse_kd = models.IntegerField(blank=True, null=True)
    lpse_slug = models.CharField(max_length=120, blank=True, default="")
    lpse_name = models.CharField(max_length=255, blank=True, default="")
    lpse_detail_url = models.URLField(blank=True, default="")

    # === META ===
    tanggal_pembuatan = models.DateField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        nama = self.nama_paket or "-"
        return f"{self.kode_tender} - {nama}"


class TenderBookmark(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "tender")

    def __str__(self):
        return f"{self.user} - {self.tender}"


class LPSEWatchlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="lpse_watchlists")
    lpse_slug = models.SlugField(max_length=160)
    lpse_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "lpse_slug"],
                name="unique_user_lpse_watchlist",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.lpse_name}"


class TenderNotification(models.Model):
    WATCHLIST_LPSE = "watchlist_lpse"
    AI_MATCH_HIGH = "ai_match_high"
    NOTIFICATION_TYPE_CHOICES = [
        (WATCHLIST_LPSE, "Watchlist LPSE"),
        (AI_MATCH_HIGH, "AI Match Tinggi"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tender_notifications")
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name="notifications")
    notification_type = models.CharField(max_length=32, choices=NOTIFICATION_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tender", "notification_type"],
                name="unique_user_tender_notification_type",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "is_read", "-created_at"],
                name="tenders_ten_user_id_d785ce_idx",
            ),
        ]
        ordering = ["is_read", "-created_at"]

    def __str__(self):
        return f"{self.user} - {self.title}"
