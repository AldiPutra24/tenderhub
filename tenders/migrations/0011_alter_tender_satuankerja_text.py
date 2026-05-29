from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenders", "0010_tender_tender_ulang_alasan_ulang"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tender",
            name="satuankerja",
            field=models.TextField(blank=True, default="", null=True),
        ),
    ]
