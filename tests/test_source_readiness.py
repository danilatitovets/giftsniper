from types import SimpleNamespace

from app.services.source_readiness import build_source_readiness_summary


def test_mock_in_production_warns(monkeypatch):
    s = SimpleNamespace(
        production_mode=True,
        enable_mock_source=True,
        getgems_enabled=False,
        tonapi_enabled=False,
        collection_registry_path="data/collections.json",
        getgems_base_url="",
        getgems_api_key="",
        tonnel_enabled=False,
        tonnel_base_url="",
        tonnel_api_key="",
        tonapi_base_url="",
        tonapi_api_key="",
        fragment_enabled=False,
        fragment_base_url="",
        fragment_api_key="",
    )

    monkeypatch.setattr(
        "app.services.source_readiness.describe_sources",
        lambda _st: {
            "mock_enabled": True,
            "collections_count": 0,
            "getgems": {"enabled": False, "has_api_key": False},
            "tonapi": {"enabled": False, "has_api_key": False},
            "manual": {"enabled": True},
        },
    )
    r = build_source_readiness_summary(s)
    assert any("mock" in w.lower() for w in r.warnings)
