from django.urls import path
from .views import show_data, map_view
from . import views

urlpatterns = [
    path('', show_data, name='home'),       # Homepage
    path('data/', show_data, name='show_data'),  # Data Table
    path('index/', map_view, name='index'),  # Map Page
    path('ppi-dashboard/', views.ppi_dashboard, name='ppi_dashboard'), # PPI Page
]