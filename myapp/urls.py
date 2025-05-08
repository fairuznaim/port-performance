from django.urls import path
from .views import show_data, map_view

urlpatterns = [
    path('', show_data, name='home'),       # Homepage
    path('data/', show_data, name='show_data'),  # Data Table
    path('index/', map_view, name='index'),  # Map Page
]