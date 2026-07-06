from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_vendorprofile_email_verification"),
    ]

    operations = [
        migrations.AddField(
            model_name="vendorprofile",
            name="email_notifications_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="vendorprofile",
            name="email_digest_frequency",
            field=models.CharField(
                choices=[
                    ("DAILY", "Setiap Hari"),
                    ("THREE_DAYS", "Setiap 3 Hari"),
                    ("WEEKLY", "Mingguan"),
                ],
                default="THREE_DAYS",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="vendorprofile",
            name="last_digest_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
