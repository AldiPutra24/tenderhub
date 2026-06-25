from django.db import migrations
from django.db.models import Q


def reclassify_realisasi_spse_mixed(apps, schema_editor):
    Tender = apps.get_model("tenders", "Tender")
    spse_signal = (
        Q(lpse_slug__gt="")
        | Q(lpse_detail_url__contains="spse.inaproc.id")
        | Q(detail_url__contains="spse.inaproc.id")
    )
    Tender.objects.filter(data_source="REALISASI").filter(spse_signal).update(data_source="MIXED")


class Migration(migrations.Migration):

    dependencies = [
        ("tenders", "0018_tender_dokumen_tender_metode_kualifikasi_and_more"),
    ]

    operations = [
        migrations.RunPython(reclassify_realisasi_spse_mixed, migrations.RunPython.noop),
    ]
