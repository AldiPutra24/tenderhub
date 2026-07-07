from django.contrib import admin
from django.conf import settings
from django.urls import path, include
from users import location_views

admin.site.site_header = "GPFE PROC HUB Admin"
admin.site.site_title = "GPFE PROC HUB"
admin.site.index_title = "Procurement Intelligence Administration"

urlpatterns = [
    path(f"{settings.ADMIN_URL_PATH}/", admin.site.urls),
    path("api/locations/provinces/", location_views.provinces_api, name="api_location_provinces"),
    path("api/locations/regencies/", location_views.regencies_api, name="api_location_regencies"),
    path("", include("tenders.urls")),
    path("accounts/", include("users.urls")),
]
