from app.bot.messages import FREE_FLIP_PLAN_TEASER, LITE_PLAN_TEASER_FOOTER


def test_lite_teaser_footer_mentions_pro():
    assert "Pro" in LITE_PLAN_TEASER_FOOTER or "pro" in LITE_PLAN_TEASER_FOOTER.lower()
    assert "/upgrade" in LITE_PLAN_TEASER_FOOTER


def test_free_flip_plan_teaser_points_to_lite():
    assert "/lite_plan" in FREE_FLIP_PLAN_TEASER
