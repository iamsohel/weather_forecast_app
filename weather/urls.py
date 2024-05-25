from django.urls import path

from .views import compare_temperatures, get_coolest_districts

urlpatterns = [
    path("coolest-districts/", get_coolest_districts, name="coolest_districts"),
    path("travel-decision/", compare_temperatures, name="compare_temperatures"),
]
