# OneHopz — Business Modules Specification

**Document Version:** 1.1.0  
**Status:** Approved Technical Specification (Milestone 1.2 Finalized)  
**Scope:** Deep-Dive Functional & Domain Specifications for all Seven Verticals  
**System Architecture:** Modular Monolith with Polymorphic Category Adapters

---

## 1. Architectural Divergence Rationale

A critical architectural pitfall in multi-category marketplaces is attempting to force heterogeneous inventory types into a single homogeneous booking model. The table below details why universal assumptions fail and how OneHopz isolates vertical-specific domain mechanics:

```
+-------------------------------------------------------------------------------------------------------------+
|                                  CROSS-CATEGORY DIVERGENCE ANALYSIS                                         |
+------------------+----------------------+--------------------+---------------------+------------------------+
| Category         | Unit of Allocation   | Concurrency Nature | Perishability Event | Cancellation Feasibility|
+------------------+----------------------+--------------------+---------------------+------------------------+
| 1. Cinema        | Exact physical seat  | High competition,  | Showtime starts     | Permitted until 2 hrs  |
|                  | (Row C, Seat 12)     | discrete unit lock | (T-0)               | before show (policy)   |
+------------------+----------------------+--------------------+---------------------+------------------------+
| 2. Restaurant    | Table & party covers | Flexible capacity; | Shift/Window ends;  | Configurable; table can|
|                  | (e.g. 4 covers, 8pm) | soft table mapping | 15-min grace window | be released for walk-in|
+------------------+----------------------+--------------------+---------------------+------------------------+
| 3. Surplus Food  | Perishable food pack | Stock pool count   | Store closing time; | Configurable policy;   |
|                  | (Magic Bag / Meal)   | (integer decrement)| strict pickup cutoff| safety window dependent|
+------------------+----------------------+--------------------+---------------------+------------------------+
| 4. Hotel         | Room category & night| Multi-night block; | Night-audit cutoff  | Configurable policy;   |
|                  | (Deluxe King, 3 nts) | calendar row locks | (e.g. 04:00 AM next)| usually strict cutoff  |
+------------------+----------------------+--------------------+---------------------+------------------------+
| 5. Salon         | Stylist + Time Slot  | Multi-resource     | Appointment slot    | Rescheduling permitted;|
|                  | + Chair resource     | graph dependency   | begins              | buffer time required   |
+------------------+----------------------+--------------------+---------------------+------------------------+
| 6. Events        | Tiered pass or seat  | Massive concurrency| Event start time /  | Non-refundable or gate |
|                  | (VIP / General Adm.) | burst at drops     | Gate closure        | resale policy          |
+------------------+----------------------+--------------------+---------------------+------------------------+
| 7. Travel        | Seat/Berth + PNR     | External GDS sync  | Departure time;     | Governed by operator   |
|                  | on route leg         | latency & timeout  | boarding gate closes| & regulatory transit rules|
+------------------+----------------------+--------------------+---------------------+------------------------+
```

---

## 2. Module 1: Cinema Ticket Booking (`modules.cinema`)

### 2.1 Inventory Representation
- **Entities**: `CinemaScreen`, `CinemaShowtime`, `CinemaSeatAllocation`.
- **Unit of Sale**: Discrete, identifiable seat instance (e.g., `Screen 2, Row F, Seat 14, Recliner Tier`).
- **Status Enum**: `AVAILABLE`, `HELD`, `RESERVED`, `MAINTENANCE_BLOCKED`.
- **Unique Constraint**: `CONSTRAINT uq_cinema_seat UNIQUE (showtime_id, row_code, seat_number)`.

### 2.2 Availability & Concurrency Rules
- **Locking Mechanism**: PostgreSQL explicit row-level lock (`SELECT ... FOR UPDATE`) on the seat allocation record bound to the specific `showtime_id`.
- **Hold Duration Policy**: Configurable per theater chain or showtime (default: 8 minutes).
- **Seat Gap Rules**: Optional screen policy preventing single orphan seats between reserved seats.

### 2.3 Dynamic Yield & Discount Policies
- **Time-Decay Schedule**:
  - *Checkpoint 1* (T - 4 hours to showtime): 25% discount if hall occupancy < 40%.
  - *Checkpoint 2* (T - 1 hour to showtime): 50% discount if hall occupancy < 30%.
  - *Sales Cutoff* (T - 15 minutes before showtime): Sales close; inventory released to on-site box office.
- **Floor Price**: Strict distributor minimum ticket price (e.g., cannot discount below ₹120 base distributor share).

### 2.4 Cancellation & Refund Policy
- Configurable by theater operator:
  - Full refund (minus platform fee) if cancelled $\ge 2$ hours before showtime.
  - Zero refund if cancelled $< 2$ hours before showtime.

