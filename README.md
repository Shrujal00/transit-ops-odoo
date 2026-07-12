# TransitOps ERP 🚚📊

TransitOps ERP is a high-performance, modern Fleet Management and Logistics Operations ERP built with Python and Django. Designed for speed, security, and high visual appeal, it features strict Role-Based Access Control (RBAC), customized data analytics, and operational quick action shortcuts.

---

## 🌟 Key Features

### 1. 👥 Role-Based Access Control (RBAC)
Dedicated dashboards and permission constraints for four key operational profiles:
- **Fleet Manager**: Full CRUD on vehicles, odometer updates, and creation/closure of maintenance tickets.
- **Safety Officer**: Driver registry CRUD, license expiry tracking, and driver suspension controls.
- **Financial Analyst**: Access to Expense auditing, ROI dashboards, and tabular operational reports with export support.
- **Driver**: Quick access to assigned trips, dispatching, fuel purchase logging, and trip completion updates.

### 2. 🌙 Theme Management (Light / Dark Mode)
- **Instant Persistence**: A responsive sun/moon toggle button in the top bar. Themes are persisted across sessions in `localStorage`.
- **Contrast Overrides**: Tailored dark theme variables covering all page layouts, tables, inputs, hovers, navigation chips, and buttons.

### 3. 📈 Custom Analytics Dashboard
Interactive, real-time widgets driven by Chart.js:
- **Revenue vs Cost Trend**: Weekly analysis for the last 8 weeks (Cost in red, Revenue in green) featuring Indian Rupee (`₹`) scale formatting.
- **Trip Analytics**: Horizontal bar charts displaying trip status distributions.
- **Fuel Efficiency**: Daily area chart tracking total liters of fuel consumed.
- **Top Driver Radar**: Comparative radar chart mapping safety scores vs completed trips.

### 4. 📋 Performance Reports & Exports
- **Tables**: Sectioned tables for Vehicle and Driver Performance displaying trips, cost breakdowns, total revenue, and computed ROI ratios.
- **Exports**: Instant file downloads in CSV and print-ready HTML/PDF formatting (`window.print()`).

### 5. ⚡ One-Click Operational Quick Actions
Cut down click workflows with direct action shortcuts:
- **`🔧 Service`**: Sent available vehicles directly to the shop, auto-generating active maintenance logs.
- **`✅ Resolve`**: Close active maintenance tickets and return vehicles to the available registry.
- **`🚀 Dispatch`**: Immediately set draft trips to ongoing state, setting assigned drivers and vehicles to trip status.
- **`✅ Complete`**: Instantly resolve ongoing trips with auto-estimated odometer distance and fuel averages.

---

## 🛠️ Technology Stack
- **Backend**: Python 3.12, Django 6.0
- **Frontend**: HTML5, custom Vanilla CSS3 (no external styling framework dependencies), Javascript (ES6)
- **Charts**: Chart.js
- **Database**: SQLite3

---

## 🚀 Getting Started

### 1. Clone & Setup Environment
Ensure Python 3.12+ is installed on your machine.
```bash
# Apply database migrations
python manage.py migrate
```

### 2. Seed Database with High-Volume Data
TransitOps features a high-speed database seeding command that utilizes Django bulk operations to write **1000s of realistic, profitable mock records** in seconds:
```bash
python manage.py seed_transitops
```

### 3. Launch Development Server
```bash
python manage.py runserver
```
Visit the local server in your browser at [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

---

## 👤 Seed User Credentials

All passwords are set to `password123`:
* **Admin / Fleet Manager**: `manager@transitops.com`
* **Safety Officer**: `safety@transitops.com`
* **Financial Analyst**: `finance@transitops.com`
* **Driver profile login**: `john.doe@transitops.com` (or any generated profile user `driver_N_XXXX@transitops.com`)

---

## 🧪 Testing Suite

Run the automated test suite containing RBAC guard verifications and quick-action workflow assertions:
```bash
python manage.py test
```
