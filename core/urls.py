from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    
    # Vehicles
    path('vehicles/', views.vehicle_list_view, name='vehicle_list'),
    path('vehicles/new/', views.vehicle_create_view, name='vehicle_create'),
    path('vehicles/<int:pk>/', views.vehicle_detail_view, name='vehicle_detail'),
    path('vehicles/<int:pk>/edit/', views.vehicle_update_view, name='vehicle_update'),
    path('vehicles/<int:pk>/delete/', views.vehicle_delete_view, name='vehicle_delete'),

    # Drivers
    path('drivers/', views.driver_list_view, name='driver_list'),
    path('drivers/new/', views.driver_create_view, name='driver_create'),
    path('drivers/<int:pk>/', views.driver_detail_view, name='driver_detail'),
    path('drivers/<int:pk>/edit/', views.driver_update_view, name='driver_update'),
    path('drivers/<int:pk>/delete/', views.driver_delete_view, name='driver_delete'),
]
