from app.schemas.gift import GiftAttributeSchema, GiftCard
from app.services.pricing import estimate_gift_price, is_viable_flip


def _gift(attrs: list[GiftAttributeSchema] | None = None) -> GiftCard:
    return GiftCard(collection="Ice Cream", number=217467, attributes=attrs or [])


def _market(
    recent_sales: list[float] | None = None,
    listings: list[float] | None = None,
    floor: float = 186.0,
    listed_count: int = 120,
    trait_floors: list[float] | None = None,
) -> dict:
    return {
        "collection_floor": floor,
        "trait_floors": [210, 220, 240] if trait_floors is None else trait_floors,
        "similar_listings": [220, 240, 260, 280] if listings is None else listings,
        "recent_sales": [190, 210, 230, 250, 245] if recent_sales is None else recent_sales,
        "listed_count": listed_count,
    }


def test_pricing_returns_reasonable_values():
    gift = _gift(
        [
            GiftAttributeSchema(trait_type="Symbol", trait_value="Moon", rarity_percent=0.7),
            GiftAttributeSchema(trait_type="Backdrop", trait_value="Ivory White", rarity_percent=1.2),
        ]
    )
    estimate = estimate_gift_price(gift, _market(), risk_mode="normal", buy_price_ton=170)
    assert estimate.quick_sell_price_ton > 0
    assert estimate.fair_price_ton >= estimate.quick_sell_price_ton
    assert estimate.list_price_ton >= estimate.fair_price_ton
    assert estimate.optimistic_price_ton >= estimate.fair_price_ton


def test_profit_is_calculated_after_fee():
    estimate = estimate_gift_price(_gift(), _market(), buy_price_ton=170, marketplace_fee_percent=5.0)
    assert estimate.expected_net_sale_ton == round(estimate.list_price_ton * 0.95, 2)


def test_roi_calculated_correctly():
    estimate = estimate_gift_price(_gift(), _market(), buy_price_ton=170, marketplace_fee_percent=5.0)
    expected = (estimate.expected_profit_ton / 170) * 100
    assert round(expected, 2) == estimate.expected_roi_percent


def test_buy_for_flip_not_possible_with_negative_profit():
    weak_market = _market(listings=[150, 155, 160], recent_sales=[145, 150, 155], floor=140, listed_count=260)
    estimate = estimate_gift_price(_gift(), weak_market, buy_price_ton=180, risk_mode="normal")
    assert estimate.expected_profit_ton <= 0
    assert estimate.recommendation != "BUY_FOR_FLIP"


def test_low_liquidity_increases_risk():
    liquid = estimate_gift_price(_gift(), _market(listed_count=80, recent_sales=[200, 205, 210, 215, 220]), buy_price_ton=170)
    illiquid = estimate_gift_price(_gift(), _market(listed_count=400, recent_sales=[205]), buy_price_ton=170)
    assert illiquid.risk_score > liquid.risk_score


def test_few_sales_reduce_confidence():
    many_sales = estimate_gift_price(_gift(), _market(recent_sales=[190, 200, 210, 220, 230, 240]), buy_price_ton=170)
    few_sales = estimate_gift_price(_gift(), _market(recent_sales=[210]), buy_price_ton=170)
    assert few_sales.confidence_score < many_sales.confidence_score


def test_conservative_requires_higher_roi_than_normal():
    conservative = estimate_gift_price(_gift(), _market(), buy_price_ton=185, risk_mode="conservative")
    normal = estimate_gift_price(_gift(), _market(), buy_price_ton=185, risk_mode="normal")
    assert conservative.buy_zone_max_ton < normal.buy_zone_max_ton


def test_aggressive_allows_lower_roi_than_conservative():
    market = _market()
    aggressive = estimate_gift_price(_gift(), market, buy_price_ton=185, risk_mode="aggressive")
    conservative = estimate_gift_price(_gift(), market, buy_price_ton=185, risk_mode="conservative")
    priority = {"BUY_FOR_FLIP": 3, "BUY_ONLY_CHEAP": 2, "HOLD": 1, "LIST_HIGHER": 1, "SELL_FAST": 1, "AVOID": 0}
    assert priority[aggressive.recommendation] >= priority[conservative.recommendation]


def test_rare_trait_without_sales_not_high_confidence():
    rare = _gift([GiftAttributeSchema(trait_type="Symbol", trait_value="Moon", rarity_percent=0.3)])
    estimate = estimate_gift_price(rare, _market(recent_sales=[]), buy_price_ton=170)
    assert estimate.confidence_score <= 60


def test_scan_logic_blocks_bad_roi():
    weak_market = _market(listings=[190, 195, 198], recent_sales=[185, 188], floor=180, listed_count=220)
    estimate = estimate_gift_price(_gift(), weak_market, buy_price_ton=180, risk_mode="normal")
    assert is_viable_flip(estimate, "normal") is False
