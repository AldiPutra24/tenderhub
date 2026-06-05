from django.contrib import admin
from django.conf import settings
from django.urls import path, include

admin.site.site_header = "GPFE PROC HUB Admin"
admin.site.site_title = "GPFE PROC HUB"
admin.site.index_title = "Procurement Intelligence Administration"

urlpatterns = [
    path(f"{settings.ADMIN_URL_PATH}/", admin.site.urls),
    path("", include("tenders.urls")),
    path("accounts/", include("users.urls")),
]
