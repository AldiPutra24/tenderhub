from django.conf import settings
from django.contrib import messages
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import User
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect
from django.urls import reverse
import logging


logger = logging.getLogger(__name__)


class ApprovedUserRequiredMiddleware:
    protected_prefixes = (
        "/dashboard",
        "/settings",
        "/bookmark",
        "/tender",
        "/tenders",
        "/lpse",
        "/recommendations",
        "/analytics",
        "/notifications",
        "/bookmark",
        "/accounts/profile",
    )
    public_prefixes = (
        "/accounts/login/",
        "/accounts/register/",
        "/accounts/logout/",
        "/accounts/inactive/",
        "/accounts/password-reset/",
        "/accounts/reset/",
        "/accounts/verify-email/",
        "/accounts/resend-verification/",
        "/admin/",
        "/static/",
        "/media/",
    )
    limited_prefixes = (
        "/accounts/profile",
        "/accounts/logout",
        "/accounts/inactive",
        "/accounts/resend-verification",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info

        if not self.requires_approval(path):
            return self.get_response(request)

        if not request.user.is_authenticated:
            if self.has_inactive_session_user(request):
                logger.warning("Inactive session blocked path=%s", path)
                messages.warning(
                    request,
                    "Akun kakak belum aktif. Silakan tunggu approval admin.",
                )
                return redirect(reverse("inactive_account"))

            logger.info("Anonymous access redirected path=%s", path)
            messages.info(
                request,
                "Silakan login terlebih dahulu untuk mengakses halaman tersebut.",
            )
            return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)

        email_verified = self.is_email_verified(request.user)
        if not email_verified:
            logger.warning("Unverified user blocked user_id=%s path=%s", request.user.id, path)
            messages.warning(
                request,
                "Email kakak belum diverifikasi. Silakan cek email untuk verifikasi akun.",
            )
            return redirect(reverse("resend_verification"))

        if not request.user.is_active and not self.is_limited_allowed(path):
            logger.warning("Pending approval user blocked user_id=%s path=%s", request.user.id, path)
            messages.warning(
                request,
                "Akun kakak sudah terverifikasi, tetapi masih menunggu approval admin untuk mengakses fitur tender.",
            )
            return redirect(reverse("dashboard"))

        return self.get_response(request)

    def requires_approval(self, path):
        if path == "/":
            return False
        if any(path.startswith(prefix) for prefix in self.public_prefixes):
            return False
        return any(path.startswith(prefix) for prefix in self.protected_prefixes)

    def is_limited_allowed(self, path):
        if path in ("/dashboard", "/dashboard/"):
            return True
        return any(path.startswith(prefix) for prefix in self.limited_prefixes)

    def is_email_verified(self, user):
        profile = getattr(user, "vendor_profile", None)
        return bool(profile and profile.email_verified)

    def has_inactive_session_user(self, request):
        user_id = request.session.get(SESSION_KEY)
        if not user_id:
            return False
        return User.objects.filter(pk=user_id, is_active=False).exists()
