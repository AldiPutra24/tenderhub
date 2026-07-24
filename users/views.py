from django.contrib import messages
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.views import (
    LoginView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode
from django.db import transaction
from .email_verification import send_verification_email
from .forms import ApprovedAuthenticationForm, ResendVerificationForm, VendorRegisterForm, VendorProfileForm
from .models import VendorProfile
from .tokens import email_verification_token
from django.contrib.auth.decorators import login_required
from users.services.turnstile import TurnstileService
import logging


logger = logging.getLogger(__name__)

def get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")

    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR", "")

class GPFELoginView(LoginView):
    template_name = "users/login.html"
    authentication_form = ApprovedAuthenticationForm

    def form_valid(self, form):
        response = super().form_valid(form)
        if form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        else:
            self.request.session.set_expiry(0)
        return response


class GPFEPasswordResetView(PasswordResetView):
    template_name = "users/password_reset_form.html"
    email_template_name = "users/password_reset_email.html"
    subject_template_name = "users/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")

    def form_valid(self, form):
        client_ip = get_client_ip(self.request)

        success = TurnstileService.verify(
            self.request.POST.get("cf-turnstile-response"),
            client_ip,
        )

        if not success:
            logger.warning(
                "Turnstile verification failed",
                extra={
                    "ip": client_ip,
                    "user_agent": self.request.META.get("HTTP_USER_AGENT"),
                },
            )
            messages.error(
                self.request,
                "Verifikasi keamanan gagal. Silakan selesaikan pemeriksaan keamanan dan coba lagi."
            )
            return self.form_invalid(form)

        return super().form_valid(form)

class GPFEPasswordResetDoneView(PasswordResetDoneView):
    template_name = "users/password_reset_done.html"


class GPFEPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "users/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")


class GPFEPasswordResetCompleteView(PasswordResetCompleteView):
    def dispatch(self, request, *args, **kwargs):
        messages.success(request, "Kata sandi berhasil diperbarui. Silakan masuk menggunakan kata sandi baru.")
        return redirect("login")

def register_view(request):
    if request.method == "POST":
        form = VendorRegisterForm(request.POST)
   
        if form.is_valid():
            email = form.cleaned_data["institution_email"]
            password = form.cleaned_data["password"]
        
            # Verify Cloudflare Turnstile
            client_ip = get_client_ip(request)

            success = TurnstileService.verify(
                request.POST.get("cf-turnstile-response"),
                client_ip,
            )

            if not success:
                logger.warning(
                    "Turnstile verification failed",
                    extra={
                        "ip": client_ip,
                        "user_agent": request.META.get("HTTP_USER_AGENT"),
                    },
                )
                messages.error(
                    request,
                    "Verifikasi keamanan gagal. Silakan selesaikan pemeriksaan keamanan dan coba lagi."
                )

                return render(
                    request,
                    "users/register.html",
                    {"form": form},
                )

            with transaction.atomic():

                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                    first_name=form.cleaned_data["full_name"],
                    is_active=False,
                )

                VendorProfile.objects.create(
                    user=user,
                    full_name=form.cleaned_data["full_name"],
                    whatsapp_number=form.cleaned_data["whatsapp_number"],
                    institution_email=email,
                    company_name=form.cleaned_data["company_name"],
                    business_field=form.cleaned_data["business_field"],
                    location_type=form.cleaned_data["location_type"],
                    province=form.cleaned_data.get("province"),
                    city_or_regency=form.cleaned_data.get("city_or_regency"),
                    country=form.cleaned_data.get("country"),
                    province_id=form.cleaned_data.get("province_id"),
                    province_name=form.cleaned_data.get("province_name"),
                    city_id=form.cleaned_data.get("city_id"),
                    city_name=form.cleaned_data.get("city_name"),
                    international_location=form.cleaned_data.get("international_location"),
                    email_verified=False,
                    email_verified_at=None,
                )

            email_sent = send_verification_with_rate_limit(request, user, email)
            if email_sent:
                messages.success(
                    request,
                    "Pendaftaran berhasil. Silakan periksa email Anda untuk melakukan verifikasi akun.",
                )
            else:
                messages.success(
                    request,
                    "Pendaftaran berhasil, tetapi email verifikasi gagal dikirim.",
                )
                messages.warning(
                    request,
                    "Silakan gunakan kirim ulang verifikasi dari halaman masuk.",
                )
            return redirect("login")

    else:
        form = VendorRegisterForm()

    return render(request, "users/register.html", {"form": form})


