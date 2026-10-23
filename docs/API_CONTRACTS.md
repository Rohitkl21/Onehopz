# OneHopz — API Contracts & Interface Specification

**Document Version:** 1.1.0  
**Status:** Approved Technical Specification (Milestone 1.2 Finalized)  
**API Style:** RESTful JSON API over HTTPS  
**Authentication:** JWT Bearer (RFC 7519) + Encrypted SameSite Refresh Cookies  
**Standard Headers:** `Authorization: Bearer <token>`, `Content-Type: application/json`, `Idempotency-Key: <UUIDv4>`, `X-Correlation-ID: <string>`

---

## 1. Global API Standards & Conventions

### 1.1 Uniform Success & Error Response Envelopes
Every API endpoint responds with a standardized envelope structure.

#### Success Response (2xx)
```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "request_id": "req_01HV99Z8Q0XY231908AB",
    "timestamp": "2026-10-23T15:00:00Z"
  }
}
```

#### Error Response (4xx, 5xx)
```json
{
  "success": false,
  "error": {
    "code": "INVENTORY_ALREADY_LOCKED",
    "message": "The requested unit is currently reserved by another session.",
    "details": {
      "conflicting_unit": "Row E, Seat 10",
      "retry_after_seconds": 30
    },
    "request_id": "req_01HV99Z8Q0XY231908AB",
    "timestamp": "2026-10-23T15:00:00Z"
  }
}
```

### 1.2 Pagination Conventions
Endpoints returning collections support standardized pagination query parameters:

1. **Offset/Limit Pagination (Standard Catalog Lists)**:
   - `limit`: Number of items to return (default: `20`, max: `100`).
   - `offset`: Zero-based item offset (default: `0`).
   - Response includes:
     ```json
     "pagination": {
       "total_count": 142,
       "limit": 20,
       "offset": 0,
       "has_next": true
     }
     ```
2. **Cursor Pagination (Audit Logs, High-Volume Ledgers, Transactions)**:
   - `cursor`: Opaque base64 cursor string.
   - `page_size`: Number of items (default: `50`, max: `200`).
   - Response includes `next_cursor` and `has_more`.

### 1.3 Idempotency Header Standard
All state-modifying `POST`, `PUT`, or `PATCH` endpoints that trigger financial transactions, inventory holds, or cancellations require the `Idempotency-Key: <UUIDv4>` header.
- Cached responses for identical keys are valid for 24 hours.
- Concurrent executions with the same key return `409 Conflict` (`IDEMPOTENT_OPERATION_IN_PROGRESS`).

---

## 2. Authentication & Identity (`/api/v1/auth`)

### 2.1 User Registration
- **Endpoint**: `POST /api/v1/auth/register`
- **Auth**: None (Public)
- **Request Payload**:
```json
{
  "email": "customer@example.com",
  "phone_number": "+919876543210",
  "password": "SecurePassword#2026",
  "first_name": "Arjun",
  "last_name": "Mehta",
  "role": "CUSTOMER"
}
```
- **Response (201 Created)**:
```json
{
  "success": true,
  "data": {
    "user_id": "c1f7a220-4318-47bc-8ee7-e6fa7c5881a0",
    "email": "customer@example.com",
    "first_name": "Arjun",
    "role": "CUSTOMER",
    "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
    "expires_in_seconds": 900
  }
}
```
*(Sets HttpOnly secure cookie: `onehopz_refresh_token`)*

### 2.2 User Login
- **Endpoint**: `POST /api/v1/auth/login`
- **Auth**: None (Public)
- **Request Payload**:
```json
{
  "email": "customer@example.com",
  "password": "SecurePassword#2026"
}
```
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "user_id": "c1f7a220-4318-47bc-8ee7-e6fa7c5881a0",
    "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
    "token_type": "Bearer",
    "expires_in_seconds": 900
  }
}
```

### 2.3 Token Refresh
- **Endpoint**: `POST /api/v1/auth/refresh`
- **Auth**: HttpOnly `onehopz_refresh_token` cookie (or JSON body `refresh_token` for non-browser clients)
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
    "token_type": "Bearer",
    "expires_in_seconds": 900
  }
}
```
*(Single-use rotation: old token is revoked, new HttpOnly cookie is set. Raw refresh token is omitted from JSON response.)*

