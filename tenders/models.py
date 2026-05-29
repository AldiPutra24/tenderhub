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
    satuankerja = models.CharField(max_length=255, blank=True, null=True, default="")

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