def verify_email_view(request, uidb64, token):
    user = get_user_from_uid(uidb64)
    if not user or not email_verification_token.check_token(user, token):
        messages.error(request, "Tautan verifikasi tidak valid atau sudah kedaluwarsa.")
        return render(request, "users/email_verification_result.html", {"verified": False})

    profile = get_or_create_profile(user)
    if not profile.email_verified:
        profile.email_verified = True
        profile.email_verified_at = timezone.now()
        profile.save(update_fields=["email_verified", "email_verified_at"])

    messages.success(
        request,
        "Verifikasi email berhasil. Akun Anda akan melalui proses peninjauan oleh administrator.",
    )
    return render(request, "users/email_verification_result.html", {"verified": True})


def resend_verification_view(request):
    if request.user.is_authenticated:
        profile = get_or_create_profile(request.user)
        if profile.email_verified:
            messages.info(request, "Email Anda telah diverifikasi.")
            return redirect("dashboard")

        if request.method == "POST":
            email_sent = send_verification_with_rate_limit(request, request.user, request.user.email)
            if email_sent:
                messages.success(
                    request,
                    "Email verifikasi telah dikirim kembali. Silakan periksa kotak masuk atau folder spam pada email Anda.",
                )
            else:
                messages.warning(
                    request,
                    "Permintaan pengiriman ulang terlalu sering. Silakan coba kembali dalam beberapa menit.",
                )
            return redirect("resend_verification")

        cache_key = f"email-verification:{(request.user.email or '').strip().casefold()}"
        remaining_seconds = 0
        if cache.get(cache_key):
            remaining_seconds = 60
        return render(request, "users/resend_verification.html", {"form": None, "profile": profile, "remaining_seconds": remaining_seconds})

    if request.method == "POST":
        form = ResendVerificationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip()
            request.session["resend_email"] = email
            user = User.objects.filter(email__iexact=email).select_related("vendor_profile").first()
            if not user:
                messages.success(
                    request,
                    "Email verifikasi telah dikirim kembali. Silakan periksa kotak masuk atau folder spam pada email Anda.",
                )
                return redirect("resend_verification")

            email_sent = send_verification_with_rate_limit(request, user, email)
            if not email_sent:
                messages.warning(
                    request,
                    "Permintaan pengiriman ulang terlalu sering. Silakan coba kembali dalam beberapa menit.",
                )
            else:
                messages.success(
                    request,
                    "Email verifikasi telah dikirim kembali. Silakan periksa kotak masuk atau folder spam pada email Anda.",
                )
            return redirect("resend_verification")
    else:
        form = ResendVerificationForm()

    resend_email = request.session.pop("resend_email", None) or form.data.get("email", "")
    cache_key = f"email-verification:{(resend_email or '').strip().casefold()}"
    remaining_seconds = 0
    if cache.get(cache_key):
        remaining_seconds = 60
    return render(request, "users/resend_verification.html", {"form": form, "remaining_seconds": remaining_seconds})


def get_user_from_uid(uidb64):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        return User.objects.select_related("vendor_profile").get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None


def get_or_create_profile(user):
    try:
        return user.vendor_profile
    except ObjectDoesNotExist:
        return VendorProfile.objects.create(
            user=user,
            full_name=user.get_full_name() or user.username,
            institution_email=user.email or user.username,
            company_name="",
            whatsapp_number="",
            business_field="",
            email_verified=False,
            email_verified_at=None,
        )


def send_verification_with_rate_limit(request, user, email):
    cache_key = f"email-verification:{(email or '').strip().casefold()}"
    if cache.get(cache_key):
        return False

    cache.set(cache_key, True, 60)
    if not user:
        return False

    profile = get_or_create_profile(user)
    if profile.email_verified:
        return False

    try:
        send_verification_email(request, user)
    except Exception:
        logger.exception("Failed to send verification email for user_id=%s email=%s", user.pk, email)
        return False
    return True


def inactive_view(request):
    return render(request, "users/inactive.html", {
        "has_auth_session": bool(request.session.get(SESSION_KEY)),
    })


@login_required
def profile_view(request):
    profile, created = VendorProfile.objects.get_or_create(
        user=request.user,
        defaults={
            "full_name": request.user.get_full_name() or request.user.username,
            "institution_email": request.user.email or request.user.username,
            "company_name": "",
            "whatsapp_number": "",
            "business_field": "",
        }
    )

    if request.method == "POST":
        form = VendorProfileForm(request.POST, instance=profile)

        if form.is_valid():
            form.save()
            return redirect("vendor_profile")
    else:
        form = VendorProfileForm(instance=profile)

    return render(request, "users/profile.html", {
        "form": form,
        "profile": profile,
        "created": created,
    })
