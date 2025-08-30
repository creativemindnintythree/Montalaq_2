from django.urls import path
from .views import UserPreferenceView

urlpatterns = [
    path("", UserPreferenceView.as_view(), name="user-preferences"),
]
