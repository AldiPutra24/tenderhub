from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenders", "0008_tender_lpse_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="tender",
            name="lpse_slug",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
    ]
