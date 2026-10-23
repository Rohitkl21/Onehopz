# OneHopz — Implementation Roadmap & Delivery Plan

**Document Version:** 1.2.0  
**Status:** Approved Delivery Blueprint (Milestone 1.7 Planning Reconciled)  
**Organization Structure:** 8-Level Roadmap & Milestones (Strictly Milestone-Driven, No Arbitrary Week Estimates)  
**Governance:** Strict Quality Gates with Mandatory Verification Evidence

---

## 1. Roadmap Architecture: 8-Level Framework & Milestones

The delivery blueprint is organized across an **8-Level Roadmap**, reconciling core engine foundations, domain modules, financial operations, and jury demonstrations:

```
LEVEL 1: ARCHITECTURE AND PROJECT FOUNDATION
  ├── Milestone 1.1: Master Product Requirements Specification [COMPLETED]
  ├── Milestone 1.2: Finalize System Architecture and Data Model [COMPLETED]
  └── Milestone 1.3: Development Environment and Repository Setup [COMPLETED]

LEVEL 2: SHARED PLATFORM CORE
  ├── Milestone 1.4: Core Identity, RBAC & Multi-Tenant Merchant Model [COMPLETED]
  │     └── Milestone 1.4.1: Authentication Security Hardening [COMPLETED]
  ├── Milestone 1.5: Core Catalog, Offer Specifications & Inventory Domain [COMPLETED]
  │     └── Milestone 1.5.1: Catalog and Offer Security/Integrity Fixes [COMPLETED]
  ├── Milestone 1.6: Authoritative Hold Engine & ACID Concurrency Core [COMPLETED]
  └── Core Orders & Order-Hold Conversion Engine [IN SCOPE: M1.7]

LEVEL 3: SEVEN BUSINESS MODULES
  ├── Milestone 1.8a: Cinema Screens, Seat Grid & Showtimes
  ├── Milestone 1.8b: Restaurant Tables, Dining Shifts & Covers
  ├── Milestone 1.8c: Surplus Food Batches & Pickup Windows
  ├── Milestone 2.1: Hotel Room-Night & Inventory Calendar Module
  ├── Milestone 2.2: Salon Stylist Scheduling & Service Graph Module
  ├── Milestone 2.3: Event Tiering & Ticket Pass Generation Module
  └── Milestone 2.4: Travel Routing, PNR Engine & Mock Aggregator Adapter

LEVEL 4: PAYMENTS AND FINANCIAL OPERATIONS
  ├── Milestone 1.7: Payment Gateway Orchestrator & Escrow Webhook Pipeline [NEXT MILESTONE]
  │     ├── Gateway Adapters (Cashfree, Razorpay, MockGateway)
  │     ├── HMAC-SHA256 Webhook Ingress & Idempotent Deduplication
  │     ├── Double-Entry Immutable Append-Only Ledger (Triggers & Balances)
  │     └── Automated Refund Saga for Orphaned Payments / Hold Expirations
  └── Milestone 4.3: Merchant Settlement Batches, Tax Withholding (TCS/TDS) & Bank Payouts

LEVEL 5: APPLICATIONS AND OPERATIONS
  ├── Milestone 3.1: Unified Customer Web Portal (Next.js Multi-Vertical Flow)
  ├── Milestone 3.2: Merchant Web Portal & Mobile-Responsive QR Scanner
  └── Milestone 3.3: Admin Portal, Settlement Dashboard & Reconciliation Ledger

LEVEL 6: INTEGRATIONS AND AUTOMATION
  ├── Dynamic QR Digital Passes & TOTP Gate Redemption
  ├── Transactional Messaging Outbox (SMS/Email/WhatsApp)
  └── Live External GDS & Cinema POS Connectors

LEVEL 7: SECURITY, RELIABILITY AND PERFORMANCE
  ├── Milestone 4.1: Security, Penetration Testing & DPDP Privacy Hardening
  └── Milestone 4.4: High-Scale Concurrency Benchmarking & Production Launch

LEVEL 8: DEPLOYMENT AND JURY DEMONSTRATION
  ├── Milestone 3.4: Jury Demonstration Suite & Synthetic Scenario Injector
  └── Milestone 4.2: Payment Partner & Nodal Bank Certification
```

---

## 2. Level 1: Architecture, Foundation & Core Engine

### Milestone 1.1: Master Product Requirements Specification
- **Status**: Completed.
- **Deliverables**: Comprehensive `/docs` directory containing initial product specifications, operational journeys, and cross-category divergence models.
- **Verification Evidence**: Complete set of 9 specification documents in `D:\Onehopz\docs`.

