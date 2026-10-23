# OneHopz — Master Test Strategy & Quality Assurance Plan

**Document Version:** 1.1.0  
**Status:** Approved Technical Specification (Milestone 1.2 Finalized)  
**Scope:** Automated & Manual Testing Across Unit, Integration, API, Concurrency, Security, Recovery, and Demonstration Modes  
**Test Harness:** Pytest (Django/Backend), Jest / Playwright (Next.js/Frontend), Locust (Concurrency & Load)

---

## 1. Quality Philosophy & Testing Pyramid

The OneHopz platform relies on an inverted test pyramid prioritizing high-fidelity database integration and concurrency tests over brittle UI tests:

```
                  ▲
                 / \
                /   \     E2E UI & Demo Flows (Playwright)
               /     \    ~10% of test suite
              /-------\
             /         \   API Contract & Failure Recovery Sagas
            /           \  ~30% of test suite
           /-------------\
          /               \ Database Concurrency & Adapter Integrations
         /                 \ ~40% of test suite (PostgreSQL row locks, ACID)
        /-------------------\
       /                     \ Unit Tests & Domain Calculation Specs
      /                       \ ~20% of test suite (Pure functions, Yield decay)
     /-------------------------\
```

---

## 2. Test Scope & Categorization

### 2.1 Unit Testing
- **Dynamic Yield Formulas**: Verify linear, exponential, and step decay curves. Ensure calculated prices never drop below the merchant-specified `floor_price`.
- **Policy Evaluators**: Test hold TTL calculators, cancellation fee percentages based on time elapsed, and commission/tax withholding arithmetic.
- **Data Model Methods & Cryptography**: Model string representations, state machine transition validators, and cryptographic TOTP token generators.

### 2.2 Integration & Database Concurrency Testing
- **Authoritative Database Holds**: Execute concurrent transactions attempting to acquire the identical inventory unit (Cinema Seat, Restaurant Table, Surplus Bag, Salon Slot, Event Tier, Hotel Room).
- **PostgreSQL Isolation**: Verify that `SELECT ... FOR UPDATE` locks conflicting rows and returns `409 Conflict` on competing sessions without deadlock.
- **Immutable Ledger Verification**: Execute SQL `UPDATE` and `DELETE` statements against `ledger_entries` and assert that the database trigger strictly raises an exception.
- **Redis Decoupling Test**: Verify that holds correctly expire and checkout is strictly blocked even when Redis is terminated or wiped.

### 2.3 API Contract Testing
- Automated schema validation using pytest-drf against the specifications defined in `API_CONTRACTS.md`.
- Validate error envelopes for 400, 401, 403, 404, 409, 422, and 500 status codes.
- Validate `Idempotency-Key` header handling across duplicate requests.

---

## 3. High-Concurrency Stress Testing Protocols

### 3.1 Competing Reservation Test Protocol (Cinema Seat)
```python
def test_concurrent_seat_hold_prevents_double_booking():
    showtime = create_showtime(movie="Interstellar", available_seats=1)
    seat = showtime.seats.first()
    
    results = []
    
    def attempt_hold(user_id):
        client = APIClient()
        client.authenticate(user_id)
        response = client.post(
            "/api/v1/holds/acquire",
            data={
                "listing_id": str(showtime.listing_id),
                "category": "CINEMA",
                "selection_parameters": {
                    "showtime_id": str(showtime.id),
                    "seats": [{"row": seat.row_code, "number": seat.seat_number}]
                }
            },
            headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(attempt_hold, user_id=f"user_{i}") for i in range(50)]
        results = [f.result() for f in futures]

    # Acceptance Criteria: Exactly ONE 201 Created and FORTY-NINE 409 Conflict
    assert results.count(201) == 1
    assert results.count(409) == 49
    assert seat.refresh_from_db().status == 'HELD'
```

### 3.2 Multi-Night Hotel Concurrency Test Protocol
```python
def test_concurrent_hotel_multi_night_hold():
    room_type = create_hotel_room_type(total_rooms=1)
    # 3-night stay where only 1 room is available
    check_in = "2026-10-23"
    check_out = "2026-10-26"
    
    results = []
    def attempt_hotel_hold(user_id):
        client = APIClient()
        client.authenticate(user_id)
        response = client.post(
            "/api/v1/holds/acquire",
            data={
                "listing_id": str(room_type.listing_id),
                "category": "HOTEL",
                "selection_parameters": {
                    "room_type_id": str(room_type.id),
                    "check_in_date": check_in,
                    "check_out_date": check_out,
                    "rooms_count": 1
                }
            },
            headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(attempt_hotel_hold, user_id=f"hotel_user_{i}") for i in range(20)]
        results = [f.result() for f in futures]

    assert results.count(201) == 1
    assert results.count(409) == 19
```

