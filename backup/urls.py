from django.urls import path
from . import views

urlpatterns = [
    path("backup/trigger/", views.trigger_backup, name="trigger_backup"),
]
