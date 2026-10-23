# OneHopz — Product Requirements Document (PRD)

**Document Version:** 1.0.0  
**Status:** Approved Architecture Draft  
**Target Platform:** Unified Web Application (Customer, Merchant, Admin)  
**System Architecture:** Modular Monolith (Django REST Framework + Next.js + PostgreSQL/PostGIS)

---

## 1. Executive Summary & Vision

OneHopz is a unified multi-category marketplace engineered to recover revenue from unsold, highly perishable, time-sensitive inventory. Across entertainment, hospitality, food, personal services, and travel, billions of dollars in capacity expire unused every day:
- Empty cinema and event seats once showtime commences.
- Unfilled restaurant tables during off-peak windows.
- Unsold prepared surplus meals and bakery items at closing time.
- Unoccupied hotel rooms after nightly check-in cut-offs.
- Idle salon and spa appointment slots between peak hours.
- Empty bus and airline seats once the boarding gate closes.

OneHopz aggregates these perishable assets into **one unified customer experience**, **one merchant management platform**, **one administrative portal**, and a **single shared backend**. Rather than operating seven fragmented applications, OneHopz provides a cohesive discovery and booking engine backed by category-specific availability adapters and a dynamic time-decay discount engine.

---

## 2. Target User Personas & Core Journeys

### 2.1 Target Personas

```
+----------------------------------------------------------------------------------------------------+
|                                      ONEHOPZ USER PERSONAS                                         |
+------------------------------------+-----------------------------------+---------------------------+
| 1. The Consumer                    | 2. The Merchant                   | 3. The Platform Admin     |
| - Spontaneous Bookers              | - Cinema Operations Managers      | - Platform Operations     |
| - Value Hunters / Students         | - Restaurateurs & F&B Managers    | - Financial Reconcilers   |
| - Eco-Conscious Food Savers        | - Hotel Revenue Managers          | - Customer Support Agents |
| - Flexible Budget Travelers        | - Salon & Spa Owners              | - Trust & Safety Officers |
| - Local Experience Explorers       | - Event Organizers & Bus Fleets   | - Super Administrators    |
+------------------------------------+-----------------------------------+---------------------------+
```

### 2.2 Customer Journey

```
[Spatial Discovery] 
       │ 
       ▼ 
[Filter by Category & Time-Decay Deal] 
       │ 
       ▼ 
[Select Category-Specific Inventory Unit (Seat / Table / Bag / Room / Slot)] 
       │ 
       ▼ 
[Acquire Ephemeral Reservation Hold (Configurable TTL)] 
       │ 
       ▼ 
[Order Review & Gateway Checkout] 
       │ 
       ├── (Payment Success) ──► [Issue Digital Pass / Secure QR / Barcode] ──► [On-Site Redemption]
       └── (Payment Failure/Expired) ──► [Release Hold / Auto-Refund Ledger]
```

1. **Discovery & Geo-Search**: User opens the web application, grants location permissions (or selects a target neighborhood/city), and views real-time time-decay deals across all seven verticals within a configurable radius (e.g., 5 km, 15 km, 50 km).
2. **Evaluation**: User examines listing details, dynamic discount status (e.g., "60% off — expires in 45 mins"), redemption rules, cancellation policies, and merchant ratings.
3. **Inventory Selection**: User selects concrete units based on category rules:
   - *Cinema*: Interactive seat map selection.
   - *Restaurant*: Party size (covers) and arrival time window.
   - *Surplus Food*: Quantity of "Surplus Bags" or meal packs with strict pickup window.
   - *Hotel*: Check-in night and room category.
   - *Salon*: Service, technician/stylist preference, and appointment time-slot.
   - *Event*: Tier selection (General Admission, VIP) or seat selection.
   - *Travel*: Origin, destination, departure schedule, and seat/berth allocation.
4. **Hold Acquisition**: User clicks "Reserve Deal". An atomic, ephemeral hold is created with a category-specific expiration window (e.g., 8–10 minutes) locking the inventory against competing requests.
5. **Payment & Confirmation**: User pays via authorized gateway (UPI, cards, net banking). On verified webhook receipt, the hold converts to a confirmed reservation, generating a secure digital pass with an anti-tamper QR code and OTP.
6. **Redemption**: Customer presents the dynamic QR pass at the venue; merchant scans and marks the reservation redeemed.

