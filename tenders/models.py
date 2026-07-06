from django.db import models
from django.contrib.auth.models import User


class Tender(models.Model):
    SOURCE_SPSE = "SPSE"
    SOURCE_REALISASI = "REALISASI"
    SOURCE_LKPP_API = "LKPP_API"
    SOURCE_MIXED = "MIXED"
    DATA_SOURCE_CHOICES = [
        (SOURCE_SPSE, "SPSE"),
        (SOURCE_REALISASI, "INAPROC Realisasi"),
        (SOURCE_LKPP_API, "LKPP API"),
        (SOURCE_MIXED, "Mixed"),
    ]

    # === IDENTITAS ===
    kode_tender = models.CharField(max_length=50, db_index=True)
    kode_paket = models.CharField(max_length=50, unique=True, blank=True, null=True)
    kode_rup = models.CharField(max_length=100, blank=True, null=True, default="")

    # === NAMA ===
    nama_paket = models.TextField(blank=True, null=True)
    nama_paket_rup = models.TextField(blank=True, null=True)

    # === INSTANSI ===
    instansi = models.CharField(max_length=255, blank=True, null=True, default="")
    nama_instansi = models.CharField(max_length=255, blank=True, null=True)
    klpd_instansi = models.CharField(max_length=255, blank=True, null=True, default="")
    satuankerja = models.TextField(blank=True, null=True, default="")
    nama_satuan_kerja = models.TextField(blank=True, null=True)

    # === STATUS ===
    tahapan = models.CharField(max_length=255, blank=True, null=True, default="")
    status = models.CharField(max_length=50, blank=True, null=True, default="")
    status_paket = models.CharField(max_length=50, blank=True, null=True)
    tender_ulang = models.BooleanField(default=False)
    alasan_ulang = models.TextField(blank=True, null=True, default="")

    # === KEUANGAN ===
    sumber_dana = models.TextField(blank=True, null=True, default="")
    sumber_transaksi = models.CharField(max_length=100, blank=True, null=True)
    tahun_anggaran = models.CharField(max_length=50, blank=True, null=True, default="")

    nilai_hps = models.BigIntegerField(blank=True, null=True)
    nilai_pagu = models.BigIntegerField(blank=True, null=True)
    nilai_kontrak = models.BigIntegerField(blank=True, null=True)
    total_nilai = models.BigIntegerField(blank=True, null=True)
    nilai_pdn = models.BigIntegerField(blank=True, null=True)

    # === LOKASI ===
    lokasi_pekerjaan = models.TextField(blank=True, null=True)

    # === JENIS ===
    kategori = models.CharField(max_length=255, blank=True, null=True)
    jenis_pengadaan = models.CharField(max_length=255, blank=True, null=True, default="")
    metode_pengadaan = models.CharField(max_length=255, blank=True, null=True, default="")
    metode_kualifikasi = models.CharField(max_length=255, blank=True, null=True, default="")
    metode_pemilihan = models.CharField(max_length=255, blank=True, null=True, default="")
    metode_tender = models.CharField(max_length=255, blank=True, null=True)
    metode_evaluasi = models.CharField(max_length=255, blank=True, null=True)
    cara_pembayaran = models.CharField(max_length=255, blank=True, null=True)
    jenis_kontrak = models.CharField(max_length=255, blank=True, null=True, default="")

    # === KOMPETISI ===
    peserta_count = models.IntegerField(blank=True, null=True)
    nama_penyedia = models.CharField(max_length=255, blank=True, null=True)

    # === DOKUMEN ===
    uraian_pekerjaan = models.URLField(max_length=1000, blank=True, null=True, default="")
    uraian_pekerjaan_nama_file = models.TextField(blank=True, null=True)
    dokumen = models.TextField(blank=True, null=True, default="")
    detail_url = models.URLField(max_length=1000, blank=True, null=True, default="")

    # === LPSE ===
    lpse_kd = models.IntegerField(blank=True, null=True)
    lpse_slug = models.CharField(max_length=120, blank=True, default="")
    lpse_name = models.CharField(max_length=255, blank=True, default="")
    lpse_detail_url = models.URLField(blank=True, default="")

    # === META ===
    tanggal_pembuatan = models.DateField(blank=True, null=True)
    tanggal_tender = models.DateField(blank=True, null=True)
    data_source = models.CharField(
        max_length=20,
        choices=DATA_SOURCE_CHOICES,
        default=SOURCE_SPSE,
        blank=True,
        null=True,
    )
    raw_data = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        nama = self.nama_paket or "-"
        return f"{self.kode_tender} - {nama}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kode_tender", "lpse_slug"],
                name="unique_tender_kode_lpse_slug",
            ),
        ]
        indexes = [
            models.Index(fields=["data_source", "status"], name="tenders_src_status_idx"),
            models.Index(fields=["lpse_slug", "status"], name="tenders_lpse_status_idx"),
        ]


class InaprocInstansi(models.Model):
    kode = models.CharField(max_length=50)
    nama = models.CharField(max_length=255)
    jenis_klpd = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["jenis_klpd", "kode"],
                name="unique_inaproc_instansi_jenis_kode",
            )
        ]
        indexes = [
            models.Index(fields=["jenis_klpd", "is_active"], name="tenders_ina_jenis_k_0f3e0b_idx"),
            models.Index(fields=["kode"], name="tenders_ina_kode_5a2d9f_idx"),
        ]
        ordering = ["jenis_klpd", "nama"]

    def __str__(self):
        return f"{self.jenis_klpd}:{self.kode} - {self.nama}"


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


class TenderNotificationEmailLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tender_notification_email_logs")
    notification = models.ForeignKey(
        TenderNotification,
        on_delete=models.CASCADE,
        related_name="email_logs",
    )
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "notification"],
                name="unique_user_notification_email_log",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-sent_at"], name="tenders_email_log_user_idx"),
            models.Index(fields=["sent_at"], name="tenders_email_log_sent_idx"),
        ]
        ordering = ["-sent_at"]

    def __str__(self):
        return f"{self.user} - {self.notification_id} - {self.sent_at}"
