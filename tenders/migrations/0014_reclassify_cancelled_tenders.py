from django.db import migrations
from django.db.models import Q


def reclassify_cancelled_tenders(apps, schema_editor):
    Tender = apps.get_model("tenders", "Tender")
    Tender.objects.filter(
        Q(tahapan__icontains="batal") | Q(tahapan__icontains="gagal")
    ).exclude(status="FAILED").update(status="FAILED")


class Migration(migrations.Migration):
    dependencies = [
        ("tenders", "0013_tendernotification"),
    ]

    operations = [
        migrations.RunPython(
            reclassify_cancelled_tenders,
            migrations.RunPython.noop,
        ),
    ]