### Milestone 1.2: Finalize System Architecture and Data Model
- **Status**: Completed (Current Milestone).
- **Deliverables**:
  - Modular monolith boundaries and polymorphic `InventoryCapability` interface specifications.
  - Authoritative PostgreSQL relational schema covering shared core and all seven vertical modules.
  - Concurrency control specifications and transaction-level proofs for all six contention scenarios.
  - Double-entry ledger architecture with database-level append-only immutability.
  - Integration adapter specifications distinguishing Mock and Live providers.
- **Verification Evidence**: Updated `SYSTEM_ARCHITECTURE.md`, `DATA_MODEL.md`, `API_CONTRACTS.md`, `BUSINESS_MODULES.md`, `TEST_STRATEGY.md`, `SECURITY_AND_COMPLIANCE.md`, and `IMPLEMENTATION_ROADMAP.md`.

### Milestone 1.3: Development Environment and Repository Setup
- **Status**: Completed.
- **Deliverables**:
  - Root monorepo structure with Next.js frontend (`/frontend`) and Django backend (`/backend`).
  - Standardized `docker-compose.yml` configuring PostgreSQL 16 with PostGIS 3.4, Redis 7, Django API, Celery worker, Celery beat, and Next.js.
  - Static analysis, linters, formatters, and typing configurations (`ruff`, `mypy`, `eslint`, `prettier`).
  - Environment templates (`.env.example`) with zero committed credentials.
- **Verification Evidence**: Clean container builds, green test runs, and initial repository scaffold.

### Milestone 1.4: Core Identity, RBAC & Multi-Tenant Merchant Model
- **Status**: Completed (with Milestone 1.4.1 Security Hardening).
- **Deliverables**:
  - `apps.identity` Django app with custom `User`, `UserRole`, and `RefreshToken` models.
  - `apps.merchants` Django app with `Merchant`, `MerchantMembership`, `Outlet`, and `OutletStaff` models.
  - JWT authentication endpoints with rotating HttpOnly refresh cookies, CSRF validation, and replay detection.
- **Verification Evidence**: Automated pytest suite and live PostgreSQL 16 audit passing.

### Milestone 1.5: Core Catalog, Offer Specifications & Inventory Domain
- **Status**: Completed (with Milestone 1.5.1 Security/Integrity Hardening).
- **Deliverables**:
  - `apps.catalog` Django app with `CategoryRegistry`, capability declarations across all 7 verticals, and `CatalogItem` model.
  - Logical soft-deletion semantics protecting catalog items, offers, and future booking audit trails.
  - Strict tenant isolation and visibility scoping on catalog and offer list/detail endpoints.
  - `apps.offers` Django app with `OfferSpecification`, currency derivation, floor-price validations, and precise financial calculation service (`calculate_discounted_price`).
  - Authoritative offer calculation API (`/api/v1/offers/calculate/`) enforcing price integrity, validity windows, and transparent floor clamping telemetry.
  - `apps.inventory` domain contracts (`BaseInventoryAdapter`, `AvailabilityQuery`, `AvailabilityResult`) and `InventoryRegistry`.
  - Seven vertical adapters (`Cinema`, `Restaurant`, `SurplusFood`, `Hotel`, `Salon`, `Event`, `Travel`) providing simulated availability.
  - Tenant-isolated REST APIs (`/api/v1/catalog/`, `/api/v1/offers/`, `/api/v1/inventory/`).
- **Verification Evidence**: 67 automated tests passing on SQLite and live PostgreSQL 16; zero ruff or mypy errors across 67 source files.

### Milestone 1.6: Authoritative Hold Engine & ACID Concurrency Core
- **Status**: Completed & Verified.
- **Prerequisites**: Milestone 1.5 complete.
- **Deliverables**:
  - `apps.holds` Django app with PostgreSQL-backed row-level locking (`SELECT ... FOR UPDATE`).
  - Ephemeral hold lifecycle state machine (`ACTIVE`, `CONVERTED_TO_ORDER`, `EXPIRED`, `RELEASED_BY_USER`).
  - Strict idempotency key fingerprinting (SHA-256 canonical payload hashing) preventing parameter tampering and double claims.
  - Category-specific ACID concurrency engines across Cinema seats, Surplus Food batch capacity, Event Tier quotas, Hotel multi-night calendar rows with deterministic date sorting, Salon stylist slots, and simulated Travel holds.
  - Authoritative expiration enforcement inside PostgreSQL (`expires_at > CLOCK_TIMESTAMP()`) preventing usage of expired holds even if cleanup has not run.
  - Background sweep service (`sweep_expired_holds`) with non-blocking transactional reclamation.
  - Double-release protection guaranteeing idempotent hold cancellation without double inventory release.
  - Zero double-booking concurrency test suite proving race condition immunity across simultaneous threads on PostgreSQL 16.4.
