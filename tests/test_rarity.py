from app.schemas.gift import GiftAttributeSchema
from app.services.rarity import rarity_score


def test_rarity_score_positive_for_rare_traits():
    attrs = [
        GiftAttributeSchema(trait_type="Symbol", trait_value="Moon", rarity_percent=0.7),
        GiftAttributeSchema(trait_type="Model", trait_value="Vice Dream", rarity_percent=3.0),
    ]
    assert rarity_score(attrs) > 0.0
