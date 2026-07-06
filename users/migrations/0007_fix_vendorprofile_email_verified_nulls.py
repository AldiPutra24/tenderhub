from django.db import migrations


def fix_null_email_verified(apps, schema_editor):
    VendorProfile = apps.get_model("users", "VendorProfile")
    VendorProfile.objects.filter(email_verified__isnull=True).update(email_verified=False)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0006_vendorprofile_email_digest_preferences"),
    ]

    operations = [
        migrations.RunPython(fix_null_email_verified, migrations.RunPython.noop),
    ]
