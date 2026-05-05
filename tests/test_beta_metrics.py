import pytest

from app.services.product_analytics import calculate_activation_metrics, format_beta_metrics_report


class _Session:
    def __init__(self):
        self.scalar_values = [10, 8]

    async def scalar(self, _stmt):
        return self.scalar_values.pop(0)

    async def execute(self, stmt):
        sql = str(stmt)

        class _Exec:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        if "product_events.user_id, product_events.command" in sql:
            return _Exec(
                [
                    (1, "/add"),
                    (1, "/check"),
                    (2, "/check"),
                    (2, "/deals"),
                    (3, "/portfolio"),
                ]
            )
        return _Exec([])


@pytest.mark.asyncio
async def test_activation_metrics_and_report_format():
    activation = await calculate_activation_metrics(_Session(), period_days=7)
    assert activation["new_users"] == 10
    assert activation["activated_users"] == 2
    report = format_beta_metrics_report(
        activation=activation,
        retention={"retained_users": 3},
        funnel={
            "invite_redeemed": 4,
            "checked_gift": 5,
            "added_gift": 2,
            "upgrade_viewed": 1,
            "pay_started": 1,
            "payment_submitted": 1,
            "feedback_count": 2,
        },
        feature={"top_commands": [("/check", 11)]},
    )
    assert "Beta Metrics" in report
    assert "Activation rate" in report
