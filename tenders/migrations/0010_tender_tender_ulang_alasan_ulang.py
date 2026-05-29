from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenders", "0009_tender_lpse_slug"),
    ]

    operations = [
        migrations.AddField(
            model_name="tender",
            name="tender_ulang",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="tender",
            name="alasan_ulang",
            field=models.TextField(blank=True, default="", null=True),
        ),
    ]