### 2.5 Integrations & Verification Status
- `[UNVERIFIED: Direct integration with Cinema POS systems such as Vista, BookMyShow Box Office API, or SPI Cinemas requires bilateral commercial agreements and provider technical certification. MVP will utilize direct platform-managed cinema inventory layouts.]`

---

## 3. Module 2: Restaurant Table Reservations (`modules.restaurant`)

### 3.1 Inventory Representation
- **Entities**: `RestaurantTableLayout`, `RestaurantCoverSlot`.
- **Unit of Sale**: Table allocation or party cover reservation for a specific dining window (e.g., 4 guests at 20:00 for a 90-minute dining block).
- **Status Enum**: `AVAILABLE`, `HELD`, `RESERVED`, `NO_SHOW`.
- **Unique Constraint**: `CONSTRAINT uq_restaurant_slot UNIQUE (table_id, slot_start_time)`.

### 3.2 Availability & Concurrency Rules
- **Pacing Controls**: Maximum covers per 15-minute arrival window to prevent kitchen bottlenecks.
- **Hold Policy**: 10 minutes to complete checkout and deposit (if required).

### 3.3 Dynamic Yield & Discount Policies
- **Off-Peak Incentives**: Deep discounts (30%–50% off food bill or pre-fixed menu) during shoulder hours (e.g., 14:00–16:30 and 21:30–23:00).
- **Minimum Spend Threshold**: Dynamic discount conditioned on meeting minimum cover spend at the outlet.

### 3.4 Cancellation & Grace Period Policy
- Free cancellation up to 1 hour before reservation time.
- 15-minute grace period on arrival; after 15 minutes of no-show, the table status shifts to `NO_SHOW` and is released for walk-in dining.

---

## 4. Module 3: Surplus Food Listings & Discounted Pickup (`modules.surplus_food`)

### 4.1 Inventory Representation
- **Entities**: `SurplusBatch`, `SurplusAllocation`.
- **Unit of Sale**: Inventory pool quantity (e.g., 12 "Surplus Bakery Magic Bags" or 8 "Prepared Dinner Meal Trays").
- **Attributes**: Packaging timestamp, pickup window start/end, dietary category (Veg, Non-Veg, Vegan), allergens list, and FSSAI license number.
- **Capacity Constraint**: `CONSTRAINT chk_surplus_capacity CHECK (held_quantity + sold_quantity <= total_quantity)`.

### 4.2 Availability & Pickup Window Rules
- **Pickup Windows**: Strict time boundaries (e.g., 21:30 to 22:15).
- **Cut-Off Policy**: All orders must be placed at least 15 minutes before the pickup window begins.
- **Hold Locking**: Pessimistic row-lock on `surplus_batches` with atomic increment on `held_quantity`.

### 4.3 Cancellation & Refund Policy
- *Standard Surplus Policy*: Cancellation permitted up to 30 minutes before the pickup window starts with 100% refund.
- *Strict Perishable Policy*: Non-cancellable once the merchant marks the meal prepared/packaged.
- *Quality/Spoilage Claim*: If food is visibly spoiled or unavailable at pickup, an app dispute triggers a full refund upon photo upload and staff acknowledgment.

### 4.4 Food Safety & Compliance
- `[UNVERIFIED: Specific liability disclaimers, temperature control requirements, and food safety standards for commercial surplus distribution require formal review under the Food Safety and Standards Act, 2006.]`

---

## 5. Module 4: Hotel Room Bookings (`modules.hotel`)

### 5.1 Inventory Representation
- **Entities**: `HotelRoomType`, `HotelInventoryCalendar`, `HotelBooking`.
- **Unit of Sale**: Room-night block across stay dates for a specific room type.
- **Capacity Constraint**: `CONSTRAINT chk_hotel_capacity CHECK (held_count + booked_count <= total_available)`.
- **Unique Constraint**: `CONSTRAINT uq_hotel_room_date UNIQUE (room_type_id, stay_date)`.

### 5.2 Availability & Multi-Night Concurrency Rules
- **Multi-Night Stay Locking**: Chronological multi-row locking on `hotel_inventory_calendar` for each night between `check_in_date` and `check_out_date`.
- **Night-Audit Cutoff**: Allows booking unsold rooms for the current night up to 04:00 AM of the subsequent morning.
- **Hold Policy**: 15 minutes hold window to allow entering guest details and completing payment.

### 5.3 Dynamic Yield & Pricing Policies
- Check-in date 18:00: 30% discount off standard rack rate.
- Check-in date 21:00: 50% discount.
- Check-in date 23:00+: Maximum liquidation discount (subject to property floor rate).

