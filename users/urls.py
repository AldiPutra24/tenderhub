from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import (
    GPFELoginView,
    GPFEPasswordResetCompleteView,
    GPFEPasswordResetConfirmView,
    GPFEPasswordResetDoneView,
    GPFEPasswordResetView,
    inactive_view,
    profile_view,
    register_view,
    resend_verification_view,
    verify_email_view,
)

urlpatterns = [
    path("register/", register_view, name="register"),
    path("login/", GPFELoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path("password-reset/", GPFEPasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", GPFEPasswordResetDoneView.as_view(), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", GPFEPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset/done/", GPFEPasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("verify-email/<uidb64>/<token>/", verify_email_view, name="verify_email"),
    path("resend-verification/", resend_verification_view, name="resend_verification"),
    path("inactive/", inactive_view, name="inactive_account"),
    path("profile/", profile_view, name="vendor_profile"),
]