### 2.4 User Logout
- **Endpoint**: `POST /api/v1/auth/logout`
- **Auth**: Public or HttpOnly Cookie
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "message": "Logged out successfully."
  }
}
```
*(Atomically revokes refresh token in database and clears `onehopz_refresh_token` cookie.)*

---

## 3. Geographic & Catalog Discovery (`/api/v1/discovery`)

### 3.1 Spatial Discovery & Multi-Category Search
- **Endpoint**: `GET /api/v1/discovery/search`
- **Auth**: Optional
- **Query Parameters**:
  - `latitude`: Float (e.g. `12.9716`)
  - `longitude`: Float (e.g. `77.5946`)
  - `radius_km`: Integer (e.g. `10`, default `15`, max `50`)
  - `categories`: Comma-separated (e.g. `CINEMA,SURPLUS_FOOD,RESTAURANT,HOTEL,SALON,EVENT,TRAVEL`)
  - `sort_by`: `DISTANCE`, `DISCOUNT_PERCENTAGE`, `EXPIRING_SOONEST`
  - `limit`: Integer (default `20`)
  - `offset`: Integer (default `0`)
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "total_results": 2,
    "items": [
      {
        "listing_id": "8b981622-4467-466d-a31a-e89a24ee5901",
        "outlet_id": "3bf54d24-81c8-4ca4-bb69-ec85714343bf",
        "merchant_name": "Artisan Bakery & Cafe",
        "category": "SURPLUS_FOOD",
        "title": "Surplus Evening Bread & Croissant Bag",
        "base_price": 450.00,
        "current_discount_price": 180.00,
        "discount_percentage": 60.00,
        "currency": "INR",
        "distance_meters": 1240,
        "perishability_details": {
          "pickup_window_start": "2026-10-23T21:30:00Z",
          "pickup_window_end": "2026-10-23T22:15:00Z",
          "units_remaining": 6
        },
        "outlet_location": {
          "address": "100 Feet Road, Indiranagar, Bengaluru",
          "latitude": 12.9784,
          "longitude": 77.6408
        }
      }
    ]
  },
  "pagination": {
    "total_count": 2,
    "limit": 20,
    "offset": 0,
    "has_next": false
  }
}
```

---

## 4. Category Inventory & Availability (`/api/v1/categories`)

### 4.1 Cinema Showtimes & Seats
- **Endpoint**: `GET /api/v1/categories/cinema/showtimes/{showtime_id}/seats`
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "showtime_id": "97d39ca2-7ff4-4ff9-8ff7-66a1c1c1f592",
    "screen_name": "Screen 3 (4K Atmos)",
    "movie_title": "Interstellar Re-release",
    "seats": [
      { "row": "A", "number": 1, "tier": "EXECUTIVE", "base_price": 300.0, "current_price": 150.0, "status": "AVAILABLE" },
      { "row": "A", "number": 2, "tier": "EXECUTIVE", "base_price": 300.0, "current_price": 150.0, "status": "HELD" },
      { "row": "A", "number": 3, "tier": "EXECUTIVE", "base_price": 300.0, "current_price": 150.0, "status": "RESERVED" }
    ]
  }
}
```

### 4.2 Hotel Multi-Night Room Availability
- **Endpoint**: `GET /api/v1/categories/hotel/room-types/{room_type_id}/availability`
- **Query Parameters**: `check_in=2026-10-23&check_out=2026-10-26`
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "room_type_id": "11ab34cd-56ef-78ab-90cd-123456789abc",
    "room_name": "Deluxe Sea View King",
    "check_in": "2026-10-23",
    "check_out": "2026-10-26",
    "total_nights": 3,
    "is_available_all_nights": true,
    "nightly_rates": [
      { "date": "2026-10-23", "rate": 4500.00, "available_rooms": 4 },
      { "date": "2026-10-24", "rate": 5000.00, "available_rooms": 2 },
      { "date": "2026-10-25", "rate": 4500.00, "available_rooms": 5 }
    ],
    "total_stay_price": 14000.00
  }
}
```

