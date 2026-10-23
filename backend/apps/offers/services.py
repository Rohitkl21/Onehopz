"""Offer calculation service enforcing precise financial calculations and transparent floor price tracking."""

from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .models import OfferSpecification, OfferType


@dataclass(frozen=True)
class PricingCalculationResult:
    """Detailed financial breakdown of an evaluated offer discount."""

    base_price: Decimal
    discount_amount: Decimal
    final_price: Decimal
    advertised_discount_value: Decimal
    offer_type: str
    actual_savings_percentage: Decimal
    is_floor_price_clamped: bool
    is_max_discount_capped: bool
    currency: str

    def __iter__(self) -> Any:
        """Allow tuple unpacking (discount_amount, final_price) for backwards compatibility."""
        yield self.discount_amount
        yield self.final_price

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_discounted_price(
    base_price: Decimal,
    offer: OfferSpecification,
    currency: str | None = None,
) -> PricingCalculationResult:
    """
    Calculate precise discount amount, final payable price, and floor-clamping telemetry.

    Returns:
        PricingCalculationResult with exact two-decimal Decimals and boolean flags.
    """
    if not isinstance(base_price, Decimal):
        base_price = Decimal(str(base_price))

    calc_currency = currency.upper() if currency else offer.currency.upper()

    # Validate currency consistency
    if currency and offer.currency and currency.upper() != offer.currency.upper():
        raise ValueError(
            f"Currency mismatch: base price is in {currency.upper()} but offer is in {offer.currency.upper()}."
        )

    cents = Decimal("0.01")
    advertised_val = offer.discount_value

    if base_price <= Decimal("0.00"):
        return PricingCalculationResult(
            base_price=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            final_price=Decimal("0.00"),
            advertised_discount_value=advertised_val,
            offer_type=offer.offer_type,
            actual_savings_percentage=Decimal("0.00"),
            is_floor_price_clamped=False,
            is_max_discount_capped=False,
            currency=calc_currency,
        )

    is_max_discount_capped = False
    if offer.offer_type == OfferType.PERCENTAGE:
        raw_discount = (base_price * offer.discount_value / Decimal("100.00")).quantize(
            cents, rounding=ROUND_HALF_UP
        )
        if offer.max_discount_amount is not None and raw_discount > offer.max_discount_amount:
            raw_discount = offer.max_discount_amount
            is_max_discount_capped = True
    else:  # FIXED_AMOUNT
        raw_discount = min(offer.discount_value, base_price)

    # Floor price constraint enforcement with explicit clamping tracking
    is_floor_price_clamped = False
    if offer.floor_price is not None:
        floor = offer.floor_price
        if base_price - raw_discount < floor:
            clamped_discount = max(Decimal("0.00"), base_price - floor)
            if clamped_discount < raw_discount:
                raw_discount = clamped_discount
                is_floor_price_clamped = True

    final_price = max(Decimal("0.00"), base_price - raw_discount).quantize(
        cents, rounding=ROUND_HALF_UP
    )
    discount_amount = (base_price - final_price).quantize(cents, rounding=ROUND_HALF_UP)

    actual_savings_percentage = Decimal("0.00")
    if base_price > Decimal("0.00"):
        actual_savings_percentage = ((discount_amount / base_price) * Decimal("100.00")).quantize(
            cents, rounding=ROUND_HALF_UP
        )

    return PricingCalculationResult(
        base_price=base_price,
        discount_amount=discount_amount,
        final_price=final_price,
        advertised_discount_value=advertised_val,
        offer_type=offer.offer_type,
        actual_savings_percentage=actual_savings_percentage,
        is_floor_price_clamped=is_floor_price_clamped,
        is_max_discount_capped=is_max_discount_capped,
        currency=calc_currency,
    )
