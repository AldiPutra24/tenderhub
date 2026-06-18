from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenders", "0014_reclassify_cancelled_tenders"),
    ]

    operations = [
        migrations.AddField(
            model_name="tender",
            name="kode_paket",
            field=models.CharField(blank=True, max_length=50, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="tender",
            name="nama_instansi",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="tender",
            name="nama_satuan_kerja",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tender",
            name="status_paket",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="tender",
            name="sumber_transaksi",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="tender",
            name="total_nilai",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tender",
            name="nilai_pdn",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tender",
            name="kategori",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="tender",
            name="metode_tender",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="tender",
            name="metode_evaluasi",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="tender",
            name="cara_pembayaran",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="tender",
            name="nama_penyedia",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="tender",
            name="tanggal_tender",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tender",
            name="data_source",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="tender",
            name="raw_data",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