- **Dependencies**: Milestones 1.4, 1.5.
- **Acceptance Criteria**: Concurrent requests competing for exclusive seats, quota capacity, or calendar nights yield strictly exact allocations and zero overbooking; duplicate idempotency keys return identical holds without double allocation.
- **Verification Evidence**: 85 automated tests passing (100% pass rate) on live PostgreSQL 16.4; 0 ruff errors, 0 mypy issues across 80 source files.

### Milestone 1.7: Payment Gateway Orchestrator & Escrow Webhook Pipeline
- **Prerequisites**: Milestone 1.6 complete.
- **Deliverables**:
  - `core.payments` module with gateway adapter interface.
  - Cashfree, Razorpay, and Mock gateway adapters.
  - HMAC webhook signature verification and idempotent deduplication table (`payment_attempts`).
  - Double-entry ledger engine (`ledger_entries`) recording gross, fee, tax, and merchant payable.
  - Automated refund saga for orphaned payments.
- **Dependencies**: Milestone 1.6.
- **Acceptance Criteria**: Duplicate webhook delivered 10 times results in single capture and single ledger balance; orphaned payment triggers automated refund.
- **Verification Evidence**: Automated test execution trace proving idempotent handling and refund saga trigger.

### Milestone 1.8: MVP Category Implementations (Cinema, Restaurant, Surplus Food)
- **Prerequisites**: Milestone 1.7 complete.
- **Deliverables**:
  - `modules.cinema`: Screens, seat grid layout, showtimes, seat-level locking.
  - `modules.restaurant`: Tables, meal shifts, cover slots, dining window hold.
  - `modules.surplus_food`: Surplus batch pools, pickup windows, FSSAI display, allergy tags.
- **Dependencies**: Milestones 1.6, 1.7.
- **Acceptance Criteria**: End-to-end booking of a cinema seat, restaurant table, and surplus food bag complete successfully via API.
- **Verification Evidence**: Pytest test suite covering full booking lifecycles for all three categories.

---

## 3. Level 2: Advanced Verticals & External Adapters

### Milestone 2.1: Hotel Room-Night & Inventory Calendar Module
- **Prerequisites**: Level 1 complete.
- **Deliverables**:
  - `modules.hotel`: Room types, inventory calendar, same-day night-audit cut-offs.
  - Chronological multi-row locking for multi-night date ranges.
  - Concrete `hotel_bookings` model.
- **Dependencies**: Milestone 1.6.
- **Acceptance Criteria**: Booking prevents room over-allocation across date boundaries.
- **Verification Evidence**: Integration test suite validating zero overbooking across multi-day blocks.

### Milestone 2.2: Salon Stylist Scheduling & Service Graph Module
- **Prerequisites**: Level 1 complete.
- **Deliverables**:
  - `modules.salon`: Stylists, service catalog, chair/station allocation.
  - Composite resource lock (Stylist + Service duration + Buffer).
- **Dependencies**: Milestone 1.6.
- **Acceptance Criteria**: Prevents double-booking a stylist or station during overlapping time blocks.
- **Verification Evidence**: Pytest suite executing conflicting stylist slot requests.

### Milestone 2.3: Event Tiering & Ticket Pass Generation Module
- **Prerequisites**: Level 1 complete.
- **Deliverables**:
  - `modules.events`: Venues, tiered ticket quotas (VIP, GA), capacity constraints.
  - Atomic ticket instance generator with unique barcodes.
- **Dependencies**: Milestone 1.6.
- **Acceptance Criteria**: Quota pool atomic decrement handles burst requests without breaching capacity.
- **Verification Evidence**: High-concurrency quota exhaustion test output.

### Milestone 2.4: Travel Routing, PNR Engine & Mock Aggregator Adapter
- **Prerequisites**: Level 1 complete.
- **Deliverables**:
  - `modules.travel`: Routes, schedules, bus berth / airline seat maps.
  - `TravelProviderAdapter` interface with deterministic `MockTravelAdapter`.
  - PNR generation and failure injection test harness.
- **Dependencies**: Milestone 1.6.
- **Acceptance Criteria**: Travel booking generates valid simulated PNR; external timeout triggers graceful circuit break.
- **Verification Evidence**: Contract test execution log validating mock PNR and circuit-breaker tripping.

