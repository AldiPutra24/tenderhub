from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tenders", "0012_lpsewatchlist"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenderNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "notification_type",
                    models.CharField(
                        choices=[("watchlist_lpse", "Watchlist LPSE"), ("ai_match_high", "AI Match Tinggi")],
                        max_length=32,
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("is_read", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                (
                    "tender",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to="tenders.tender",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tender_notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["is_read", "-created_at"],
                "indexes": [models.Index(fields=["user", "is_read", "-created_at"], name="tenders_ten_user_id_d785ce_idx")],
            },
        ),
        migrations.AddConstraint(
            model_name="tendernotification",
            constraint=models.UniqueConstraint(
                fields=("user", "tender", "notification_type"),
                name="unique_user_tender_notification_type",
            ),
        ),
    ]
