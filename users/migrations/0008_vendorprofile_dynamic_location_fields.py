from django.db import migrations, models


def copy_existing_location_names(apps, schema_editor):
    VendorProfile = apps.get_model("users", "VendorProfile")
    for profile in VendorProfile.objects.all():
        update_fields = []

        if profile.location_type == "indonesia":
            if not profile.country:
                profile.country = "Indonesia"
                update_fields.append("country")
            if profile.province and not profile.province_name:
                profile.province_name = profile.province
                update_fields.append("province_name")
            if profile.city_or_regency and not profile.city_name:
                profile.city_name = profile.city_or_regency
                update_fields.append("city_name")
        else:
            if profile.country and not profile.international_location:
                profile.international_location = profile.country
                update_fields.append("international_location")

        if update_fields:
            profile.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0007_fix_vendorprofile_email_verified_nulls"),
    ]

    operations = [
        migrations.AddField(
            model_name="vendorprofile",
            name="province_id",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="vendorprofile",
            name="province_name",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="vendorprofile",
            name="city_id",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="vendorprofile",
            name="city_name",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="vendorprofile",
            name="international_location",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.RunPython(copy_existing_location_names, migrations.RunPython.noop),
    ]
