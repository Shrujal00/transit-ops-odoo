from django.test import TestCase, TransactionTestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth.models import Group
import datetime
import threading
from .models import Role, User, Vehicle, Driver, Trip, MaintenanceLog, AuditLog

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
        # Create roles
        self.fm_role = Role.objects.create(name="Fleet Manager", code="fleet_manager")
        self.driver_role = Role.objects.create(name="Driver", code="driver")
        
        # Create Groups
        self.fm_group = Group.objects.create(name="Fleet Manager")
        self.driver_group = Group.objects.create(name="Driver")
        
        # Create Users
        self.manager_user = User.objects.create_user(email="manager@test.com", password="password123", role=self.fm_role)
        self.manager_user.groups.add(self.fm_group)
        
        self.driver_user_1 = User.objects.create_user(email="driver1@test.com", password="password123", role=self.driver_role)
        self.driver_user_1.groups.add(self.driver_group)

        self.driver_user_2 = User.objects.create_user(email="driver2@test.com", password="password123", role=self.driver_role)
        self.driver_user_2.groups.add(self.driver_group)

        # Create Vehicles & Drivers
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
        # Setup roles, groups, manager user
        self.fm_role = Role.objects.create(name="Fleet Manager", code="fleet_manager")
        self.fm_group = Group.objects.create(name="Fleet Manager")
        self.manager_user = User.objects.create_user(email="manager@test.com", password="password123", role=self.fm_role)
        self.manager_user.groups.add(self.fm_group)
        
        # Resources
        self.vehicle = Vehicle.objects.create(
            registration_number="TX-5544-M", make="Toyota", model="Hilux", year=2021, capacity_kg=1200, acquisition_cost=35000.00
        )
        self.driver = Driver.objects.create(
            name="Bob Driver", license_number="LIC-Bob", license_expiry=timezone.now().date() + datetime.timedelta(days=100)
        )
        
        # Test client login
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
        # Attempt to dispatch
        response = self.client.post(reverse('trip_dispatch', kwargs={'pk': trip.pk}))
        trip.refresh_from_db()
        self.assertEqual(trip.status, 'Draft') # remains Draft because driver license is expired

    def test_dispatch_state_transition(self):
        trip = Trip.objects.create(
            source="A", destination="B", vehicle=self.vehicle, driver=self.driver, cargo_weight=1000, scheduled_date=timezone.now().date()
        )
        # Dispatch
        response = self.client.post(reverse('trip_dispatch', kwargs={'pk': trip.pk}))
        trip.refresh_from_db()
        self.vehicle.refresh_from_db()
        self.driver.refresh_from_db()
        
        self.assertEqual(trip.status, 'Ongoing')
        self.assertEqual(self.vehicle.status, 'On Trip')
        self.assertEqual(self.driver.status, 'On Trip')

        # Complete
        response = self.client.post(reverse('trip_complete', kwargs={'pk': trip.pk}))
        trip.refresh_from_db()
        self.vehicle.refresh_from_db()
        self.driver.refresh_from_db()
        
        self.assertEqual(trip.status, 'Completed')
        self.assertEqual(self.vehicle.status, 'Available')
        self.assertEqual(self.driver.status, 'Available')
        self.assertIsNotNone(trip.end_time)

    def test_maintenance_flow_transitions(self):
        # Create maintenance log
        log = MaintenanceLog.objects.create(
            vehicle=self.vehicle, description="Repair radiator", cost=150.00, start_date=timezone.now().date(), status="In Progress"
        )
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, 'In Shop')

        # Complete maintenance
        log.status = "Completed"
        log.save()
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, 'Available')


class ConcurrencyLockingTest(TransactionTestCase):
    def setUp(self):
        # Setup roles, groups, manager user
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
        
        def dispatch_action(trip_id):
            client = self.client_class()
            client.login(email="manager@test.com", password="password123")
            response = client.post(reverse('trip_dispatch', kwargs={'pk': trip_id}))
            messages_list = list(response.wsgi_request._messages)
            for msg in messages_list:
                if "failed" in msg.message or "not available" in msg.message:
                    errors.append(msg.message)

        # Spawn two threads trying to dispatch separate trips with the SAME vehicle simultaneously
        t1 = threading.Thread(target=dispatch_action, args=(self.trip_1.id,))
        t2 = threading.Thread(target=dispatch_action, args=(self.trip_2.id,))

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, 'On Trip')
        
        # Assert that at least one error message was generated due to the double booking lock
        self.assertTrue(len(errors) >= 1)
        self.assertTrue(any("not available" in err for err in errors))
