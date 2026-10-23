# OneHopz — Security & Regulatory Compliance Specification

**Document Version:** 1.1.0  
**Status:** Approved Technical Architecture (Milestone 1.2 Finalized)  
**Jurisdiction Context:** Republic of India  
**Scope:** Information Security, Cryptography, Role-Based Access, Webhook Validation, and Statutory Compliance Verification Matrix

---

## 1. Information Security Architecture

### 1.1 Authentication & Token Mechanics
- **Customer Authentication**:
  - Short-lived JWT Access Tokens (15-minute lifespan) signed using HMAC-SHA256 (`HS256`) or RS256.
  - Refresh Tokens: Cryptographically secure 64-byte random tokens stored as HttpOnly, Secure, SameSite=Strict cookies with 30-day lifetime.
  - Stored as SHA-256 hashes in PostgreSQL `refresh_tokens` table.
  - Single-use rotation: When a refresh token is used, it is revoked and replaced with a newly generated token. If an already-revoked refresh token is presented, all refresh tokens for that user session are revoked immediately (replay attack mitigation).
- **Merchant & Administrator Authentication**:
  - Enforces mandatory Two-Factor Authentication (TOTP via RFC 6238 or SMS OTP) for all actions in `MERCHANT_ADMIN`, `FINANCE_ADMIN`, and `SUPER_ADMIN` roles.
  - Immediate session invalidation upon password reset or role alteration.

### 1.2 Role-Based Access Control (RBAC) Matrix

```
+---------------------+----------+----------------+----------------+------------------+---------------+-------------+
| Resource / Action   | CUSTOMER | MERCHANT_STAFF | MERCHANT_ADMIN | PLATFORM_SUPPORT | FINANCE_ADMIN | SUPER_ADMIN |
+---------------------+----------+----------------+----------------+------------------+---------------+-------------+
| Browse Discovery    | READ     | READ           | READ           | READ             | READ          | READ        |
| Acquire Hold        | CREATE   | NO_ACCESS      | NO_ACCESS      | NO_ACCESS        | NO_ACCESS     | NO_ACCESS   |
| Place Order         | CREATE   | NO_ACCESS      | NO_ACCESS      | NO_ACCESS        | NO_ACCESS     | NO_ACCESS   |
| View Personal Order | READ     | NO_ACCESS      | NO_ACCESS      | READ             | READ          | READ        |
| Scan/Redeem Pass    | NO_ACCESS| EXECUTE        | EXECUTE        | NO_ACCESS        | NO_ACCESS     | EXECUTE     |
| Manage Listings     | NO_ACCESS| READ           | CRUD           | READ             | READ          | CRUD        |
| Configure Pricing   | NO_ACCESS| READ           | CRUD           | READ             | NO_ACCESS     | CRUD        |
| View Bank & Payouts | NO_ACCESS| NO_ACCESS      | READ           | NO_ACCESS        | READ_WRITE    | FULL_ACCESS |
| Process Refunds     | REQUEST  | NO_ACCESS      | APPROVE        | APPROVE          | EXECUTE       | FULL_ACCESS |
| Modify User Roles   | NO_ACCESS| NO_ACCESS      | NO_ACCESS      | NO_ACCESS        | NO_ACCESS     | FULL_ACCESS |
+---------------------+----------+----------------+----------------+------------------+---------------+-------------+
```

### 1.3 Webhook Ingress Security
Payment gateways (Cashfree, Razorpay) deliver asynchronous event notifications to `/api/v1/payments/webhook/{gateway}`. The following pipeline is strictly enforced:
1. **Raw Body Ingestion**: Django reads the raw unparsed HTTP request body bytes before JSON parsing.
2. **Cryptographic Signature Verification**:
   - For Razorpay: HMAC-SHA256 of `request.body` using the configured `RAZORPAY_WEBHOOK_SECRET`. Compare in constant time using `hmac.compare_digest`.
   - For Cashfree: Verification of signature timestamp and payload using Cashfree public key or signature verification header.
