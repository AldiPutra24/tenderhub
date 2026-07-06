from django.core.management.base import BaseCommand

from tenders.services.email_digest import send_due_digests


class Command(BaseCommand):
    help = "Send GPFE PROC HUB tender email digests for users whose notification preferences are due."

    def handle(self, *args, **options):
        result = send_due_digests()
        self.stdout.write(
            self.style.SUCCESS(
                "Tender digest complete: "
                f"checked={result['checked']} "
                f"sent={result['sent']} "
                f"skipped={result['skipped']} "
                f"notifications_logged={result['notifications_logged']}"
            )
        )
