from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("settings/", views.settings_redirect, name="settings"),
    path("notifications/<int:notification_id>/read/", views.mark_tender_notification_read, name="tender_notification_read"),
    path("notifications/<int:notification_id>/open/", views.open_tender_notification, name="tender_notification_open"),
    path("notifications/read-all/", views.mark_all_tender_notifications_read, name="tender_notifications_read_all"),
    path("tenders/", views.tender_list, name="tender_list"),
    path("tenders/bookmarks/", views.saved_tenders, name="saved_tenders"),
    path("tenders/<int:pk>/", views.tender_detail, name="tender_detail"),
    path("tender/<int:pk>/", views.tender_detail, name="tender_detail_legacy"),
    path("lpse/", views.lpse_list_view, name="lpse_list"),
    path("lpse", views.lpse_list_view, name="lpse_list"),
    path("lpse/watchlist/", views.lpse_watchlist_view, name="lpse_watchlist"),
    path("lpse/<slug:slug>/watchlist/add/", views.add_lpse_watchlist, name="lpse_watchlist_add"),
    path("lpse/<slug:slug>/watchlist/remove/", views.remove_lpse_watchlist, name="lpse_watchlist_remove"),
    path("lpse/open/<str:kode_tender>/", views.open_lpse_detail, name="open_lpse_detail"),
    path("lpse/<slug:slug>/", views.lpse_detail_view, name="lpse_detail"),
    path("bookmark/<int:pk>/", views.toggle_bookmark, name="toggle_bookmark"),
    path("dashboard/saved/", views.saved_tenders_legacy, name="saved_tenders_legacy"),
]
