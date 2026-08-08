from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/activities/$', consumers.ActivityConsumer.as_asgi()),
]
