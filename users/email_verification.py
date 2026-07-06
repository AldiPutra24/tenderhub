from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

from .tokens import email_verification_token


def build_verification_url(request, user):
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    path = reverse("verify_email", kwargs={"uidb64": uidb64, "token": token})
    return request.build_absolute_uri(path)


def send_verification_email(request, user):
    profile = user.vendor_profile
    verification_url = build_verification_url(request, user)
    body = render_to_string(
        "users/email_verification_email.txt",
        {
            "user": user,
            "profile": profile,
            "verification_url": verification_url,
        },
    )
    send_mail(
        subject="Verifikasi Email GPFE PROC HUB",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
