from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenders", "0016_alter_tender_detail_url_alter_tender_instansi_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="InaprocInstansi",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kode", models.CharField(max_length=50)),
                ("nama", models.CharField(max_length=255)),
                ("jenis_klpd", models.CharField(max_length=10)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["jenis_klpd", "nama"],
            },
        ),
        migrations.AddIndex(
            model_name="inaprocinstansi",
            index=models.Index(fields=["jenis_klpd", "is_active"], name="tenders_ina_jenis_k_0f3e0b_idx"),
        ),
        migrations.AddIndex(
            model_name="inaprocinstansi",
            index=models.Index(fields=["kode"], name="tenders_ina_kode_5a2d9f_idx"),
        ),
        migrations.AddConstraint(
            model_name="inaprocinstansi",
            constraint=models.UniqueConstraint(
                fields=("jenis_klpd", "kode"),
                name="unique_inaproc_instansi_jenis_kode",
            ),
        ),
    ]