### 5.4 Cancellation & Refund Policy
- *Last-Minute Flash Deal*: Non-refundable upon confirmation.
- *Standard Rate*: Cancellable up to 18:00 on the date of check-in.

### 5.5 Integrations & Verification Status
- `[UNVERIFIED: Live bidirectional integration with Channel Managers such as SiteMinder, RateGain, or Staah requires formal enterprise partner agreements. MVP will operate platform-direct property room allocations.]`

---

## 6. Module 5: Salon & Beauty Appointments (`modules.salon`)

### 6.1 Inventory Representation
- **Entities**: `SalonService`, `SalonStylist`, `SalonAppointment`.
- **Unit of Sale**: Discrete multi-resource time slot: `Stylist + Service + Time Interval + Cleanup Buffer`.
- **Status Enum**: `HELD`, `CONFIRMED`, `COMPLETED`, `CANCELLED`, `NO_SHOW`.

### 6.2 Availability Rules & Graph Dependency
- **Composite Resource Lock**: An appointment requires simultaneous availability of:
  1. A stylist qualified to perform the service.
  2. Continuous unbroken time block equal to `service_duration + cleanup_buffer`.
- **Schedule Serialization**: Serialized by pessimistically locking the stylist record in PostgreSQL (`SELECT ... FOR UPDATE`), then checking for overlapping active appointments.

### 6.3 Dynamic Yield Policies
- **Idle Chair Liquidation**: Deep discounts (35%–60%) offered on open stylist slots identified 2–4 hours in advance during historically slow weekday shifts.

### 6.4 Cancellation & Rescheduling Policy
- Free cancellation or rescheduling up to 2 hours before appointment time.
- Cancellations $< 2$ hours subject to a 30% cancellation fee credited to the stylist.

---

## 7. Module 6: Event Ticket Booking (`modules.events`)

### 7.1 Inventory Representation
- **Entities**: `EventVenue`, `EventTier`, `EventTicketAllocation`.
- **Unit of Sale**: Tiered capacity quota increment or allocated reserved pass.
- **Capacity Constraint**: `CONSTRAINT chk_event_tier_capacity CHECK (held_tickets + sold_tickets <= total_tickets)`.

### 7.2 High-Concurrency Burst Rules
- **Atomic Quota Decrement**:
  ```sql
  UPDATE event_tiers 
  SET held_tickets = held_tickets + :qty 
  WHERE id = :tier_id 
    AND (held_tickets + sold_tickets + :qty) <= total_tickets;
  ```
- **Hold Duration Policy**: 8 minutes strict hold TTL.

### 7.3 Dynamic Yield Policies
- **Day-of-Event Liquidation**: Unsold tiered tickets discounted 2–6 hours before doors open to ensure maximum hall attendance.

### 7.4 Cancellation Policy
- Strictly non-refundable once issued, unless the event is officially cancelled or rescheduled by the organizer.

---

## 8. Module 7: Travel Bookings (`modules.travel`)

### 8.1 Inventory Representation
- **Entities**: `TravelRoute`, `TravelSchedule`, `TravelInventoryUnit`, `TravelBooking`, `TravelPassenger`.
- **Unit of Sale**: PNR-associated passenger reservation on a specific scheduled route leg.
- **Unique Constraint**: `CONSTRAINT uq_travel_seat UNIQUE (schedule_id, seat_identifier)`.

### 8.2 Availability & Aggregator Synchronization
- **Adapter Contract**: The `TravelProviderAdapter` mediates:
  - `fetch_live_availability(route, date)`
  - `create_provisional_pnr(passenger_data, hold_duration)`
  - `commit_ticket(pnr_id, payment_ref)`
  - `cancel_ticket(pnr_id)`
- **Timeout Management**: 5000ms strict timeout on external GDS calls. If timeout occurs, fallback mechanism engages Celery reconciliation saga.

### 8.3 Dynamic Yield Policies
- **Last-Hour Seat Liquidation**: Unsold bus berths or airline seats discounted heavily 3–6 hours before scheduled departure.

### 8.4 Cancellation & Regulatory Rules
- Subject to Indian Motor Vehicles Act rules for buses and DGCA CAR Section 3, Series M, Part II for airline refunds.

### 8.5 Integrations & Verification Status
- `[UNVERIFIED: Production access to commercial airline GDS (Amadeus, Sabre) or bus aggregators (RedBus API, AbhiBus) requires formal IATA accreditation, carrier agency agreements, security compliance deposits, and provider testing certification. The platform will maintain a strict MOCK_TRAVEL_PROVIDER adapter for development, testing, and jury demonstrations.]`
