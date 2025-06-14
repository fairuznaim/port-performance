from django.urls import path
from .views import (
    homepage,
    map_with_data,
    ppi_dashboard,
    get_phase_graph_data,
    refresh_ppi
)

urlpatterns = [
    path('', homepage, name='home'), 
    path('map/', map_with_data, name='map_with_data'),
    path('ppi-dashboard/', ppi_dashboard, name='ppi_dashboard'),
    path('api/phase-graph/<str:phase>/', get_phase_graph_data, name='phase-graph-api'),
    path('refresh-ppi/',refresh_ppi, name='refresh_ppi'),
]