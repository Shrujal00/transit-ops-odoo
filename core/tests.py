from django.test import TestCase, TransactionTestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth.models import Group
import datetime
import threading
from decimal import Decimal
from .models import Role, User, Vehicle, Driver, Trip, MaintenanceLog, FuelLog, Expense, AuditLog

class VehicleModelTest(TestCase):
    def test_registration_number_uppercase_on_save(self):
        vehicle = Vehicle.objects.create(
            registration_number="  tx-4589-k  ",
            make="Toyota",
            model="Hilux",
            year=2021,
            capacity_kg=1200,
            acquisition_cost=35000.00
        )
        self.assertEqual(vehicle.registration_number, "TX-4589-K")

    def test_invalid_capacity_raises_validation_error(self):
        vehicle = Vehicle(
            registration_number="TX-1111-B",
            make="Toyota",
            model="Hilux",
            year=2021,
            capacity_kg=0,
            acquisition_cost=35000.00
        )
        with self.assertRaises(ValidationError):
            vehicle.full_clean()

    def test_invalid_acquisition_cost_raises_validation_error(self):
        vehicle = Vehicle(
            registration_number="TX-1111-B",
            make="Toyota",
            model="Hilux",
            year=2021,
            capacity_kg=1200,
            acquisition_cost=-50.00
        )
        with self.assertRaises(ValidationError):
            vehicle.full_clean()

class DriverModelTest(TestCase):
    def test_is_license_valid_with_future_expiry(self):
        expiry = timezone.now().date() + datetime.timedelta(days=10)
        driver = Driver(
            name="John Doe",
            license_number="DL-12345",
            license_expiry=expiry,
            status="Available"
        )
        self.assertTrue(driver.is_license_valid)

    def test_is_license_valid_with_past_expiry(self):
        expiry = timezone.now().date() - datetime.timedelta(days=1)
        driver = Driver(
            name="Jane Doe",
            license_number="DL-54321",
            license_expiry=expiry,
            status="Available"
        )
        self.assertFalse(driver.is_license_valid)


class ViewGuardsRBACTest(TestCase):
    def setUp(self):
        self.fm_role = Role.objects.create(name="Fleet Manager", code="fleet_manager")
        self.driver_role = Role.objects.create(name="Driver", code="driver")
        
        self.fm_group = Group.objects.create(name="Fleet Manager")
        self.driver_group = Group.objects.create(name="Driver")
        
        self.manager_user = User.objects.create_user(email="manager@test.com", password="password123", role=self.fm_role)
        self.manager_user.groups.add(self.fm_group)
        
        self.driver_user_1 = User.objects.create_user(email="driver1@test.com", password="password123", role=self.driver_role)
        self.driver_user_1.groups.add(self.driver_group)

        self.driver_user_2 = User.objects.create_user(email="driver2@test.com", password="password123", role=self.driver_role)
        self.driver_user_2.groups.add(self.driver_group)

        self.vehicle = Vehicle.objects.create(
            registration_number="TX-9988-V", make="Ford", model="Transit", year=2020, capacity_kg=3000, acquisition_cost=40000.00
        )
        self.driver_1 = Driver.objects.create(
            user=self.driver_user_1, name="John Driver 1", license_number="LIC-111", license_expiry=timezone.now().date() + datetime.timedelta(days=365)
        )
        self.driver_2 = Driver.objects.create(
            user=self.driver_user_2, name="Jane Driver 2", license_number="LIC-222", license_expiry=timezone.now().date() + datetime.timedelta(days=365)
        )

    def test_unauthenticated_user_redirects_to_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_fleet_manager_can_access_vehicle_crud(self):
        self.client.login(email="manager@test.com", password="password123")
        response = self.client.get(reverse('vehicle_list'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('vehicle_create'))
        self.assertEqual(response.status_code, 200)

    def test_driver_blocked_from_vehicle_create(self):
        self.client.login(email="driver1@test.com", password="password123")
        response = self.client.get(reverse('vehicle_create'))
        self.assertEqual(response.status_code, 403)

    def test_driver_blocked_from_driver_list(self):
        self.client.login(email="driver1@test.com", password="password123")
        response = self.client.get(reverse('driver_list'))
        self.assertEqual(response.status_code, 403)

    def test_driver_can_view_own_detail_but_blocked_from_other_driver_detail(self):
        self.client.login(email="driver1@test.com", password="password123")
        response = self.client.get(reverse('driver_detail', kwargs={'pk': self.driver_1.pk}))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('driver_detail', kwargs={'pk': self.driver_2.pk}))
        self.assertEqual(response.status_code, 403)