3. **Replay & Timestamp Protection**: Reject webhooks where payload timestamp differs from server clock by $> 300$ seconds.
4. **Idempotent Ingestion**: Query `payment_attempts.gateway_event_id`. If the event has already been recorded, immediately respond with `HTTP 200 OK` without triggering side-effects.

### 1.4 Rate Limiting & Abuse Prevention
- Configured via Redis token bucket at the Nginx reverse-proxy and Django REST Framework throttle layer:
  - `POST /api/v1/auth/login`: 5 attempts per minute per IP.
  - `POST /api/v1/holds/acquire`: 20 requests per minute per authenticated user (guards against inventory denial-of-service).
  - `GET /api/v1/discovery/search`: 60 requests per minute per IP.
  - `POST /api/v1/merchant/redemptions/verify`: 120 scans per minute per outlet terminal.

---

## 2. Secrets Management & Environment Hygiene

- **Zero Hardcoded Secrets**: Under no circumstances shall database passwords, JWT signing keys, gateway secrets, or third-party API tokens be committed to Git.
- **Environment Isolation**: `.env.example` serves as the authoritative template. Actual secrets are injected at runtime via environment variables or secret management daemons.
- **Masking in Logs**: Credit card numbers, CVVs, UPI PINs, user passwords, and raw JWT tokens are strictly scrubbed from application logs via custom logging filters.

---

## 3. Statutory Compliance Verification Matrix (India)

> [!WARNING]
> Software architecture and code implementation do not constitute legal or regulatory compliance. The table below marks Indian statutory, tax, banking, and sector obligations as **UNVERIFIED** until formal review, agreements, and certifications are executed with licensed professionals and providers.

```
+---------------------------------------------------------------------------------------------------------------------------------+
|                                          STATUTORY & REGULATORY STATUS MATRIX                                                   |
+--------------------------+-------------------------------------+------------------+---------------------------------------------+
| Regulatory Domain        | Statutory Authority & Act           | Status           | Architecture Requirements & Limitations     |
+--------------------------+-------------------------------------+------------------+---------------------------------------------+
| 1. Payment Aggregation   | Reserve Bank of India (RBI)         | UNVERIFIED       | Platform CANNOT operate a closed or semi-   |
|    & Escrow Settlement   | Guidelines for Regulation of PAs    | Requires PA      | closed stored-value customer wallet without |
|                          | and PGs (2020, as updated)          | Agreement        | an RBI PPI license. Must route settlements  |
|                          |                                     | & Legal Review   | directly through licensed PA Escrow/Nodal.  |
+--------------------------+-------------------------------------+------------------+---------------------------------------------+
| 2. Tax Collection at     | Central Goods and Services Tax      | UNVERIFIED       | E-commerce operators are liable to deduct   |
|    Source (TCS)          | (CGST) Act, 2017 — Section 52       | Requires Tax     | TCS @ 1% (or applicable notified rate) on   |
|                          |                                     | Advisory Review  | net taxable supply. Ledger must support TCS.|
+--------------------------+-------------------------------------+------------------+---------------------------------------------+
| 3. Tax Deduction at      | Income Tax Act, 1961 —              | UNVERIFIED       | E-commerce operator deduction of TDS @ 1%   |
|    Source (TDS)          | Section 194-O                       | Requires Tax     | on gross sale amount to e-commerce          |
|                          |                                     | Advisory Review  | participants, subject to statutory limits.  |
+--------------------------+-------------------------------------+------------------+---------------------------------------------+
| 4. Food Safety &         | Food Safety and Standards           | UNVERIFIED       | Mandatory capture and display of 14-digit   |
|    Hygiene Regulations   | Authority of India (FSSAI)          | Requires FSSAI   | FSSAI registration on surplus food listings.|
|                          | Food Safety and Standards Act, 2006 | Legal Clearance  | Mandatory allergen declarations & packaging.|
+--------------------------+-------------------------------------+------------------+---------------------------------------------+
| 5. Personal Data Privacy | Digital Personal Data Protection    | UNVERIFIED       | Lawful basis notice, explicit user consent, |
|    & Data Protection     | (DPDP) Act, 2023                    | Requires Privacy | right to grievance redressal, right to      |
|                          |                                     | Counsel Review   | erasure, and prohibition on dark patterns.  |
+--------------------------+-------------------------------------+------------------+---------------------------------------------+
| 6. Consumer Protection   | Consumer Protection (E-Commerce)    | UNVERIFIED       | Grievance Officer designation, transparent  |
|    in E-Commerce         | Rules, 2020                         | Requires Legal   | total price breakdown, explicit cancellation|
|                          |                                     | Compliance Audit | and refund terms displayed before checkout. |
+--------------------------+-------------------------------------+------------------+---------------------------------------------+
| 7. Commercial Travel &   | DGCA CAR (Civil Aviation) &         | UNVERIFIED       | Airline ticketing requires certified IATA   |
|    Transport Licensing   | Motor Vehicles Act                  | Requires Agency  | accreditation / aggregator commercial       |
|                          |                                     | Agreements       | contract. Cannot issue real PNRs in demo.   |
+--------------------------+-------------------------------------+------------------+---------------------------------------------+
```

