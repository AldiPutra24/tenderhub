from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0004_alter_vendorprofile_preferred_locations_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="vendorprofile",
            name="email_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="vendorprofile",
            name="email_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
