"""Category-specific authoritative inventory and allocation models."""

import uuid
from decimal import Decimal

from django.db import models
from django.db.models import F, Q

from apps.merchants.models import Outlet


class CinemaScreen(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    outlet = models.ForeignKey(Outlet, on_delete=models.CASCADE, related_name="cinema_screens")
    name = models.CharField(max_length=100)
    total_capacity = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cinema Screen"
        verbose_name_plural = "Cinema Screens"


class CinemaShowtime(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    screen = models.ForeignKey(CinemaScreen, on_delete=models.CASCADE, related_name="showtimes")
    catalog_item = models.ForeignKey(
        "catalog.CatalogItem",
        on_delete=models.CASCADE,
        related_name="cinema_showtimes",
    )
    movie_title = models.CharField(max_length=255)
    movie_duration_minutes = models.PositiveIntegerField(default=120)
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cinema Showtime"
        verbose_name_plural = "Cinema Showtimes"
        indexes = [
            models.Index(fields=["catalog_item", "start_time"], name="idx_showtime_item_start"),
        ]


class CinemaSeatAllocation(models.Model):
    class SeatStatus(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        HELD = "HELD", "Held"
        RESERVED = "RESERVED", "Reserved"
        MAINTENANCE_BLOCKED = "MAINTENANCE_BLOCKED", "Maintenance Blocked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    showtime = models.ForeignKey(
        CinemaShowtime,
        on_delete=models.CASCADE,
        related_name="seat_allocations",
    )
    row_code = models.CharField(max_length=10)
    seat_number = models.PositiveIntegerField()
    tier_name = models.CharField(max_length=50, default="STANDARD")
    status = models.CharField(
        max_length=25,
        choices=SeatStatus.choices,
        default=SeatStatus.AVAILABLE,
        db_index=True,
    )
    current_hold = models.ForeignKey(
        "holds.Hold",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cinema_seat_allocations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cinema Seat Allocation"
        verbose_name_plural = "Cinema Seat Allocations"
        constraints = [
            models.UniqueConstraint(
                fields=["showtime", "row_code", "seat_number"],
                name="uq_cinema_seat",
            ),
        ]
        indexes = [
            models.Index(fields=["showtime", "status"], name="idx_cinema_seat_lookup"),
        ]


class SurplusBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    catalog_item = models.ForeignKey(
        "catalog.CatalogItem",
        on_delete=models.CASCADE,
        related_name="surplus_batches",
    )
    batch_title = models.CharField(max_length=255)
    pickup_window_start = models.DateTimeField(db_index=True)
    pickup_window_end = models.DateTimeField(db_index=True)
    total_quantity = models.PositiveIntegerField()
    held_quantity = models.PositiveIntegerField(default=0)
    sold_quantity = models.PositiveIntegerField(default=0)
    dietary_type = models.CharField(max_length=50, default="MIXED")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Surplus Batch"
        verbose_name_plural = "Surplus Batches"
        constraints = [
            models.CheckConstraint(
                condition=Q(held_quantity__gte=0),
                name="chk_surplus_held_non_neg",
            ),
            models.CheckConstraint(
                condition=Q(sold_quantity__gte=0),
                name="chk_surplus_sold_non_neg",
            ),
            models.CheckConstraint(
                condition=Q(total_quantity__gte=F("held_quantity") + F("sold_quantity")),
                name="chk_surplus_capacity",
            ),
        ]


class SurplusAllocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(SurplusBatch, on_delete=models.CASCADE, related_name="allocations")
    hold = models.ForeignKey(
        "holds.Hold",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="surplus_allocations",
    )
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=20, default="HELD")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Surplus Allocation"
        verbose_name_plural = "Surplus Allocations"


class HotelRoomType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    catalog_item = models.ForeignKey(
        "catalog.CatalogItem",
        on_delete=models.CASCADE,
        related_name="hotel_room_types",
    )
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.CASCADE,
        related_name="hotel_room_types",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=100)
    max_occupancy_adults = models.PositiveIntegerField(default=2)
    total_rooms_in_inventory = models.PositiveIntegerField()

    class Meta:
        verbose_name = "Hotel Room Type"
        verbose_name_plural = "Hotel Room Types"


class HotelInventoryCalendar(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room_type = models.ForeignKey(
        HotelRoomType,
        on_delete=models.CASCADE,
        related_name="calendar_entries",
    )
    stay_date = models.DateField(db_index=True)
    total_available = models.PositiveIntegerField()
    held_count = models.PositiveIntegerField(default=0)
    booked_count = models.PositiveIntegerField(default=0)
    nightly_base_rate = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        verbose_name = "Hotel Inventory Calendar"
        verbose_name_plural = "Hotel Inventory Calendar Entries"
        constraints = [
            models.UniqueConstraint(
                fields=["room_type", "stay_date"],
                name="uq_hotel_room_date",
            ),
            models.CheckConstraint(
                condition=Q(total_available__gte=F("held_count") + F("booked_count")),
                name="chk_hotel_capacity",
            ),
        ]


class HotelBookingHold(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room_type = models.ForeignKey(
        HotelRoomType,
        on_delete=models.CASCADE,
        related_name="booking_holds",
    )
    hold = models.ForeignKey(
        "holds.Hold",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hotel_booking_holds",
    )
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    rooms_count = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Hotel Booking Hold"
        verbose_name_plural = "Hotel Booking Holds"


class EventVenue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    outlet = models.ForeignKey(Outlet, on_delete=models.CASCADE, related_name="event_venues")
    venue_name = models.CharField(max_length=255)
    total_max_capacity = models.PositiveIntegerField()

    class Meta:
        verbose_name = "Event Venue"
        verbose_name_plural = "Event Venvenues"


class EventTier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    catalog_item = models.ForeignKey(
        "catalog.CatalogItem",
        on_delete=models.CASCADE,
        related_name="event_tiers",
    )
    tier_name = models.CharField(max_length=100)
    total_allocation = models.PositiveIntegerField()
    held_tickets = models.PositiveIntegerField(default=0)
    sold_tickets = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Event Tier"
        verbose_name_plural = "Event Tiers"
        constraints = [
            models.CheckConstraint(
                condition=Q(total_allocation__gte=F("held_tickets") + F("sold_tickets")),
                name="chk_event_tier_capacity",
            ),
        ]


class EventTicketAllocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tier = models.ForeignKey(EventTier, on_delete=models.CASCADE, related_name="ticket_allocations")
    hold = models.ForeignKey(
        "holds.Hold",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_ticket_allocations",
    )
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=20, default="HELD")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Event Ticket Allocation"
        verbose_name_plural = "Event Ticket Allocations"


class RestaurantTableLayout(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    outlet = models.ForeignKey(Outlet, on_delete=models.CASCADE, related_name="restaurant_tables")
    table_number = models.CharField(max_length=20)
    min_covers = models.PositiveIntegerField(default=1)
    max_covers = models.PositiveIntegerField(default=4)
    dining_area = models.CharField(max_length=50, default="MAIN_HALL")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Restaurant Table Layout"
        verbose_name_plural = "Restaurant Table Layouts"
        constraints = [
            models.UniqueConstraint(
                fields=["outlet", "table_number"],
                name="uq_restaurant_table",
            ),
        ]


class RestaurantCoverSlot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    catalog_item = models.ForeignKey(
        "catalog.CatalogItem",
        on_delete=models.CASCADE,
        related_name="restaurant_slots",
        null=True,
        blank=True,
    )
    outlet = models.ForeignKey(Outlet, on_delete=models.CASCADE, related_name="restaurant_slots")
    table = models.ForeignKey(
        RestaurantTableLayout,
        on_delete=models.CASCADE,
        related_name="cover_slots",
    )
    slot_start_time = models.DateTimeField(db_index=True)
    slot_end_time = models.DateTimeField()
    status = models.CharField(max_length=20, default="AVAILABLE")
    current_hold = models.ForeignKey(
        "holds.Hold",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="restaurant_cover_slots",
    )

    class Meta:
        verbose_name = "Restaurant Cover Slot"
        verbose_name_plural = "Restaurant Cover Slots"
        constraints = [
            models.UniqueConstraint(
                fields=["table", "slot_start_time"],
                name="uq_restaurant_slot",
            ),
        ]


class SalonStylistSlotAllocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    catalog_item = models.ForeignKey(
        "catalog.CatalogItem",
        on_delete=models.CASCADE,
        related_name="salon_slots",
    )
    outlet = models.ForeignKey(Outlet, on_delete=models.CASCADE, related_name="salon_slots")
    stylist_name = models.CharField(max_length=100)
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField()
    status = models.CharField(max_length=20, default="AVAILABLE")
    current_hold = models.ForeignKey(
        "holds.Hold",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salon_slot_allocations",
    )

    class Meta:
        verbose_name = "Salon Stylist Slot Allocation"
        verbose_name_plural = "Salon Stylist Slot Allocations"
        constraints = [
            models.UniqueConstraint(
                fields=["outlet", "stylist_name", "start_time"],
                name="uq_salon_stylist_slot",
            ),
        ]


class TravelInventoryUnit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    catalog_item = models.ForeignKey(
        "catalog.CatalogItem",
        on_delete=models.CASCADE,
        related_name="travel_units",
        null=True,
        blank=True,
    )
    route_code = models.CharField(max_length=50)
    departure_time = models.DateTimeField()
    seat_identifier = models.CharField(max_length=20)
    is_simulated = models.BooleanField(default=True)
    status = models.CharField(max_length=20, default="AVAILABLE")
    current_hold = models.ForeignKey(
        "holds.Hold",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="travel_units",
    )

    class Meta:
        verbose_name = "Travel Inventory Unit"
        verbose_name_plural = "Travel Inventory Units"
        constraints = [
            models.UniqueConstraint(
                fields=["route_code", "departure_time", "seat_identifier"],
                name="uq_travel_unit",
            ),
        ]