---

## 4. Evaluation of Marketplace Payment Providers

### 4.1 Evaluation Summary: Cashfree Marketplace vs. Razorpay Route

| Evaluation Dimension | Cashfree Marketplace / Easy Split | Razorpay Route | OneHopz Architectural Decision |
|---|---|---|---|
| **Marketplace Split Architecture** | Direct vendor bank split via Escrow/Nodal account with flexible fee deduction. | Sub-merchant onboarding with automated split transfers and deduction of commissions. | Abstracted behind `PaymentGatewayAdapter`. Platform will support both via driver plugins. |
| **Vendor Onboarding API** | Instant automated KYC and bank account penny-drop verification via API. | Extensive vendor onboarding APIs, linked account verification. | `[UNVERIFIED: Specific API rates, penny-drop verification costs, and documentation requirements require vendor enterprise agreement.]` |
| **Escrow Compliance** | Compliant with RBI PA/PG norms for direct nodal disbursements. | Compliant with RBI PA/PG norms for split nodal settlements. | Meets platform architectural requirement: funds never touch OneHopz corporate checking account. |
| **Webhooks & Idempotency** | Webhooks sign event payloads with RSA/HMAC signatures; supports retry with backoff. | Cryptographic HMAC signature over webhook body; predictable event schemas. | Webhook receiver handles signature formats of both providers cleanly. |

---

## 5. Customer Privacy & DPDP Act 2023 Architecture

1. **Purpose Limitation**: Customer geolocation coordinates are utilized solely in volatile memory or temporary query parameters to compute distance to merchants. User coordinates are never persisted permanently in database tracking tables.
2. **Right to Erasure (Account Deletion)**: When a customer invokes account deletion:
   - Personal identification data (`users.email`, `users.phone_number`, `users.first_name`, `users.last_name`) is anonymized/pseudonymized (`deleted_user_c1f7a220@redacted.onehopz.internal`).
   - Transactional, order, and tax records are retained in an immutable, pseudonymized state to satisfy statutory requirements under Indian tax laws (which require 8 years of ledger retention).
3. **Auditability**: Every administrative lookup of customer PII is recorded in `audit_events` with staff user ID and justification reason.

---

## 6. Token Concurrency, CSRF Defense & PII Protection Controls (Milestone 1.4.1 Hardening)

