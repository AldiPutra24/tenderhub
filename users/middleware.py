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
        "/admin/",
        "/static/",
        "/media/",
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

        if not request.user.is_active:
            logger.warning("Inactive user blocked user_id=%s path=%s", request.user.id, path)
            messages.warning(
                request,
                "Akun kakak belum aktif. Silakan tunggu approval admin.",
            )
            return redirect(reverse("inactive_account"))

        return self.get_response(request)

    def requires_approval(self, path):
        if path == "/":
            return False
        if any(path.startswith(prefix) for prefix in self.public_prefixes):
            return False
        return any(path.startswith(prefix) for prefix in self.protected_prefixes)

    def has_inactive_session_user(self, request):
        user_id = request.session.get(SESSION_KEY)
        if not user_id:
            return False
        return User.objects.filter(pk=user_id, is_active=False).exists()