---

## 5. Ephemeral Reservation Holds (`/api/v1/holds`)

### 5.1 Acquire Ephemeral Hold
- **Endpoint**: `POST /api/v1/holds/acquire`
- **Auth**: Required (`CUSTOMER`)
- **Headers**: `Idempotency-Key: <UUIDv4>`
- **Request Payload (Example: Cinema Seats)**:
```json
{
  "listing_id": "a90b4e11-e633-4f90-bf38-51ecaa748239",
  "category": "CINEMA",
  "selection_parameters": {
    "showtime_id": "97d39ca2-7ff4-4ff9-8ff7-66a1c1c1f592",
    "seats": [
      { "row": "E", "number": 10 },
      { "row": "E", "number": 11 }
    ]
  }
}
```
- **Request Payload (Example: Multi-Night Hotel)**:
```json
{
  "listing_id": "550e8400-e29b-41d4-a716-446655440000",
  "category": "HOTEL",
  "selection_parameters": {
    "room_type_id": "11ab34cd-56ef-78ab-90cd-123456789abc",
    "check_in_date": "2026-10-23",
    "check_out_date": "2026-10-26",
    "rooms_count": 1
  }
}
```
- **Response (201 Created)**:
```json
{
  "success": true,
  "data": {
    "hold_id": "410887e5-1813-4458-9ffb-365eef8b54b1",
    "status": "ACTIVE",
    "held_at": "2026-10-23T15:05:00Z",
    "expires_at": "2026-10-23T15:15:00Z",
    "ttl_remaining_seconds": 600,
    "locked_units": ["E-10", "E-11"],
    "total_price": 350.00,
    "currency": "INR"
  }
}
```
- **Error Response (409 Conflict)**:
```json
{
  "success": false,
  "error": {
    "code": "INVENTORY_ALREADY_LOCKED",
    "message": "Seat E-10 is currently held by another customer.",
    "details": { "conflicting_unit": "E-10" }
  }
}
```

### 5.2 Release Ephemeral Hold
- **Endpoint**: `DELETE /api/v1/holds/{hold_id}`
- **Auth**: Required (`CUSTOMER` owning the hold)
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "hold_id": "410887e5-1813-4458-9ffb-365eef8b54b1",
    "status": "RELEASED_BY_USER"
  }
}
```

---

## 6. Orders & Checkout (`/api/v1/orders`)

### 6.1 Create Order from Active Hold
- **Endpoint**: `POST /api/v1/orders/checkout`
- **Auth**: Required (`CUSTOMER`)
- **Headers**: `Idempotency-Key: <UUIDv4>`
- **Request Payload**:
```json
{
  "hold_id": "410887e5-1813-4458-9ffb-365eef8b54b1",
  "customer_contact": {
    "name": "Arjun Mehta",
    "email": "customer@example.com",
    "phone": "+919876543210"
  }
}
```
- **Response (201 Created)**:
```json
{
  "success": true,
  "data": {
    "order_id": "89012a67-0cbf-4e69-b50e-6f8d07e6005b",
    "order_number": "OH-20261023-9912",
    "status": "PENDING_PAYMENT",
    "financials": {
      "gross_amount": 700.00,
      "discount_amount": 350.00,
      "platform_fee": 25.00,
      "tax_amount": 4.50,
      "net_payable_amount": 379.50,
      "currency": "INR"
    },
    "cancellation_policy": {
      "policy_type": "WINDOWED_REFUND",
      "deadline": "2026-10-23T18:15:00Z"
    }
  }
}
```

---

## 7. Payments & Ingress Webhooks (`/api/v1/payments`)

### 7.1 Initiate Gateway Payment Session
- **Endpoint**: `POST /api/v1/payments/initiate`
- **Auth**: Required (`CUSTOMER`)
- **Request Payload**:
```json
{
  "order_id": "89012a67-0cbf-4e69-b50e-6f8d07e6005b",
  "gateway_preferred": "CASHFREE"
}
```
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "payment_session_id": "session_live_992178ad99a0",
    "gateway_order_id": "cf_order_91823901",
    "amount": 379.50,
    "currency": "INR",
    "client_auth_token": "cf_tok_live_881920"
  }
}
```

