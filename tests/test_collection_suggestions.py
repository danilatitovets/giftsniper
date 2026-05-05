from app.sources.collections import load_collection_registry, suggest_collections_with_scores


def test_fuzzy_suggestions_registry():
    reg = load_collection_registry("data/collections.example.json")
    top = suggest_collections_with_scores("Ice Creem", registry=reg, limit=3, min_score=0.55)
    assert top and top[0][0] == "Ice Cream"