---

## 4. Edge-Case Acceptance Criteria & Test Scenarios

```
+----------------------------------------------------------------------------------------------------+
|                                    EDGE CASE TEST SCENARIOS                                        |
+--------------------------+------------------------------------+------------------------------------+
| Test Scenario            | Execution Conditions               | Expected Acceptance Criteria       |
+--------------------------+------------------------------------+------------------------------------+
| TC-01: Payment Success   | User holds seat; hold expires at   | 1. DB detects expires_at < NOW().  |
| on Expired Hold          | T+10m; user completes payment at   | 2. Order moves to ALLOCATION_FAILED|
| (Orphaned Payment)       | T+12m; seat was re-sold to User B. | 3. Automated refund triggered.     |
|                          | Webhook arrives with CAPTURED.     | 4. User alerted with refund ref.   |
+--------------------------+------------------------------------+------------------------------------+
| TC-02: Duplicate Webhook | Payment gateway sends identical    | 1. First webhook: Order confirmed. |
| Delivery (Network Retry) | CAPTURED webhook 10 times in 500ms.| 2. Webhooks 2-10: Return 200 OK.   |
|                          |                                    | 3. Zero duplicate ledger entries.  |
|                          |                                    | 4. Single digital ticket issued.   |
+--------------------------+------------------------------------+------------------------------------+
| TC-03: Delayed Webhook   | Payment captured, but gateway      | 1. Client poll queries gateway API.|
| Ingress                  | webhook is delayed by 45 minutes.  | 2. Order confirmed via direct pull.|
|                          |                                    | 3. Late webhook handled cleanly.   |
+--------------------------+------------------------------------+------------------------------------+
| TC-04: Dynamic QR Replay | User takes a screenshot of pass    | 1. Pass utilizes rotating TOTP QR. |
| / Screenshot Fraud       | and shares with a second party.    | 2. Screenshot rejected after 30s.  |
|                          | Both attempt gate entry.           | 3. If scanned twice, 2nd rejected. |
+--------------------------+------------------------------------+------------------------------------+
| TC-05: Double Redemption | Two merchant staff members scan    | 1. Row lock on digital_tickets.    |
| Race Condition           | the exact same ticket at two gates | 2. Staff A gets 200 OK Verified.   |
|                          | at the exact same millisecond.     | 3. Staff B gets 409 Redeemed.      |
+--------------------------+------------------------------------+------------------------------------+
| TC-06: External Provider | Travel GDS API fails to respond    | 1. Circuit breaker trips at 5000ms.|
| Timeout (Travel PNR)     | within 5000ms during checkout.     | 2. Retry saga queued in Celery.    |
|                          |                                    | 3. If retry fails, refund customer.|
+--------------------------+------------------------------------+------------------------------------+
| TC-07: Redis Failure /   | Redis process is killed while      | 1. Active holds still verified     |
| Cluster Flush            | multiple customers are checking    |    via PostgreSQL expires_at.      |
|                          | out.                               | 2. Zero double-booking occurs.     |
+--------------------------+------------------------------------+------------------------------------+
| TC-08: Ledger Tamper     | Application tries to execute       | 1. PostgreSQL trigger fires.       |
| Attempt                  | UPDATE or DELETE on ledger_entries.| 2. Database raises exception.      |
|                          |                                    | 3. Transaction aborts.             |
+--------------------------+------------------------------------+------------------------------------+
```

---

## 5. Demonstration vs. Live Integration Testing

```
+------------------------------------+-----------------------------------+
| DEMO / JURY TEST ENVIRONMENT       | LIVE COMMERCIAL TEST ENVIRONMENT  |
+------------------------------------+-----------------------------------+
| - is_demo = True on all entities   | - is_demo = False                 |
| - Mock Payment Gateway Adapter     | - Sandbox Cashfree / Razorpay     |
|   (Interactive Success/Fail toggle)|   with real test credentials      |
| - Mock Travel GDS Adapter          | - Live GDS Partner API Adapter    |
|   (Instant deterministic PNRs)     |   (Requires carrier agreements)   |
| - Synthetic pre-seeded city deals  | - Real merchant onboarding data   |
|   (Bengaluru, Mumbai, Delhi)       |   with verified FSSAI/GSTIN docs  |
| - Rapid dynamic price decay speed  | - Real-time chronological decay   |
|   (Simulate 4 hours in 30 seconds) |   over actual calendar days       |
| - Zero financial liability or tax  | - Double-entry ledger subject to  |
|   reporting obligations generated  |   statutory audit and TCS filings |
+------------------------------------+-----------------------------------+
```
