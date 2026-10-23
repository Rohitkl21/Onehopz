"""Offer calculation service enforcing precise financial calculations."""

from decimal import ROUND_HALF_UP, Decimal

from .models import OfferSpecification, OfferType


def calculate_discounted_price(
    base_price: Decimal,
    offer: OfferSpecification,
) -> tuple[Decimal, Decimal]:
    """
    Calculate precise discount amount and final payable price.

    Returns:
        (discount_amount, final_price) as two-decimal precision Decimals.
    """
    if not isinstance(base_price, Decimal):
        base_price = Decimal(str(base_price))

    if base_price <= Decimal("0.00"):
        return Decimal("0.00"), Decimal("0.00")

    cents = Decimal("0.01")

    if offer.offer_type == OfferType.PERCENTAGE:
        raw_discount = (base_price * offer.discount_value / Decimal("100.00")).quantize(
            cents, rounding=ROUND_HALF_UP
        )
        if offer.max_discount_amount is not None:
            raw_discount = min(raw_discount, offer.max_discount_amount)
    else:  # FIXED_AMOUNT
        raw_discount = min(offer.discount_value, base_price)

    # Floor price constraint enforcement
    if offer.floor_price is not None:
        floor = offer.floor_price
        if base_price - raw_discount < floor:
            raw_discount = max(Decimal("0.00"), base_price - floor)

    final_price = max(Decimal("0.00"), base_price - raw_discount).quantize(
        cents, rounding=ROUND_HALF_UP
    )
    discount_amount = (base_price - final_price).quantize(cents, rounding=ROUND_HALF_UP)

    return discount_amount, final_price
