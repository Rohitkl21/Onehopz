# OneHopz — Antigravity Engineering & Agent Governance Rules

**Document Version:** 1.0.0  
**Status:** Mandatory Governance Specification  
**Target Audience:** Autonomous AI Agents (Antigravity), Core Engineers, and Code Reviewers  
**Authority:** Absolute — Overrides Any Ad-Hoc Implementation Preferences

---

## 1. Core Engineering Directives

### 1.1 Technology Stack & Architectural Boundaries
1. **Preserve the Fixed Stack**:
   - Backend: Python 3.12+ with Django REST Framework (DRF).
   - Database: PostgreSQL 16+ with PostGIS 3.4+.
   - Cache / Queue: Redis 7+ and Celery.
   - Frontend: Next.js 14+ (App Router), React 18+, TypeScript (Strict Mode).
   - Local Runtime: Docker Compose.
2. **Modular Monolith Discipline**:
   - Code must reside in the single repository under clear domain modules (`core.identity`, `core.merchants`, `core.catalog`, `core.holds`, `core.orders`, `modules.cinema`, etc.).
   - Cross-module logic must be mediated via public service interfaces or Python capability protocols. Never write direct raw SQL or ORM joins across private category tables from core domains.
   - Microservices are strictly prohibited at this stage.

### 1.2 Authoritative Database Correctness (The PostgreSQL Law)
1. **PostgreSQL is the Sole Authority**:
   - All reservation states, hold allocations, and financial records must be persisted and validated inside PostgreSQL ACID transactions.
   - **REDIS RULE**: Redis expiration notifications (`EXPIRE`, keyspace notifications) must **NEVER** be required for business correctness. Holds are authoritative only through PostgreSQL `expires_at` column checks inside `SELECT ... FOR UPDATE` database transactions. Redis is strictly an auxiliary cache and rate-limiting accelerator.
2. **Zero Double-Booking Guarantee**:
   - Every discrete inventory unit must have a PostgreSQL unique constraint on its allocation table.
   - Quota-based inventory must use atomic database increments/decrements with `CHECK` constraints.
   - Hold acquisitions must use row-level locking (`SELECT ... FOR UPDATE`).

### 1.3 Strict Typing & Code Quality
1. **Python / Django Backend**:
   - All Python code must have comprehensive type annotations and pass `mypy --strict`.
   - Django models must utilize django-stubs for type checking.
   - No untyped dictionaries for domain entities; utilize Python `@dataclass(frozen=True)` or Pydantic models for domain contracts.
2. **TypeScript / Next.js Frontend**:
   - TypeScript must run in `strict: true` mode in `tsconfig.json`.
   - The `any` type is strictly forbidden. Use `unknown` with runtime Zod schema parsing.
   - All API interactions must use Zod schemas to validate backend responses before rendering.

---

## 2. Security, Secrets & Environment Hygiene

1. **Zero Secrets in Git**:
   - Never commit API keys, database credentials, JWT secrets, private keys, or webhook secrets.
   - Provide clean `.env.example` templates with placeholder values.
2. **Never Invent Capabilities or Credentials**:
   - Do not hallucinate API endpoints, credentials, tax rates, regulatory approvals, or merchant agreements.
   - When an external integration is unconfirmed, mark it explicitly:  
     `[UNVERIFIED: Requires Provider Documentation / Legal Review]` and route execution through mock/sandbox adapters.
3. **Demo vs. Live Segregation**:
   - All transactional entities must include an `is_demo` boolean flag.
   - Demo transactions and synthetic jury test data must never touch live payment gateways or live financial ledgers.

---

## 3. Database Migration & Schema Hygiene

1. **Transactional Migrations**: All schema migrations must be written using Django’s migration framework with backwards-compatible steps.
2. **No Table Locks in Production**:
   - Adding a column with a default value must not rewrite the entire table (use PostgreSQL 11+ fast default feature).
   - Creating an index on high-volume tables (`orders`, `payment_attempts`, `holds`) must use `CONCURRENTLY` in production SQL.
3. **Irreversible Data Loss Prevention**:
   - Never execute `DROP TABLE` or `DROP COLUMN` in automated migrations without explicit, documented architectural approval.
   - Implement soft-deletes via `is_active` or explicit lifecycle states for business entities.

---

## 4. Verification Evidence & Definition of Done

1. **No Completion Without Proof**:
   - Never mark any milestone, task, or bugfix complete without attaching explicit verification evidence.
   - Acceptable evidence includes:
     - Full terminal output of passing unit/integration test suites (`pytest`).
     - Concurrency test logs demonstrating race-condition safety.
     - Build verification outputs (`npm run build`, `python manage.py check`).
     - Execution plans (`EXPLAIN ANALYZE`) for database queries.
2. **Mandatory Concurrency Tests**:
   - Any modification to inventory, holds, reservations, or payments requires an accompanying multi-threaded concurrency test proving race-condition immunity.

---

## 5. Deployment & Infrastructure Boundaries

1. **No Unauthorized Infrastructure Changes**:
   - Never modify cloud resources, production servers, or DNS records without explicit user sign-off.
   - Deployment to production is strictly manual and outside the scope of autonomous implementation loops.
2. **Strict Phase Adherence**:
   - Work strictly within the current assigned milestone.
   - Do not generate Milestone 1.2 application code, install packages, or initialize databases while Milestone 1.1 is active.
