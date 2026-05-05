import pytest

from app.config import get_settings
from app.services.smoke_suite import build_smoke_suite_report, format_smoke_suite_report


class _Sess:
    async def execute(self, *_a, **_k):
        class _R:
            def first(self):
                return (1,)

        return _R()

    async def scalar(self, *_a, **_k):
        return 0


@pytest.mark.asyncio
async def test_smoke_suite_passes_without_external_http(monkeypatch):
    monkeypatch.setattr(
        "app.services.smoke_suite.create_market_source",
        lambda *a, **k: object(),
    )
    report = await build_smoke_suite_report(_Sess(), get_settings(), user_id=1)
    assert report.overall_status in {"GO", "GO_WITH_WARNINGS", "NO_GO"}
    txt = format_smoke_suite_report(report)
    assert "Smoke suite" in txt
    assert "http://" not in txt and "https://" not in txt
