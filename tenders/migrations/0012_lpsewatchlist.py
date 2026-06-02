from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tenders", "0011_alter_tender_satuankerja_text"),
    ]

    operations = [
        migrations.CreateModel(
            name="LPSEWatchlist",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("lpse_slug", models.SlugField(max_length=160)),
                ("lpse_name", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lpse_watchlists",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["user", "created_at"], name="tenders_lps_user_id_1ed275_idx")],
            },
        ),
        migrations.AddConstraint(
            model_name="lpsewatchlist",
            constraint=models.UniqueConstraint(fields=("user", "lpse_slug"), name="unique_user_lpse_watchlist"),
        ),
    ]
