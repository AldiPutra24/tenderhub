from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView
from .forms import ApprovedAuthenticationForm
from .views import inactive_view, register_view, profile_view

urlpatterns = [
    path("register/", register_view, name="register"),
    path(
        "login/",
        LoginView.as_view(
            template_name="users/login.html",
            authentication_form=ApprovedAuthenticationForm,
        ),
        name="login",
    ),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path("inactive/", inactive_view, name="inactive_account"),
    path("profile/", profile_view, name="vendor_profile"),
]
