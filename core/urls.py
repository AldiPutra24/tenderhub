from django.contrib import admin
from django.conf import settings
from django.http import HttpResponse
from django.urls import path, include
from django.contrib.sitemaps import views as sitemap_views
from core.sitemaps import (
    HomeSitemap,
    TenderListSitemap,
    TenderDetailSitemap,
    LpseListSitemap,
    LpseDetailSitemap,
)
from users import location_views

admin_slug = getattr(settings, "ADMIN_URL_PATH", "admin")


def robots_txt(request):
    scheme = request.scheme
    host = request.get_host()
    lines = [
        "User-agent: *",
        "Allow: /",
        f"Disallow: /{admin_slug}/",
        "Disallow: /dashboard/",
        "Disallow: /accounts/",
        "Disallow: /lpse/watchlist/",
        "Disallow: /notifications/",
        "Disallow: /settings/",
        "",
        f"Sitemap: {scheme}://{host}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


admin.site.site_header = "GPFE PROC HUB Admin"
admin.site.site_title = "GPFE PROC HUB"
admin.site.index_title = "Procurement Intelligence Administration"

SITEMAPS = {
    "home": HomeSitemap,
    "tender_list": TenderListSitemap,
    "tenders": TenderDetailSitemap,
    "lpse_list": LpseListSitemap,
    "lpse": LpseDetailSitemap,
}

urlpatterns = [
    path(f"{settings.ADMIN_URL_PATH}/", admin.site.urls),
    path("api/locations/provinces/", location_views.provinces_api, name="api_location_provinces"),
    path("api/locations/regencies/", location_views.regencies_api, name="api_location_regencies"),
    path("", include("tenders.urls")),
    path("accounts/", include("users.urls")),
    path("robots.txt", robots_txt, name="robots_txt"),
    path(
        "sitemap.xml",
        sitemap_views.index,
        {"sitemaps": SITEMAPS},
        name="sitemap",
    ),
    path(
        "sitemap-<section>.xml",
        sitemap_views.sitemap,
        {"sitemaps": SITEMAPS},
        name="django.contrib.sitemaps.views.sitemap",
    ),
]
