from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("tenders/", views.tender_list, name="tender_list"),
    path("tender/<int:pk>/", views.tender_detail, name="tender_detail"),
    path("bookmark/<int:pk>/", views.toggle_bookmark, name="toggle_bookmark"),
    path("dashboard/saved/", views.saved_tenders, name="saved_tenders"),
]