class DispatchStateMachineTest(TestCase):
    def setUp(self):
        self.fm_role = Role.objects.create(name="Fleet Manager", code="fleet_manager")
        self.fm_group = Group.objects.create(name="Fleet Manager")
        self.manager_user = User.objects.create_user(email="manager@test.com", password="password123", role=self.fm_role)
        self.manager_user.groups.add(self.fm_group)
        
        self.vehicle = Vehicle.objects.create(
            registration_number="TX-5544-M", make="Toyota", model="Hilux", year=2021, capacity_kg=1200, acquisition_cost=35000.00
        )
        self.driver = Driver.objects.create(
            name="Bob Driver", license_number="LIC-Bob", license_expiry=timezone.now().date() + datetime.timedelta(days=100)
        )
        self.client.login(email="manager@test.com", password="password123")

    def test_cargo_limit_validation(self):
        trip = Trip(
            source="A", destination="B", vehicle=self.vehicle, driver=self.driver, cargo_weight=1500, scheduled_date=timezone.now().date()
        )
        with self.assertRaises(ValidationError):
            trip.full_clean()

    def test_driver_license_valid_at_dispatch(self):
        expired_driver = Driver.objects.create(
            name="Expired Bob", license_number="LIC-Expired", license_expiry=timezone.now().date() - datetime.timedelta(days=1)
        )
        trip = Trip.objects.create(
            source="A", destination="B", vehicle=self.vehicle, driver=expired_driver, cargo_weight=1000, scheduled_date=timezone.now().date()
        )
        response = self.client.post(reverse('trip_dispatch', kwargs={'pk': trip.pk}))
        trip.refresh_from_db()
        self.assertEqual(trip.status, 'Draft')

    def test_dispatch_state_transition(self):
        trip = Trip.objects.create(
            source="A", destination="B", vehicle=self.vehicle, driver=self.driver, cargo_weight=1000, scheduled_date=timezone.now().date()
        )
        response = self.client.post(reverse('trip_dispatch', kwargs={'pk': trip.pk}))
        trip.refresh_from_db()
        self.vehicle.refresh_from_db()
        self.driver.refresh_from_db()
        
        self.assertEqual(trip.status, 'Ongoing')
        self.assertEqual(self.vehicle.status, 'On Trip')
        self.assertEqual(self.driver.status, 'On Trip')

        response = self.client.post(reverse('trip_complete', kwargs={'pk': trip.pk}), data={
            'end_odometer': 500,
            'fuel_consumed': '25.00'
        })
        trip.refresh_from_db()
        self.vehicle.refresh_from_db()
        self.driver.refresh_from_db()
        
        self.assertEqual(trip.status, 'Completed')
        self.assertEqual(self.vehicle.status, 'Available')
        self.assertEqual(self.driver.status, 'Available')
        self.assertEqual(self.vehicle.odometer, 500)
        self.assertIsNotNone(trip.end_time)

    def test_completion_odometer_validation(self):
        trip = Trip.objects.create(
            source="A", destination="B", vehicle=self.vehicle, driver=self.driver, cargo_weight=1000, scheduled_date=timezone.now().date()
        )
        self.client.post(reverse('trip_dispatch', kwargs={'pk': trip.pk}))
        
        response = self.client.post(reverse('trip_complete', kwargs={'pk': trip.pk}), data={
            'end_odometer': -10,
            'fuel_consumed': '15.00'
        })
        trip.refresh_from_db()
        self.assertNotEqual(trip.status, 'Completed')
        
        response = self.client.post(reverse('trip_complete', kwargs={'pk': trip.pk}), data={
            'end_odometer': 350,
            'fuel_consumed': '20.00'
        })
        trip.refresh_from_db()
        self.assertEqual(trip.status, 'Completed')
        self.assertEqual(trip.end_odometer, 350)
        self.assertEqual(float(trip.fuel_consumed), 20.00)

    def test_maintenance_flow_transitions(self):
        log = MaintenanceLog.objects.create(
            vehicle=self.vehicle, description="Repair radiator", cost=150.00, start_date=timezone.now().date(), status="In Progress"
        )
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, 'In Shop')

        log.status = "Completed"
        log.save()
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, 'Available')


