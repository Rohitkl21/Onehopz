# OneHopz — Perishable Inventory & Dynamic Yield Marketplace

**Status:** Milestone 1.3 Development Scaffold Active  
**Architecture:** Modular Monolith with Polymorphic Category Adapters  
**Backend:** Python 3.12 + Django REST Framework + Celery  
**Database:** PostgreSQL 16 with PostGIS 3.4  
**Cache & Broker:** Redis 7  
**Frontend:** Next.js 14 (App Router) + TypeScript (Strict Mode) + React 18  
**Containerization:** Docker Compose

---

## 1. Project Overview

OneHopz is a unified multi-category marketplace engineered to recover revenue from unsold, highly perishable, time-sensitive inventory across seven core verticals:
1. **Cinema**: Showtime seats with dynamic yield time-decay.
2. **Restaurants**: Off-peak table reservations and shoulder-hour dining slots.
3. **Surplus Food**: End-of-day surplus batches, bakery Magic Bags, and FSSAI-compliant perishable pickups.
4. **Hotels**: Same-day room night liquidation and night-audit cutoffs.
5. **Salons & Spas**: Idle chair liquidation and composite stylist/time-slot scheduling.
6. **Events**: Tiered ticket passes and burst-concurrency flash sales.
7. **Travel**: Last-hour bus berths and airline seats with PNR issuing.

> [!IMPORTANT]
> **Milestone 1.3 Notice**: This repository currently contains the initial development environment, repository scaffolding, code quality configurations, and diagnostic health check endpoints. **No marketplace business functionality (orders, payments, holds, inventory bookings) has been implemented yet.**

---

## 2. Repository Structure

```
D:\Onehopz\
├── .editorconfig          # Cross-editor formatting consistency
├── .env.example           # Sanitized environment template (no real credentials)
├── .gitignore             # Comprehensive secrets & artifact exclusion
├── docker-compose.yml     # Containerized orchestration for all platform services
├── README.md              # Project onboarding and developer workflow guide
│
├── backend/               # Django REST Framework backend service
│   ├── apps/              # Modular Django domain apps
│   │   └── core/          # Core scaffold & health check endpoints
│   ├── config/            # Django project settings, WSGI/ASGI, and Celery app
│   ├── tests/             # Backend test suite (pytest)
│   ├── Dockerfile         # Python 3.12 container specification
│   ├── manage.py          # Django administrative CLI
│   ├── pyproject.toml     # Ruff, Mypy, and Pytest configuration
│   ├── requirements.txt   # Production dependencies
│   └── requirements-dev.txt # Development & testing dependencies
│
├── frontend/              # Next.js 14 App Router frontend service
│   ├── src/
│   │   ├── app/           # Next.js App Router (layout, page, styles)
│   │   └── components/    # Reusable UI components (HealthStatus diagnostics)
│   ├── Dockerfile         # Node.js 20 container specification
│   ├── next.config.mjs    # Next.js configuration
│   ├── package.json       # Frontend scripts and dependencies
│   ├── tsconfig.json      # TypeScript strict mode configuration
│   ├── .eslintrc.json     # ESLint configuration
│   └── .prettierrc        # Prettier formatting rules
│
└── docs/                  # Master Technical Documentation & Architecture Blueprints
    ├── ANTIGRAVITY_RULES.md          # Autonomous agent governance rules
    ├── API_CONTRACTS.md              # RESTful API specifications
    ├── BUSINESS_MODULES.md           # 7-vertical deep dive specifications
    ├── DATA_MODEL.md                 # PostgreSQL relational schema & constraints
    ├── IMPLEMENTATION_ROADMAP.md     # Level & Milestone delivery plan
    ├── PRODUCT_REQUIREMENTS.md       # Product requirements document (PRD)
    ├── SECURITY_AND_COMPLIANCE.md    # Security, RBAC & Indian statutory matrix
    ├── SYSTEM_ARCHITECTURE.md        # Monolith architecture & concurrency proofs
    └── TEST_STRATEGY.md              # Testing pyramid & edge case scenarios
```

---

## 3. Prerequisites

