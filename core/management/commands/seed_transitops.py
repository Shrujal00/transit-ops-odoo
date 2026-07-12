import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from core.models import Role, User, Vehicle, Driver, Trip, MaintenanceLog, FuelLog, Expense, AuditLog

class Command(BaseCommand):
    help = 'Seeds TransitOps database with realistic demo data'

    def handle(self, *args, **options):
        self.stdout.write('Clearing existing database records...')
        AuditLog.objects.all().delete()
        Expense.objects.all().delete()
        FuelLog.objects.all().delete()
        MaintenanceLog.objects.all().delete()
        Trip.objects.all().delete()
        Driver.objects.all().delete()
        User.objects.all().delete()
        Role.objects.all().delete()
        Vehicle.objects.all().delete()

        self.stdout.write('Creating Roles...')
        roles_data = [
            {'name': 'Fleet Manager', 'code': 'fleet_manager'},
            {'name': 'Driver', 'code': 'driver'},
            {'name': 'Safety Officer', 'code': 'safety_officer'},
            {'name': 'Financial Analyst', 'code': 'financial_analyst'},
        ]
        roles = {}
        for r_info in roles_data:
            role = Role.objects.create(name=r_info['name'], code=r_info['code'])
            roles[r_info['code']] = role

        from django.contrib.auth.models import Group, Permission
        from django.contrib.contenttypes.models import ContentType

        self.stdout.write('Creating Groups and Permissions...')
        group_permissions = {
            'fleet_manager': {
                'vehicle': ['add', 'change', 'delete', 'view'],
                'driver': ['view'],
                'trip': ['view'],
                'maintenancelog': ['add', 'change', 'delete', 'view'],
                'fuellog': ['view'],
                'expense': ['view'],
            },
            'driver': {
                'trip': ['add', 'change', 'delete', 'view'],
                'vehicle': ['view'],
                'driver': ['view'],
            },
            'safety_officer': {
                'driver': ['add', 'change', 'delete', 'view'],
                'maintenancelog': ['view'],
                'vehicle': ['view'],
                'trip': ['view'],
            },
            'financial_analyst': {
                'fuellog': ['add', 'change', 'delete', 'view'],
                'expense': ['add', 'change', 'delete', 'view'],
                'vehicle': ['view'],
                'driver': ['view'],
                'trip': ['view'],
                'maintenancelog': ['view'],
            }
        }

        model_classes = {
            'vehicle': Vehicle,
            'driver': Driver,
            'trip': Trip,
            'maintenancelog': MaintenanceLog,
            'fuellog': FuelLog,
            'expense': Expense
        }

        for role_code, specs in group_permissions.items():
            role_name = next(r['name'] for r in roles_data if r['code'] == role_code)
            group, created = Group.objects.get_or_create(name=role_name)
            
            perms_to_add = []
            for model_name, actions in specs.items():
                model_class = model_classes[model_name]
                ct = ContentType.objects.get_for_model(model_class)
                for action in actions:
                    codename = f"{action}_{model_name}"
                    try:
                        perm = Permission.objects.get(content_type=ct, codename=codename)
                        perms_to_add.append(perm)
                    except Permission.DoesNotExist:
                        pass
            
            group.permissions.set(perms_to_add)
            self.stdout.write(f"Configured group {group.name} with {len(perms_to_add)} permissions.")

        self.stdout.write('Creating Staff Users...')
        password = 'password123'
        
        manager_user = User.objects.create_superuser(
            email='manager@transitops.com',
            password=password,
            first_name='Admin',
            last_name='Manager',
            role=roles['fleet_manager']
        )
        safety_user = User.objects.create_user(
            email='safety@transitops.com',
            password=password,
            first_name='Sarah',
            last_name='Safety',
            role=roles['safety_officer']
        )
        finance_user = User.objects.create_user(
            email='finance@transitops.com',
            password=password,
            first_name='Fred',
            last_name='Finance',
            role=roles['financial_analyst']
        )

        # Assign staff users to their groups
        Group.objects.get(name='Fleet Manager').user_set.add(manager_user)
        Group.objects.get(name='Safety Officer').user_set.add(safety_user)
        Group.objects.get(name='Financial Analyst').user_set.add(finance_user)

        self.stdout.write('Creating Vehicles...')
        vehicles_data = [
            {'reg': 'TX-1002-A', 'make': 'Ford', 'model': 'F-350', 'year': 2021, 'cap': 3500, 'cost': 45000.00, 'status': 'Available', 'type': 'Van', 'region': 'North', 'odometer': 15000},
            {'reg': 'NY-5021-B', 'make': 'Mercedes-Benz', 'model': 'Sprinter', 'year': 2022, 'cap': 2500, 'cost': 55000.00, 'status': 'Available', 'type': 'Van', 'region': 'South', 'odometer': 8000},
            {'reg': 'CA-9874-C', 'make': 'Volvo', 'model': 'FH16 Truck', 'year': 2019, 'cap': 15000, 'cost': 140000.00, 'status': 'Available', 'type': 'Truck', 'region': 'East', 'odometer': 120000},
            {'reg': 'FL-4402-D', 'make': 'Scania', 'model': 'R450', 'year': 2020, 'cap': 18000, 'cost': 165000.00, 'status': 'Available', 'type': 'Truck', 'region': 'West', 'odometer': 95000},
            {'reg': 'IL-8912-E', 'make': 'Toyota', 'model': 'Hilux', 'year': 2021, 'cap': 1200, 'cost': 35000.00, 'status': 'Available', 'type': 'Truck', 'region': 'North', 'odometer': 42000},
            {'reg': 'TX-9901-F', 'make': 'Isuzu', 'model': 'NPR', 'year': 2018, 'cap': 4500, 'cost': 48000.00, 'status': 'In Shop', 'type': 'Truck', 'region': 'South', 'odometer': 60000},
            {'reg': 'NV-2311-G', 'make': 'Freightliner', 'model': 'Cascadia', 'year': 2023, 'cap': 20000, 'cost': 180000.00, 'status': 'Available', 'type': 'Truck', 'region': 'East', 'odometer': 35000},
            {'reg': 'AZ-7721-H', 'make': 'Mack', 'model': 'Anthem', 'year': 2021, 'cap': 19000, 'cost': 160000.00, 'status': 'Available', 'type': 'Truck', 'region': 'West', 'odometer': 55000},
            {'reg': 'OR-5509-I', 'make': 'Chevrolet', 'model': 'Express', 'year': 2017, 'cap': 2200, 'cost': 28000.00, 'status': 'Retired', 'type': 'Van', 'region': 'North', 'odometer': 180000},
            {'reg': 'WA-1088-J', 'make': 'Volvo', 'model': 'VNL 860', 'year': 2022, 'cap': 16000, 'cost': 155000.00, 'status': 'Available', 'type': 'Truck', 'region': 'South', 'odometer': 25000},
        ]
        
        vehicles = []
        for v in vehicles_data:
            vehicle = Vehicle.objects.create(
                registration_number=v['reg'],
                make=v['make'],
                model=v['model'],
                type=v['type'],
                region=v['region'],
                year=v['year'],
                capacity_kg=v['cap'],
                odometer=v['odometer'],
                acquisition_cost=v['cost'],
                status=v['status']
            )
            vehicles.append(vehicle)

        self.stdout.write('Creating Drivers and their Login Users...')
        drivers_data = [
            {'name': 'John Doe', 'email': 'john.doe@transitops.com', 'license': 'DL-887412-A', 'expiry_offset': 365, 'status': 'Available', 'cat': 'Class A', 'phone': '555-0101', 'score': 98},
            {'name': 'Jane Smith', 'email': 'jane.smith@transitops.com', 'license': 'DL-908124-B', 'expiry_offset': 730, 'status': 'Available', 'cat': 'Class B', 'phone': '555-0102', 'score': 95},
            {'name': 'Carlos Ruiz', 'email': 'carlos.ruiz@transitops.com', 'license': 'DL-441029-C', 'expiry_offset': 400, 'status': 'Available', 'cat': 'Class A', 'phone': '555-0103', 'score': 92},
            {'name': 'David Miller', 'email': 'david.miller@transitops.com', 'license': 'DL-110948-D', 'expiry_offset': -30, 'status': 'Suspended', 'cat': 'Class A', 'phone': '555-0104', 'score': 68},
            {'name': 'Linda Brown', 'email': 'linda.brown@transitops.com', 'license': 'DL-552910-E', 'expiry_offset': 150, 'status': 'Available', 'cat': 'Class B', 'phone': '555-0105', 'score': 99},
            {'name': 'James Wilson', 'email': 'james.wilson@transitops.com', 'license': 'DL-883719-F', 'expiry_offset': 600, 'status': 'Available', 'cat': 'Class A', 'phone': '555-0106', 'score': 90},
            {'name': 'Patricia Taylor', 'email': 'patricia.taylor@transitops.com', 'license': 'DL-729108-G', 'expiry_offset': 120, 'status': 'Off Duty', 'cat': 'Class B', 'phone': '555-0107', 'score': 97},
            {'name': 'Michael Thomas', 'email': 'michael.thomas@transitops.com', 'license': 'DL-389104-H', 'expiry_offset': 900, 'status': 'Available', 'cat': 'Class A', 'phone': '555-0108', 'score': 94},
            {'name': 'Barbara Anderson', 'email': 'barbara.anderson@transitops.com', 'license': 'DL-289103-I', 'expiry_offset': 300, 'status': 'Available', 'cat': 'Class B', 'phone': '555-0109', 'score': 91},
            {'name': 'Richard Jackson', 'email': 'richard.jackson@transitops.com', 'license': 'DL-993810-J', 'expiry_offset': 50, 'status': 'Available', 'cat': 'Class A', 'phone': '555-0110', 'score': 88},
        ]

        drivers = []
        today = timezone.now().date()
        driver_group = Group.objects.get(name='Driver')
        for idx, d in enumerate(drivers_data):
            d_user = User.objects.create_user(
                email=d['email'],
                password=password,
                first_name=d['name'].split()[0],
                last_name=d['name'].split()[1] if len(d['name'].split()) > 1 else '',
                role=roles['driver']
            )
            driver_group.user_set.add(d_user)
            driver = Driver.objects.create(
                user=d_user,
                name=d['name'],
                license_number=d['license'],
                license_category=d['cat'],
                license_expiry=today + datetime.timedelta(days=d['expiry_offset']),
                contact_number=d['phone'],
                safety_score=d['score'],
                status=d['status']
            )
            drivers.append(driver)

        self.stdout.write('Creating sample Trips...')
        trips_data = [
            {'src': 'Chicago, IL', 'dest': 'Dallas, TX', 'vehicle': vehicles[2], 'driver': drivers[2], 'cargo': 12000, 'rev': 3200.00, 'status': 'Ongoing', 'sched': today, 'dist': 950},
            {'src': 'Las Vegas, NV', 'dest': 'San Francisco, CA', 'vehicle': vehicles[6], 'driver': drivers[5], 'cargo': 15000, 'rev': 4500.00, 'status': 'Ongoing', 'sched': today, 'dist': 570},
            {'src': 'Houston, TX', 'dest': 'New Orleans, LA', 'vehicle': vehicles[0], 'driver': drivers[0], 'cargo': 2800, 'rev': 1200.00, 'status': 'Completed', 'sched': today - datetime.timedelta(days=3), 'end': timezone.now() - datetime.timedelta(days=2), 'dist': 350, 'end_odo': 15350, 'fuel': 130},
            {'src': 'New York, NY', 'dest': 'Boston, MA', 'vehicle': vehicles[1], 'driver': drivers[1], 'cargo': 2000, 'rev': 900.00, 'status': 'Completed', 'sched': today - datetime.timedelta(days=5), 'end': timezone.now() - datetime.timedelta(days=4), 'dist': 215, 'end_odo': 8215, 'fuel': 85},
            {'src': 'Seattle, WA', 'dest': 'Portland, OR', 'vehicle': vehicles[4], 'driver': drivers[4], 'cargo': 1000, 'rev': 500.00, 'status': 'Draft', 'sched': today + datetime.timedelta(days=2), 'dist': 180},
        ]

        for t in trips_data:
            trip = Trip(
                source=t['src'],
                destination=t['dest'],
                vehicle=t['vehicle'],
                driver=t['driver'],
                cargo_weight=t['cargo'],
                planned_distance=t['dist'],
                revenue=t['rev'],
                status=t['status'],
                scheduled_date=t['sched'],
                end_time=t.get('end'),
                end_odometer=t.get('end_odo'),
                fuel_consumed=t.get('fuel')
            )
            trip._bypass_date_validation = True
            trip.save()
            if trip.status == 'Ongoing':
                trip.vehicle.status = 'On Trip'
                trip.vehicle.save(update_fields=['status'])
                trip.driver.status = 'On Trip'
                trip.driver.save(update_fields=['status'])
            elif trip.status == 'Completed':
                trip.vehicle.odometer = trip.end_odometer
                trip.vehicle.save(update_fields=['odometer'])

        self.stdout.write('Creating sample Maintenance Logs...')
        # TX-9901-F (idx 5) is In Shop
        m_logs = [
            {'v': vehicles[5], 'desc': 'Transmission fluid replacement and gear adjustments', 'cost': 1250.00, 'start': today - datetime.timedelta(days=1), 'status': 'In Progress'},
            {'v': vehicles[0], 'desc': 'Routine oil change and multi-point inspection', 'cost': 150.00, 'start': today - datetime.timedelta(days=10), 'end': today - datetime.timedelta(days=10), 'status': 'Completed'},
            {'v': vehicles[1], 'desc': 'Front brake pads and rotor replacement', 'cost': 450.00, 'start': today - datetime.timedelta(days=15), 'end': today - datetime.timedelta(days=14), 'status': 'Completed'},
            {'v': vehicles[2], 'desc': 'Annual safety inspection and engine tuning', 'cost': 800.00, 'start': today - datetime.timedelta(days=30), 'end': today - datetime.timedelta(days=29), 'status': 'Completed'},
        ]
        for m in m_logs:
            log = MaintenanceLog(
                vehicle=m['v'],
                description=m['desc'],
                cost=m['cost'],
                start_date=m['start'],
                end_date=m.get('end'),
                status=m['status']
            )
            log._bypass_date_validation = True
            log.save()

        self.stdout.write('Creating sample Fuel Logs...')
        fuel_logs = [
            {'v': vehicles[2], 'liters': 150.00, 'cost': 225.00, 'date': today - datetime.timedelta(days=2)},
            {'v': vehicles[6], 'liters': 180.00, 'cost': 270.00, 'date': today - datetime.timedelta(days=1)},
            {'v': vehicles[0], 'liters': 45.00, 'cost': 67.50, 'date': today - datetime.timedelta(days=3)},
            {'v': vehicles[1], 'liters': 55.00, 'cost': 82.50, 'date': today - datetime.timedelta(days=4)},
            {'v': vehicles[0], 'liters': 40.00, 'cost': 60.00, 'date': today - datetime.timedelta(days=8)},
        ]
        for f in fuel_logs:
            log = FuelLog(
                vehicle=f['v'],
                liters=f['liters'],
                cost=f['cost'],
                date=f['date']
            )
            log._bypass_date_validation = True
            log.save()

        self.stdout.write('Creating sample Expenses...')
        expenses = [
            {'v': vehicles[2], 'amount': 150.00, 'category': 'Tolls', 'desc': 'Cross-country tolls CA-TX route', 'date': today - datetime.timedelta(days=2)},
            {'v': vehicles[6], 'amount': 75.00, 'category': 'Tolls', 'desc': 'State line turnpike toll', 'date': today - datetime.timedelta(days=1)},
            {'v': vehicles[0], 'amount': 1200.00, 'category': 'Insurance', 'desc': 'Semi-annual liability insurance premium', 'date': today - datetime.timedelta(days=20)},
            {'v': vehicles[1], 'amount': 250.00, 'category': 'Permits', 'desc': 'Oversize load state permit fee', 'date': today - datetime.timedelta(days=5)},
        ]
        for e in expenses:
            exp = Expense(
                vehicle=e['v'],
                amount=e['amount'],
                category=e['category'],
                description=e['desc'],
                date=e['date']
            )
            exp._bypass_date_validation = True
            exp.save()

        self.stdout.write('Creating initial Audit Logs...')
        # Write generic audit log entries for vehicle status changes
        v_content_type = ContentType.objects.get_for_model(Vehicle)
        
        # Log vehicle TX-9901-F going In Shop
        AuditLog.objects.create(
            user=manager_user,
            content_type=v_content_type,
            object_id=vehicles[5].id,
            action='Status Change',
            old_status='Available',
            new_status='In Shop',
            details='Vehicle sent to shop due to transmission warnings.'
        )
        # --- Bulk Operational Seeding (1000s of data) ---
        import random
        from django.contrib.auth.hashers import make_password

        # Bulk Vehicles
        bulk_vehicles = []
        makes = ['Ford', 'Mercedes-Benz', 'Volvo', 'Scania', 'Toyota', 'Isuzu', 'Freightliner', 'Mack', 'Chevrolet']
        models_map = {
            'Ford': ['F-350', 'Transit', 'F-150'],
            'Mercedes-Benz': ['Sprinter', 'Actros', 'Atego'],
            'Volvo': ['FH16 Truck', 'VNL 860', 'FM'],
            'Scania': ['R450', 'G-Series', 'P-Series'],
            'Toyota': ['Hilux', 'HiAce', 'Land Cruiser'],
            'Isuzu': ['NPR', 'FTS', 'FTR'],
            'Freightliner': ['Cascadia', 'M2 106', 'Coronado'],
            'Mack': ['Anthem', 'Granite', 'Pinnacle'],
            'Chevrolet': ['Express', 'Silverado', 'Low Cab Forward']
        }
        types = ['Van', 'Truck', 'Trailer']
        regions = ['North', 'South', 'East', 'West']
        v_statuses = ['Available', 'On Trip', 'In Shop', 'Retired']

        self.stdout.write('Generating 1000 bulk Vehicles...')
        for i in range(1000):
            make = random.choice(makes)
            model = random.choice(models_map[make])
            reg = f"{random.choice(['TX','NY','CA','FL','IL','NV','AZ','OR','WA'])}-{random.randint(1000, 9999)}-{random.choice(['A','B','C','D','E','F','G','H','I','J'])}"
            bulk_vehicles.append(Vehicle(
                registration_number=reg,
                make=make,
                model=model,
                type=random.choice(types),
                region=random.choice(regions),
                year=random.randint(2015, 2024),
                capacity_kg=random.randint(1000, 25000),
                odometer=random.randint(5000, 250000),
                acquisition_cost=random.randint(20000, 190000),
                status=random.choice(v_statuses)
            ))
        Vehicle.objects.bulk_create(bulk_vehicles, ignore_conflicts=True)
        vehicles_all = list(Vehicle.objects.all())

        # Bulk Driver Users
        hashed_password = make_password(password)
        bulk_users = []
        first_names = ['John', 'Jane', 'Carlos', 'David', 'Linda', 'James', 'Patricia', 'Michael', 'Barbara', 'Richard', 'Robert', 'Mary', 'William', 'Elizabeth', 'Joseph', 'Susan', 'Thomas', 'Jessica']
        last_names = ['Doe', 'Smith', 'Ruiz', 'Miller', 'Brown', 'Wilson', 'Taylor', 'Thomas', 'Anderson', 'Jackson', 'White', 'Harris', 'Martin', 'Thompson', 'Garcia', 'Martinez', 'Robinson', 'Clark']
        
        self.stdout.write('Generating 1000 bulk Users...')
        for i in range(1000):
            fname = random.choice(first_names)
            lname = random.choice(last_names)
            email = f"driver_{i}_{random.randint(10000,99999)}@transitops.com"
            bulk_users.append(User(
                email=email,
                password=hashed_password,
                first_name=fname,
                last_name=lname,
                role=roles['driver']
            ))
        User.objects.bulk_create(bulk_users, ignore_conflicts=True)
        drivers_users = list(User.objects.filter(role=roles['driver']))

        # Bulk M2M User-Group Relationships
        UserGroupThrough = User.groups.through
        through_objs = []
        driver_group_id = driver_group.id
        for u in drivers_users:
            through_objs.append(UserGroupThrough(user_id=u.id, group_id=driver_group_id))
        UserGroupThrough.objects.bulk_create(through_objs, ignore_conflicts=True)

        # Bulk Driver Profiles
        bulk_drivers = []
        driver_statuses = ['Available', 'On Trip', 'Off Duty', 'Suspended']
        license_categories = ['Class A', 'Class B', 'Class C']
        
        self.stdout.write('Generating 1000 bulk Drivers...')
        existing_emails = set(d['email'] for d in drivers_data)
        for u in drivers_users:
            if u.email in existing_emails:
                continue
            lic = f"DL-{random.randint(100000, 999999)}-{random.choice(['A','B','C','D'])}"
            bulk_drivers.append(Driver(
                user=u,
                name=f"{u.first_name} {u.last_name}",
                license_number=lic,
                license_category=random.choice(license_categories),
                license_expiry=today + datetime.timedelta(days=random.randint(-30, 1000)),
                contact_number=f"555-{random.randint(1000, 9999)}",
                safety_score=random.randint(60, 100),
                status=random.choice(driver_statuses)
            ))
        Driver.objects.bulk_create(bulk_drivers, ignore_conflicts=True)
        drivers_all = list(Driver.objects.all())

        # Bulk Trips
        bulk_trips = []
        cities = ['New York, NY', 'Chicago, IL', 'Houston, TX', 'Phoenix, AZ', 'Philadelphia, PA', 'San Antonio, TX', 'San Diego, CA', 'Dallas, TX', 'San Jose, CA', 'Austin, TX', 'Jacksonville, FL', 'Fort Worth, TX', 'Columbus, OH', 'Charlotte, NC', 'San Francisco, CA', 'Indianapolis, IN', 'Seattle, WA', 'Denver, CO']
        trip_statuses = ['Draft', 'Ongoing', 'Completed', 'Cancelled']
        
        self.stdout.write('Generating 1500 bulk Trips...')
        for i in range(1500):
            src = random.choice(cities)
            dest = random.choice([c for c in cities if c != src])
            veh = random.choice(vehicles_all)
            drv = random.choice(drivers_all)
            status = random.choice(trip_statuses)
            sched = today + datetime.timedelta(days=random.randint(-60, 60))
            
            end_t = None
            end_o = None
            fuel = None
            if status == 'Completed':
                end_t = timezone.now() - datetime.timedelta(days=random.randint(1, 60))
                end_o = veh.odometer + random.randint(100, 1000)
                fuel = random.randint(10, 150)
                
            bulk_trips.append(Trip(
                source=src,
                destination=dest,
                vehicle=veh,
                driver=drv,
                cargo_weight=random.randint(500, max(2000, veh.capacity_kg)),
                planned_distance=random.randint(50, 1500),
                revenue=random.randint(200, 5000),
                status=status,
                scheduled_date=sched,
                end_time=end_t,
                end_odometer=end_o,
                fuel_consumed=fuel
            ))
        Trip.objects.bulk_create(bulk_trips)

        # Bulk Maintenance Logs
        bulk_maintenance = []
        maintenance_statuses = ['Scheduled', 'In Progress', 'Completed']
        maintenance_descs = [
            'Routine engine oil change and filter replacement',
            'Brake pads and rotor replacement with multi-point check',
            'Radiator coolant flush and transmission fluid check',
            'Tire rotation, balancing, and alignment adjustments',
            'Electrical troubleshooting and alternator replacement',
            'Suspension shock absorber and strut replacement',
            'Windshield wiper replacement and fluid top-up',
            'Air filter and cabin filter replacement service'
        ]
        
        self.stdout.write('Generating 1200 bulk Maintenance Logs...')
        for i in range(1200):
            veh = random.choice(vehicles_all)
            start = today + datetime.timedelta(days=random.randint(-120, 10))
            status = random.choice(maintenance_statuses)
            end = None
            if status == 'Completed':
                end = start + datetime.timedelta(days=random.randint(1, 5))
                
            bulk_maintenance.append(MaintenanceLog(
                vehicle=veh,
                description=random.choice(maintenance_descs),
                cost=random.randint(50, 3000),
                start_date=start,
                end_date=end,
                status=status
            ))
        MaintenanceLog.objects.bulk_create(bulk_maintenance)

        # Bulk Fuel Logs
        bulk_fuel = []
        self.stdout.write('Generating 2000 bulk Fuel Logs...')
        for i in range(2000):
            veh = random.choice(vehicles_all)
            bulk_fuel.append(FuelLog(
                vehicle=veh,
                liters=random.randint(20, 200),
                cost=random.randint(30, 400),
                date=today - datetime.timedelta(days=random.randint(1, 180))
            ))
        FuelLog.objects.bulk_create(bulk_fuel)
        
        # Bulk Expenses
        bulk_expenses = []
        categories = ['Tolls', 'Insurance', 'Permits', 'Equipment', 'Other']
        expense_descs = {
            'Tolls': 'Highway toll fee on delivery route',
            'Insurance': 'Monthly insurance premium portion',
            'Permits': 'State crossing permit fee',
            'Equipment': 'Cabin maintenance tools and cleaning kit',
            'Other': 'Miscellaneous operational expense'
        }
        
        self.stdout.write('Generating 1500 bulk Expenses...')
        for i in range(1500):
            veh = random.choice(vehicles_all)
            cat = random.choice(categories)
            bulk_expenses.append(Expense(
                vehicle=veh,
                amount=random.randint(10, 1500),
                category=cat,
                description=expense_descs[cat],
                date=today - datetime.timedelta(days=random.randint(1, 180))
            ))
        Expense.objects.bulk_create(bulk_expenses)

        self.stdout.write(self.style.SUCCESS('Successfully seeded TransitOps database with demo data!'))
        self.stdout.write('Manager Login: manager@transitops.com (password: password123)')
        self.stdout.write('Safety Login: safety@transitops.com (password: password123)')
        self.stdout.write('Finance Login: finance@transitops.com (password: password123)')
        self.stdout.write('Driver Logins: e.g. john.doe@transitops.com (password: password123)')
