def normalize_collection_name(name: str) -> str:
    value = " ".join(name.strip().split())
    compact = value.replace("_", " ").replace("-", " ")
    compact = " ".join(compact.split())
    if compact.lower() == "icecream":
        return "Ice Cream"
    return compact.title()


def normalize_trait_type(name: str) -> str:
    mapping = {
        "symbol": "Symbol",
        "backdrop": "Backdrop",
        "model": "Model",
    }
    key = name.strip().lower()
    return mapping.get(key, name.strip().title())


def normalize_trait_value(value: str) -> str:
    return " ".join(value.strip().split()).title()


def build_search_variants(collection: str) -> list[str]:
    normalized = normalize_collection_name(collection)
    variants = {
        normalized,
        normalized.lower(),
        normalized.replace(" ", ""),
        normalized.replace(" ", "_"),
        normalized.replace(" ", "-"),
    }
    return list(variants)