### 7.2 Webhook Ingress (Cashfree / Razorpay)
- **Endpoint**: `POST /api/v1/payments/webhook/{gateway_name}`
- **Auth**: Cryptographic HMAC-SHA256 signature header (`x-webhook-signature` or `X-Razorpay-Signature`)
- **Idempotency**: Handled via deduplication on `payment_attempts.gateway_event_id`.
- **Response (200 OK)**:
```json
{ "status": "acknowledged" }
```

---

## 8. Digital Pass & Gate Redemption (`/api/v1/redemptions`)

### 8.1 Fetch Customer Dynamic QR Pass
- **Endpoint**: `GET /api/v1/orders/{order_id}/pass`
- **Auth**: Required (`CUSTOMER`)
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "ticket_code": "TKT-8912-9921",
    "category": "CINEMA",
    "venue_name": "Grand Cineplex, Garuda Mall",
    "event_details": "Interstellar Re-release — Screen 3 — Row E (Seats 10, 11)",
    "dynamic_qr_payload": "oh_totp_918239a098.20261023T150000Z.sig771a",
    "backup_otp": "481902",
    "valid_from": "2026-10-23T19:45:00Z",
    "valid_until": "2026-10-23T23:00:00Z",
    "is_redeemed": false
  }
}
```

### 8.2 Merchant Gate Verification
- **Endpoint**: `POST /api/v1/merchant/redemptions/verify`
- **Auth**: Required (`MERCHANT_STAFF` or `MERCHANT_ADMIN`)
- **Request Payload**:
```json
{
  "ticket_identifier": "oh_totp_918239a098.20261023T150000Z.sig771a",
  "verification_mode": "QR_SCAN",
  "outlet_id": "89ec2374-9844-4e20-8ae9-42bbf0bc5244"
}
```
- **Response (200 OK — First Scan)**:
```json
{
  "success": true,
  "data": {
    "verification_status": "VERIFIED_SUCCESS",
    "ticket_code": "TKT-8912-9921",
    "order_number": "OH-20261023-9912",
    "customer_name": "Arjun Mehta",
    "allocated_items": ["Screen 3: Seat E-10", "Screen 3: Seat E-11"],
    "redeemed_at": "2026-10-23T19:55:12Z"
  }
}
```

---

## 9. Merchant & Admin Settlements (`/api/v1/settlements`)

### 9.1 Fetch Merchant Settlement Batches
- **Endpoint**: `GET /api/v1/merchant/settlements`
- **Auth**: Required (`MERCHANT_ADMIN`)
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "settlements": [
      {
        "settlement_id": "9921bc45-1234-5678-abcd-ef0123456789",
        "batch_reference": "SETTLE-20261023-0042",
        "gross_sales": 45000.00,
        "commission_deducted": 4500.00,
        "tcs_deducted": 450.00,
        "tds_deducted": 450.00,
        "net_disbursed": 39600.00,
        "bank_utr": "HDFC000123499210",
        "status": "SETTLED",
        "disbursed_at": "2026-10-23T04:30:00Z"
      }
    ]
  }
}
```
