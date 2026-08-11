from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from tenders.models import Tender
from tenders.views import build_lpse_entries, get_operational_queryset


class HomeSitemap(Sitemap):
    changefreq = "daily"
    priority = 1.0

    def items(self):
        return ["home"]

    def location(self, item):
        return reverse(item)


class TenderListSitemap(Sitemap):
    changefreq = "hourly"
    priority = 0.9

    def items(self):
        return ["tender_list"]

    def location(self, item):
        return reverse(item)


class TenderDetailSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.7

    def items(self):
        return get_operational_queryset().only("id", "updated_at").order_by("-id")

    def location(self, obj):
        return reverse("tender_detail", args=[obj.id])

    def lastmod(self, obj):
        return obj.updated_at


class LpseListSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return ["lpse_list"]

    def location(self, item):
        return reverse(item)


class LpseDetailSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.6

    def items(self):
        return [e["slug"] for e in build_lpse_entries() if e["slug"]]

    def location(self, slug):
        return reverse("lpse_detail", args=[slug])