---

## 4. Level 3: Cross-Module Integration & Jury Demonstration Suite

### Milestone 3.1: Unified Customer Web Portal (Next.js Multi-Vertical Flow)
- **Prerequisites**: Levels 1 & 2 complete.
- **Deliverables**: Responsive Next.js application with geolocation, map view, multi-category filtering, seat-map picker, and checkout.
- **Dependencies**: All Level 1 and Level 2 backend APIs.
- **Acceptance Criteria**: User can complete end-to-end booking in all 7 verticals through the browser UI.
- **Verification Evidence**: Playwright test run recordings and video artifacts.

### Milestone 3.2: Merchant Web Portal & Mobile-Responsive QR Scanner
- **Prerequisites**: Milestone 3.1 complete.
- **Deliverables**: Next.js Merchant portal with live order dashboard, inventory manager, dynamic discount configurator, and web-based QR scanner.
- **Dependencies**: Milestone 3.1, `core.redemption`.
- **Acceptance Criteria**: Merchant scans customer pass; camera decodes dynamic QR; atomic redemption verified.
- **Verification Evidence**: E2E test run demonstrating successful scan and rejection on double-scan.

### Milestone 3.3: Admin Portal, Settlement Dashboard & Reconciliation Ledger
- **Prerequisites**: Milestone 3.2 complete.
- **Deliverables**: Next.js Admin portal with merchant KYC verification, ledger viewer, dispute desk, and gateway reconciliation view.
- **Dependencies**: Milestone 3.2, `core.orders`.
- **Acceptance Criteria**: Admin can inspect financial ledger and resolve simulated reconciliation discrepancies.
- **Verification Evidence**: Playwright automated admin test run.

### Milestone 3.4: Jury Demonstration Suite & Synthetic Scenario Injector
- **Prerequisites**: Milestones 3.1, 3.2, 3.3 complete.
- **Deliverables**:
  - Pre-seeded synthetic database fixture across 3 major Indian cities (Bengaluru, Mumbai, Delhi).
  - One-click demo control panel to inject edge cases (simulated bank timeout, rapid price decay, expired hold checkout).
- **Dependencies**: Milestones 3.1, 3.2, 3.3.
- **Acceptance Criteria**: Flawless live demonstration of all 7 verticals and edge-case handling without manual DB tampering.
- **Verification Evidence**: Completed dry-run demonstration log and video recording.

---

## 5. Level 4: Production Hardening, Compliance & Commercial Launch

### Milestone 4.1: Security, Penetration Testing & DPDP Privacy Hardening
- **Prerequisites**: Level 3 complete.
- **Deliverables**: SAST/DAST security scanning, penetration testing report, DPDP customer data erasure workflow implementation.
- **Dependencies**: Level 3.
- **Acceptance Criteria**: Zero high or critical vulnerabilities; automated deletion anonymizes user PII while preserving financial ledger.
- **Verification Evidence**: Independent security scan audit report.

### Milestone 4.2: Payment Partner & Nodal Bank Certification
- **Prerequisites**: Milestone 4.1 complete.
- **Deliverables**: Production Cashfree Marketplace / Razorpay Route agreements, bank escrow account setup, live credentials configuration.
- **Dependencies**: External banking/PA approval.
- **Acceptance Criteria**: Live penny-drop bank verification and live 1-rupee test split transactions succeed.
- **Verification Evidence**: Banking partner certification letter and live test transaction receipts.

### Milestone 4.3: External Provider Adapters (Live GDS & Cinema POS)
- **Prerequisites**: Milestone 4.1 complete.
- **Deliverables**: Production integration with commercial GDS (Amadeus/RedBus API) and Cinema POS (Vista/BMS partner API).
- **Dependencies**: Carrier commercial agreements.
- **Acceptance Criteria**: Production ticket issuance synchronized bi-directionally with external provider.
- **Verification Evidence**: External provider staging environment sign-off.

### Milestone 4.4: High-Scale Concurrency Benchmarking & Production Launch
- **Prerequisites**: Milestones 4.1, 4.2, 4.3 complete.
- **Deliverables**: Load testing up to 10,000 RPM, Multi-AZ deployment, automated failover drills, production go-live.
- **Dependencies**: Cloud infrastructure provisioning.
- **Acceptance Criteria**: $p95$ API latency $< 200\text{ ms}$ under peak load; zero data loss during failover drill.
- **Verification Evidence**: Locust load test summary report and infrastructure failover log.
