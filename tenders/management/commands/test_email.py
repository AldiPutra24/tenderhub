from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a simple email to verify SMTP configuration"

    def add_arguments(self, parser):
        parser.add_argument("--to", required=True, help="Recipient email address")

    def handle(self, *args, **options):
        recipient = options["to"]

        try:
            sent_count = send_mail(
                subject="GPFE PROC HUB Email Test",
                message="Email configuration is working.",
                from_email=None,
                recipient_list=[recipient],
                fail_silently=False,
            )
        except Exception as exc:
            raise CommandError(f"Email test failed: {exc.__class__.__name__}") from exc

        if sent_count != 1:
            raise CommandError("Email test did not report a successful send.")

        self.stdout.write(self.style.SUCCESS(f"Email test sent to {recipient}"))