### 2.3 Merchant Journey

1. **Onboarding & Verification**: Merchant registers organization, adds legal business details, uploads statutory documents (e.g., GSTIN, FSSAI for food businesses), and configures outlet branches with geographic coordinates.
2. **Inventory & Rule Configuration**:
   - Merchant connects inventory (direct manual entry, batch schedule upload, or POS adapter integration).
   - Merchant defines dynamic discount policies (e.g., "Start at 30% discount 4 hours before showtime; increase to 60% discount 1 hour before showtime; stop sales 15 minutes before showtime").
3. **Live Operational Dashboard**: Merchant staff view incoming reservations, active holds, live capacity utilization, and pickup windows.
4. **Verification & Fulfillment**: Staff scan the customer’s dynamic QR pass using the merchant web scanner or enter the 6-digit OTP to complete redemption.
5. **Payouts & Settlement**: Merchant reviews gross sales, platform commission deductions, statutory withholdings (TCS/TDS where applicable), and tracks escrow payout disbursements.

### 2.4 Administrator Journey

1. **Merchant Governance**: Admins inspect merchant onboarding queues, review uploaded compliance certificates, verify bank accounts, and toggle live merchant status.
2. **Catalog & Policy Oversight**: Admins manage platform categories, global discount bounds, maximum hold durations, and default cancellation windows.
3. **Financial Reconciliation & Dispute Desk**: Admins review payment gateway settlement batches, track orphaned payments, handle refund escalations, and review immutable double-entry ledger entries.
4. **System Audit & Monitoring**: Admins monitor active database connection pools, Celery task backlogs, external adapter circuit breakers, and rate-limiting metrics.

---

## 3. Product Scope Differentiation Matrix

To ensure delivery discipline and prevent feature bloat, requirements are strictly stratified into **MVP**, **Jury Demonstration**, and **Live Commercial Production**:

| Capability Area | MVP Scope | Jury Demonstration Scope | Live Commercial Production Scope |
|---|---|---|---|
| **Platform Architecture** | Modular monolith in DRF + Next.js; PostgreSQL + PostGIS; Celery + Redis. | Same as MVP, running in Docker Compose with pre-seeded rich multi-city datasets. | Production-hardened container cluster (ECS/K8s/App Runner), multi-AZ PostgreSQL RDS, managed Redis, Sentry, Datadog. |
| **Cinema Vertical** | Direct cinema seat map layout; screen creation; showtime scheduling; atomic seat hold & release. | Multi-hall seat picker with realistic theater layouts (standard/recliner tiers); dynamic price decay triggers; mock ticket scanner. | Direct POS/Ticketing API adapters (Vista, BookMyShow partner APIs, SPI) with bilateral inventory synchronization. |
| **Restaurant Vertical** | Time-slot reservation by party size (covers); basic table assignment; configurable booking window. | Visual table layout; reservation pacing controls; dynamic minimum spend discount triggers. | Integration with POS table management systems (Petpooja, POSist, Micros); deposit deduction logic. |
| **Surplus Food Vertical** | Surplus batch listings (Magic Bags / fixed packs); strict pickup time windows; FSSAI display. | Live countdown timers for pickup; batch stock counter; allergy notices; real-time pickup status updates. | Barcode inventory scanning; automated batch creation based on day-end inventory dumps; cold-chain tracking. |
| **Hotel Vertical** | Same-day/last-minute room night booking; room type allocation; non-refundable policy flags. | Interactive room gallery; night-audit cutoff simulation (e.g., booking until 04:00 AM next day); guest card generation. | Channel Manager API integrations (RateGain, SiteMinder, Staah) for two-way room availability sync. |
| **Salon Vertical** | Single-service slot booking; staff chair allocation; duration-based conflict avoidance. | Multi-service booking with sequential duration stacking; stylist picker; buffer time configuration. | Integration with salon POS systems (Zenoti, Fresha); staff roster shift management and break sync. |
| **Event Vertical** | Tiered ticket inventory (VIP, GA); capacity caps; ticket instance generation with unique barcodes. | Gate-entry QR scanner simulation; tiered pricing decay curves; organizer attendee check-in stats. | Multi-gate scanner app; RFID wristband integration; organizer self-serve payout splits. |
| **Travel Vertical** | Direct route, schedule, and seat/berth inventory for intercity buses; mock airline flights. | End-to-end simulated booking for bus & flight with PNR generation, boarding pass simulator, and delay injector. | Certified GDS/OTA Aggregator integrations (Amadeus, TBO, RedBus API) with live fare search and PNR issuing. |
| **Payments & Escrow** | Gateway adapter with sandbox checkout; webhook receiver; atomic order creation; manual refund ledger. | Fully functional interactive payment simulator with instant success, bank failure, and timeout simulation modes. | Production Razorpay Route / Cashfree Marketplace integration with automated escrow splits, TCS/TDS, and dispute webhooks. |
| **Redemption** | 6-digit OTP verification and basic QR code lookup in merchant portal. | Mobile-responsive in-browser QR camera scanner with audio-visual feedback and anti-replay validation. | Dedicated native/PWA scanner with offline verification capability and cryptographic signature validation. |

