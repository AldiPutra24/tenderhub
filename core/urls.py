from django.contrib import admin
from django.conf import settings
from django.urls import path, include

urlpatterns = [
    path(f"{settings.ADMIN_URL_PATH}/", admin.site.urls),
    path("", include("tenders.urls")),
    path("accounts/", include("users.urls")),
]
