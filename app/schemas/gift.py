from pydantic import BaseModel, Field


class GiftAttributeSchema(BaseModel):
    trait_type: str
    trait_value: str
    rarity_percent: float | None = None


class GiftCard(BaseModel):
    collection: str
    number: int
    title: str | None = None
    attributes: list[GiftAttributeSchema] = Field(default_factory=list)
