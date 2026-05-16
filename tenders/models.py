from django.db import models
from django.contrib.auth.models import User


class Tender(models.Model):
    # === IDENTITAS ===
    kode_tender = models.CharField(max_length=50, unique=True)
    kode_rup = models.CharField(max_length=100, blank=True)

    # === NAMA ===
    nama_paket = models.TextField(blank=True, null=True)
    nama_paket_rup = models.TextField(blank=True, null=True)

    # === INSTANSI ===
    instansi = models.CharField(max_length=255)
    klpd_instansi = models.CharField(max_length=255, blank=True, default="")
    satuankerja = models.CharField(max_length=255, blank=True)

    # === STATUS ===
    tahapan = models.CharField(max_length=255)
    status = models.CharField(max_length=50)

    # === KEUANGAN ===
    sumber_dana = models.CharField(max_length=255, blank=True)
    tahun_anggaran = models.CharField(max_length=50, blank=True)

    nilai_hps = models.BigIntegerField(null=True, blank=True)
    nilai_pagu = models.BigIntegerField(null=True, blank=True)

    # === LOKASI ===
    lokasi_pekerjaan = models.TextField(blank=True, null=True)

    # === JENIS ===
    jenis_pengadaan = models.CharField(max_length=255, blank=True)
    metode_pengadaan = models.CharField(max_length=255, blank=True)
    jenis_kontrak = models.CharField(max_length=255, blank=True)

    # === KOMPETISI ===
    peserta_count = models.IntegerField(null=True, blank=True)

    # === DOKUMEN ===
    uraian_pekerjaan = models.URLField(max_length=1000, blank=True)
    uraian_pekerjaan_nama_file = models.TextField(blank=True, null=True)
    detail_url = models.URLField(blank=True)

    # === META ===
    tanggal_pembuatan = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.kode_tender} - {self.nama_paket}"
    
class TenderBookmark(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'tender')
