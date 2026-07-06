from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tenders", "0019_reclassify_realisasi_spse_mixed"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenderNotificationEmailLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                (
                    "notification",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_logs",
                        to="tenders.tendernotification",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tender_notification_email_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-sent_at"],
                "indexes": [
                    models.Index(fields=["user", "-sent_at"], name="tenders_email_log_user_idx"),
                    models.Index(fields=["sent_at"], name="tenders_email_log_sent_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="tendernotificationemaillog",
            constraint=models.UniqueConstraint(
                fields=("user", "notification"),
                name="unique_user_notification_email_log",
            ),
        ),
    ]