To develop on OneHopz locally, ensure the following are installed:
- **Operating System**: Windows 10/11, macOS, or Linux.
- **Git**: `>= 2.40`
- **Docker & Docker Compose**: Docker Desktop with Compose v2+
- **Python**: `3.12.x` (for local development outside containers)
- **Node.js & npm**: Node `>= 20.x` and npm `>= 10.x`

---

## 4. Local Development Setup (Windows PowerShell)

### Step 1: Environment Configuration
Copy the template environment file to `.env`:
```powershell
Copy-Item .env.example .env
```
> [!WARNING]
> Never commit `.env` or files containing secrets to version control. The `.gitignore` file is strictly configured to prevent credential exposure.

### Step 2: Running with Docker Compose (Recommended)

1. **Start all services** (PostgreSQL, Redis, Django API, Celery Worker, Celery Beat, Next.js):
   ```powershell
   docker compose up --build
   ```

2. **Start in detached mode** (background):
   ```powershell
   docker compose up -d
   ```

3. **Inspect running services & health**:
   ```powershell
   docker compose ps
   ```

4. **View live logs**:
   ```powershell
   # All services
   docker compose logs -f

   # Backend only
   docker compose logs -f backend

   # Celery worker only
   docker compose logs -f celery_worker
   ```

5. **Stop all services safely** (preserves database volume):
   ```powershell
   docker compose down
   ```
   > [!CAUTION]
   > Do **NOT** run `docker compose down -v` during standard development; doing so deletes persistent PostgreSQL database volumes.

---

## 5. Resource-Constrained Local Development (Running Bare-Metal)

If your machine has limited memory or Docker Desktop is unavailable, you can run the backend and frontend directly on the host:

### Running the Backend (Host Python 3.12)
```powershell
cd D:\Onehopz\backend

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# Install dependencies (if not already installed)
pip install -r requirements-dev.txt

# Run database migrations (or use SQLite fallback in local dev)
python manage.py migrate

# Run the development server
python manage.py runserver 127.0.0.1:8000
```
Backend Health Check URL: `http://127.0.0.1:8000/api/health/`

### Running the Frontend (Host Node.js 20+)
```powershell
cd D:\Onehopz\frontend

# Install dependencies
npm install

# Start the Next.js development server
npm run dev
```
Frontend URL: `http://localhost:3000`

---

## 6. Running Tests & Code Quality Checks

### Backend Quality Suite
From `D:\Onehopz\backend`:
```powershell
# Run automated tests
pytest

# Run Ruff linter
ruff check .

# Run Ruff formatter check
ruff format --check .

# Run Mypy static type checker
mypy apps config
```

### Frontend Quality Suite
From `D:\Onehopz\frontend`:
```powershell
# Run ESLint
npm run lint

# Run TypeScript compilation check
npm run typecheck

# Run Prettier code formatting check
npm run format:check
```

---

## 7. Diagnostics & Troubleshooting

| Problem | Root Cause | Solution |
|---|---|---|
| `docker compose` fails with `pipe/dockerDesktopLinuxEngine` not found | Docker Desktop service is stopped or not running. | Start Docker Desktop application from the Start menu and wait for the whale icon to stabilize. |
| PostGIS extension fails in local host development | Local host Python lacks native GDAL/GEOS C-libraries. | The backend automatically detects GDAL; run inside Docker (`postgis/postgis:16-3.4`) for full spatial features. |
| Port `5432` or `6379` already in use | Another local PostgreSQL or Redis instance is running. | Stop local services, or adjust `POSTGRES_PORT` / `REDIS_PORT` in `.env`. |
| Celery worker cannot connect to broker | Redis service is offline or unreachable. | Verify Redis status via `docker compose ps redis` or run `redis-cli ping`. |

---

## 8. Milestone Roadmap Alignment

- **Milestone 1.1**: Master Product Requirements Specification (`docs/`) — Completed.
- **Milestone 1.2**: System Architecture & Relational Data Model Finalization — Completed.
- **Milestone 1.3**: Development Environment & Repository Setup — **Current Milestone**.
- **Milestone 1.4**: Core Identity, RBAC & Multi-Tenant Merchant Model — Next.