class ConcurrencyLockingTest(TransactionTestCase):
    def setUp(self):
        self.fm_role = Role.objects.create(name="Fleet Manager", code="fleet_manager")
        self.fm_group = Group.objects.create(name="Fleet Manager")
        self.manager_user = User.objects.create_user(email="manager@test.com", password="password123", role=self.fm_role)
        self.manager_user.groups.add(self.fm_group)
        
        self.vehicle = Vehicle.objects.create(
            registration_number="TX-LOCK-1", make="Mack", model="Anthem", year=2021, capacity_kg=15000, acquisition_cost=150000.00
        )
        self.driver_1 = Driver.objects.create(
            name="Driver Alpha", license_number="DL-Alpha", license_expiry=timezone.now().date() + datetime.timedelta(days=365)
        )
        self.driver_2 = Driver.objects.create(
            name="Driver Beta", license_number="DL-Beta", license_expiry=timezone.now().date() + datetime.timedelta(days=365)
        )
        
        self.trip_1 = Trip.objects.create(
            source="A", destination="B", vehicle=self.vehicle, driver=self.driver_1, cargo_weight=1000, scheduled_date=timezone.now().date()
        )
        self.trip_2 = Trip.objects.create(
            source="C", destination="D", vehicle=self.vehicle, driver=self.driver_2, cargo_weight=1000, scheduled_date=timezone.now().date()
        )

    def test_double_dispatch_race_condition_fails_cleanly(self):
        errors = []
        
        # Log in two client sessions in the main thread to prevent SQLite lockups on django_session table
        client1 = self.client_class()
        client1.login(email="manager@test.com", password="password123")
        
        client2 = self.client_class()
        client2.login(email="manager@test.com", password="password123")
        
        def dispatch_action(client, trip_id):
            response = client.post(reverse('trip_dispatch', kwargs={'pk': trip_id}))
            messages_list = list(response.wsgi_request._messages)
            for msg in messages_list:
                errors.append(msg.message)

        t1 = threading.Thread(target=dispatch_action, args=(client1, self.trip_1.id))
        t2 = threading.Thread(target=dispatch_action, args=(client2, self.trip_2.id))

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, 'On Trip')
        self.assertTrue(len(errors) >= 1)
        self.assertTrue(any("not available" in err or "locked" in err for err in errors))


class FinanceAnalyticsTest(TestCase):
    def setUp(self):
        self.fa_role = Role.objects.create(name="Financial Analyst", code="financial_analyst")
        self.fa_group = Group.objects.create(name="Financial Analyst")
        self.finance_user = User.objects.create_user(email="analyst@test.com", password="password123", role=self.fa_role)
        self.finance_user.groups.add(self.fa_group)
        
        self.driver_role = Role.objects.create(name="Driver", code="driver")
        self.driver_group = Group.objects.create(name="Driver")
        self.driver_user = User.objects.create_user(email="driver@test.com", password="password123", role=self.driver_role)
        self.driver_user.groups.add(self.driver_group)

        self.vehicle = Vehicle.objects.create(
            registration_number="TX-FIN-1", make="Ford", model="F-350", year=2021, capacity_kg=3500, acquisition_cost=40000.00
        )
        self.driver = Driver.objects.create(
            user=self.driver_user, name="Finance Driver", license_number="DL-FIN", license_expiry=timezone.now().date() + datetime.timedelta(days=365)
        )

        # Revenue
        self.trip = Trip.objects.create(
            source="A", destination="B", vehicle=self.vehicle, driver=self.driver, cargo_weight=1000,
            planned_distance=200, revenue=1000.00, status="Completed",
            end_odometer=200, fuel_consumed=40.00, scheduled_date=timezone.now().date()
        )
        # Maintenance Cost
        self.maint = MaintenanceLog.objects.create(
            vehicle=self.vehicle, description="Radiator service", cost=200.00, start_date=timezone.now().date(), status="Completed"
        )
        # Fuel Cost
        self.fuel = FuelLog.objects.create(
            vehicle=self.vehicle, liters=50.00, cost=100.00, date=timezone.now().date()
        )

    def test_unauthorized_roles_cannot_access_finance_report(self):
        # Driver login
        self.client.login(email="driver@test.com", password="password123")
        response = self.client.get(reverse('finance_report'))
        self.assertEqual(response.status_code, 403)

    def test_authorized_analyst_can_access_finance_report(self):
        self.client.login(email="analyst@test.com", password="password123")
        response = self.client.get(reverse('finance_report'))
        self.assertEqual(response.status_code, 200)

    def test_roi_calculation_values_reconcile(self):
        self.client.login(email="analyst@test.com", password="password123")
        
        # Call report view
        response = self.client.get(reverse('finance_report'))
        self.assertEqual(response.status_code, 200)
        
        # Verify context values
        self.assertEqual(float(response.context['fleet_revenue']), 1000.00)
        self.assertEqual(float(response.context['fleet_maintenance']), 200.00)
        self.assertEqual(float(response.context['fleet_fuel']), 100.00)
        self.assertEqual(float(response.context['fleet_op_cost']), 300.00)
        self.assertAlmostEqual(float(response.context['fleet_roi']), (1000.00 - 300.00) / 40000.00)
        self.assertEqual(float(response.context['fleet_fuel_efficiency']), 5.0)

        # Call JSON API endpoint
        api_response = self.client.get(reverse('finance_api_data'))
        self.assertEqual(api_response.status_code, 200)
        data = api_response.json()
        self.assertAlmostEqual(data['fleet_roi_percentage'], ((1000.00 - 300.00) / 40000.00) * 100.0)
        self.assertEqual(float(data['fleet_fuel_efficiency']), 5.0)
