from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Auth
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('', views.dashboard_view, name='dashboard'),
    
    # Vehicles
    path('vehicles/', views.VehicleListView.as_view(), name='vehicle_list'),
    path('vehicles/new/', views.VehicleCreateView.as_view(), name='vehicle_create'),
    path('vehicles/<int:pk>/', views.VehicleDetailView.as_view(), name='vehicle_detail'),
    path('vehicles/<int:pk>/edit/', views.VehicleUpdateView.as_view(), name='vehicle_update'),
    path('vehicles/<int:pk>/delete/', views.VehicleDeleteView.as_view(), name='vehicle_delete'),

    # Drivers
    path('drivers/', views.DriverListView.as_view(), name='driver_list'),
    path('drivers/new/', views.DriverCreateView.as_view(), name='driver_create'),
    path('drivers/<int:pk>/', views.DriverDetailView.as_view(), name='driver_detail'),
    path('drivers/<int:pk>/edit/', views.DriverUpdateView.as_view(), name='driver_update'),
    path('drivers/<int:pk>/delete/', views.DriverDeleteView.as_view(), name='driver_delete'),

    # Trips & Dispatch
    path('trips/', views.TripListView.as_view(), name='trip_list'),
    path('trips/new/', views.TripCreateView.as_view(), name='trip_create'),
    path('trips/<int:pk>/', views.TripDetailView.as_view(), name='trip_detail'),
    path('trips/<int:pk>/edit/', views.TripUpdateView.as_view(), name='trip_update'),
    path('trips/<int:pk>/delete/', views.TripDeleteView.as_view(), name='trip_delete'),
    
    # State transitions
    path('trips/<int:pk>/dispatch/', views.trip_dispatch_view, name='trip_dispatch'),
    path('trips/<int:pk>/complete/', views.trip_complete_view, name='trip_complete'),
    path('trips/<int:pk>/cancel/', views.trip_cancel_view, name='trip_cancel'),

    # Quick Actions (One-Click Operations)
    path('vehicles/<int:pk>/quick-maintenance/', views.vehicle_quick_maintenance, name='vehicle_quick_maintenance'),
    path('vehicles/<int:pk>/quick-resolve-maintenance/', views.vehicle_quick_resolve_maintenance, name='vehicle_quick_resolve_maintenance'),
    path('trips/<int:pk>/quick-dispatch/', views.trip_quick_dispatch, name='trip_quick_dispatch'),
    path('trips/<int:pk>/quick-complete/', views.trip_quick_complete, name='trip_quick_complete'),

    # Maintenance Logs
    path('maintenance/', views.MaintenanceLogListView.as_view(), name='maintenance_list'),
    path('maintenance/new/', views.MaintenanceLogCreateView.as_view(), name='maintenance_create'),
    path('maintenance/<int:pk>/edit/', views.MaintenanceLogUpdateView.as_view(), name='maintenance_update'),

    # Analytics Dashboard
    path('analytics/', views.AnalyticsView.as_view(), name='analytics'),

    # Performance Reports & Exports
    path('reports/', views.ReportsView.as_view(), name='reports'),
    path('reports/vehicles/csv/', views.export_vehicles_csv, name='export_vehicles_csv'),
    path('reports/vehicles/pdf/', views.export_vehicles_pdf, name='export_vehicles_pdf'),
    path('reports/drivers/csv/', views.export_drivers_csv, name='export_drivers_csv'),
    path('reports/drivers/pdf/', views.export_drivers_pdf, name='export_drivers_pdf'),

    # Finance & ROI Reports
    path('finance/', views.FinanceReportView.as_view(), name='finance_report'),
    path('api/finance/data/', views.finance_api_view, name='finance_api_data'),
]