---

## 4. Detailed Functional Requirements (FR)

### FR-01: Universal Catalog & Spatial Discovery
- **FR-01.1**: The system shall index every merchant outlet with geographic coordinates (`Point(lng, lat)` in WGS 84 / EPSG:4326).
- **FR-01.2**: The customer discovery API shall accept latitude, longitude, search radius (in kilometers), optional category filters, and return listings ordered by distance, discount percentage, or expiration urgency.
- **FR-01.3**: Spatial queries must execute via PostGIS spatial indexes (`GIST`) and return results within 200ms under standard load.

### FR-02: Category-Specific Inventory Abstraction
- **FR-02.1**: The platform shall provide a common `InventoryCapability` interface that exposes standard operations: `check_availability`, `acquire_hold`, `release_hold`, and `commit_reservation`.
- **FR-02.2**: Category-specific inventory logic (seat allocations, table covers, perishable batches, room blocks, stylist slots, ticket quotas, bus seats) must be encapsulated in dedicated module adapters without polluting core schemas.

### FR-03: Dynamic Yield & Time-Decay Pricing Engine
- **FR-03.1**: Merchants shall configure dynamic discount schedules linked to absolute time, hours-to-expiration, or vacancy percentages.
- **FR-03.2**: Discount calculations must execute deterministically on the backend; client-submitted prices shall never be trusted.
- **FR-03.3**: Pricing rules must support merchant-defined floor prices below which discounts cannot drop.

### FR-04: Authoritative Ephemeral Reservation Holds
- **FR-04.1**: Customers must acquire a temporary hold before initiating payment.
- **FR-04.2**: Holds must have an explicit UTC `expires_at` timestamp governed by category-specific policies (e.g., Cinema: 8 mins; Surplus Food: 10 mins; Travel: 15 mins).
- **FR-04.3**: Hold acquisition must execute inside an ACID transaction using PostgreSQL row-level locks (`SELECT ... FOR UPDATE`), preventing double-allocation under race conditions.
- **FR-04.4**: Holds that reach `expires_at` without confirmed payment must be treated as invalid by checkout and released for other customers.

### FR-05: Order & Payment Processing
- **FR-05.1**: An order can only be created from an active, unexpired hold.
- **FR-05.2**: The system must support gateway-agnostic payment initiation, generating client tokens for frontend SDKs.
- **FR-05.3**: Payment webhooks must be cryptographically verified using HMAC signatures, processed idempotently, and update the order state machine atomically.
- **FR-05.4**: The system shall never operate an unlicensed stored-value customer wallet.

### FR-06: Digital Ticket & Pass Generation
- **FR-06.1**: Upon payment confirmation, the system must issue a digital pass containing:
  - Human-readable reservation code.
  - Category-specific details (seats, room type, pickup window, PNR, stylist).
  - High-entropy cryptographic token encoded as a dynamic QR code.
  - Single-use 6-digit backup OTP.
- **FR-06.2**: Digital passes must clearly indicate validity windows, merchant address, cancellation terms, and customer support channels.

### FR-07: Merchant Redemption & Gate Check-in
- **FR-07.1**: The merchant portal shall feature a QR verification interface capable of reading passes via camera or manual OTP entry.
- **FR-07.2**: Redemption must be atomic; scanning an already-redeemed or expired ticket must immediately display an error with the original redemption timestamp.
- **FR-07.3**: Every redemption attempt (successful or rejected) must be logged in an immutable audit trail.