1. **Atomic Refresh Token Rotation & Concurrency Defense**:
   - `AuthService.rotate_refresh_token` executes within `transaction.atomic()` using `select_for_update()` row-level locking.
   - Prevents Time-of-Check to Time-of-Use (TOCTOU) race conditions where concurrent requests with the same token could otherwise issue multiple replacement tokens.
   - **Committed Cascade Revocation**: When replay of a revoked token is detected, all active refresh tokens for that user are revoked and committed inside the database transaction *prior* to raising `TokenReuseError`. This guarantees revocation is not rolled back by the exception.
2. **Refresh Token Transport Isolation**:
   - Web browser clients utilize secure `HttpOnly`, `SameSite=Strict` cookies scoped to `/api/v1/auth/`.
   - Raw refresh tokens are strictly omitted from browser-facing response JSON payloads, eliminating token exfiltration vectors via Cross-Site Scripting (XSS).
3. **Cookie-Authenticated CSRF & Origin Defense**:
   - Cookie-authenticated refresh and logout operations enforce strict Origin and Referer validation against configured `CORS_ALLOWED_ORIGINS`.
   - Mismatched origins are rejected with `403 Forbidden` (`CSRF_FAILED`).
4. **Role-Conditioned Compliance PII Masking**:
   - Sensitive tax and statutory identifiers (`pan`, `gstin`) in `MerchantSerializer` are dynamically masked (e.g. `XXXXX1234F`) for users holding operational `STAFF` roles. Full unmasked values are restricted to `OWNER`, `ADMIN`, `FINANCE`, and platform administrators.
5. **Database-Level Case-Insensitive Email Uniqueness**:
   - In addition to application-level lowercase normalization, a database-level functional unique constraint `models.UniqueConstraint(Lower('email'), name='unique_case_insensitive_email')` enforces uniqueness across case variations at the schema level.
6. **Authentication Rate Limiting**:
   - Django REST Framework `ScopedRateThrottle` protects `/api/v1/auth/login` (10/min), `/api/v1/auth/register` (10/min), and `/api/v1/auth/refresh` (30/min).
   - In production, throttling state is maintained in Redis; in development/testing without Redis, it cleanly falls back to `LocMemCache`.


## 7. Authoritative Hold Engine Security & Anti-Fraud Controls (Milestone 1.6)

1. **Strict Customer Ownership & Isolation**:
   - Every ephemeral hold is anchored to `customer_id == request.user.id`.
   - Access to `/api/v1/holds/{id}/` and `/api/v1/holds/{id}/release/` strictly validates ownership. Attempting to view or release another customer's hold returns `403 Forbidden` (`PERMISSION_DENIED`).
2. **Authoritative Server-Side Pricing Resolution**:
   - The hold engine computes unit and total pricing strictly from verified, active `CatalogItem.base_price` and valid `OfferSpecification` rules (`apps.offers.services.calculate_discounted_price`).
   - Client-supplied prices, totals, or currencies are discarded, preventing client price tampering and currency arbitrage.
3. **Cryptographic Idempotency Fingerprinting**:
   - Each hold request computes a canonical SHA-256 fingerprint from `customer_id`, `catalog_item_id`, `category`, `selection_parameters`, and `quantity`.
   - The composite `(customer, idempotency_key)` is guarded by a PostgreSQL `UniqueConstraint`.
   - If an idempotency key is re-submitted with different parameters, the request is rejected with `409 Conflict` (`IDEMPOTENCY_CONFLICT`), preventing reuse attacks or accidental misallocations.
4. **PostgreSQL-Enforced Expiration & Zero Stale Usage**:
   - Holds enforce database-level check constraint `chk_hold_expires_after_held` (`expires_at > held_at`).
   - Any query or order conversion checks `expires_at > CLOCK_TIMESTAMP()`. Expired holds cannot be converted to orders or prevent subsequent customer allocations even if background workers are paused or delayed.
5. **Double-Release Protection**:
   - Releasing an already-released or expired hold is strictly idempotent. The operation returns `200 OK` with `status: "RELEASED_BY_USER"` without double-decrementing batch counters or corrupting quota tables.
