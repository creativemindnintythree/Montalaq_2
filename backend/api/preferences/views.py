from rest_framework.generics import RetrieveUpdateAPIView
from backend.preferences.models import UserPreference
from .serializers import UserPreferenceSerializer

class UserPreferenceView(RetrieveUpdateAPIView):
    serializer_class = UserPreferenceSerializer
    def get_object(self):
        obj, _ = UserPreference.objects.get_or_create(pk=1)
        return obj