### FR-08: Configurable Cancellation & Refund Engine
- **FR-08.1**: Every category and listing must declare a clear cancellation policy:
  - `STRICT_NON_REFUNDABLE` (e.g., immediate surplus food, last-minute travel).
  - `WINDOWED_REFUND` (e.g., 100% refund up to 2 hours before cinema showtime; 50% refund up to 1 hour before).
  - `CONDITIONAL_MERCHANT_APPROVAL` (e.g., salon rescheduling).
- **FR-08.2**: If a cancellation is permitted, the system must record a negative ledger entry and initiate an automated gateway refund via API.

### FR-09: Failure Recovery & Orphaned Payment Resolution
- **FR-09.1**: If a payment webhook arrives with status `CAPTURED` but the associated hold has expired and the inventory was re-allocated, the system must:
  - Transition order to `PAYMENT_CAPTURED_ALLOCATION_FAILED`.
  - Automatically trigger a full gateway refund.
  - Alert the customer with an explanatory notification.
  - Log an audit event for operator review.
- **FR-09.2**: Webhooks arriving out-of-order or duplicated must produce idempotent `200 OK` responses without altering confirmed state.

### FR-10: Merchant Settlement & Escrow Ledger
- **FR-10.1**: All financial transactions must be recorded in an immutable, double-entry ledger table (`ledger_entries`) tracking:
  - Gross customer payment.
  - Platform commission / convenience fee.
  - Statutory withholdings (e.g., TCS under GST, TDS under Income Tax).
  - Net merchant payable balance.
- **FR-10.2**: Settlement disbursements to merchant bank accounts must be tracked via batch settlement objects.

---

## 5. Non-Functional Requirements (NFR)

- **NFR-01: Data Integrity & ACID Compliance**: Under zero circumstances may the system double-sell an identical seat, room, table, or appointment slot. PostgreSQL is the sole authoritative state source.
- **NFR-02: Latency**: Discovery queries must resolve in $\le 200\text{ ms}$ ($p95$). Hold acquisition must resolve in $\le 150\text{ ms}$ ($p95$). Webhook ingestion must acknowledge within $\le 500\text{ ms}$.
- **NFR-03: Security & Encryption**: All traffic over TLS 1.3. Passwords hashed using Argon2id or PBKDF2 with SHA-256. Webhook payloads verified via HMAC-SHA256. PII encrypted at rest where required by regulations.
- **NFR-04: High Availability**: Platform designed for zero single-point-of-failure in production. Monolith components stateless; all session and transactional state persisted in PostgreSQL and Redis.
- **NFR-05: Maintainability & Modularity**: Backend codebase organized into strict Django apps by domain. Cross-domain communication mediated by documented service contracts, never raw direct queries across foreign domain boundaries.
- **NFR-06: Auditability**: All administrative actions, status transitions, redemptions, and refund executions must generate immutable audit events with actor ID, IP address, timestamp, and before/after state diffs.

---

## 6. Acceptance Criteria (AC)

- **AC-01 (Multi-Category Support)**: All 7 categories (Cinema, Restaurant, Surplus Food, Hotel, Salon, Events, Travel) are represented in the data schema, API endpoints, and web interfaces.
- **AC-02 (Zero Double-Booking)**: Running 50 concurrent hold requests against a single available inventory unit results in exactly 1 successful hold and 49 conflict (`409 Conflict`) responses.
- **AC-03 (Authoritative Expiration)**: An expired hold cannot be checked out, even if Redis is completely flushed or offline; the PostgreSQL timestamp check strictly blocks checkout.
- **AC-04 (Orphaned Payment Safety)**: Simulating a payment success callback on an expired, re-allocated hold initiates an automated refund and transitions the order to a safe failure state without data corruption.
- **AC-05 (Webhook Idempotency)**: Sending the exact same payment webhook 10 times consecutively produces identical `200 OK` responses and exactly one payment capture ledger entry.
- **AC-06 (Redemption Security)**: Presenting an already-redeemed QR pass displays an explicit rejection message with the exact prior redemption timestamp and staff identifier.
- **AC-07 (Demo vs. Live Isolation)**: Demo/simulated transactions are explicitly flagged with `is_demo=True` and partitioned such that they cannot be commingled with live tax or bank settlement records.
