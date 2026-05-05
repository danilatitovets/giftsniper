from app.bot.middlewares import EVENT_BY_COMMAND


def test_stage35_event_mappings():
    assert EVENT_BY_COMMAND["/examples"] == "examples_viewed"
    assert EVENT_BY_COMMAND["/how_it_works"] == "how_it_works_viewed"
    assert EVENT_BY_COMMAND["/quick_start"] == "quick_start_viewed"
    assert EVENT_BY_COMMAND["/lite_plan"] == "lite_plan_used"
    assert EVENT_BY_COMMAND["/commands"] == "commands_viewed"
    assert EVENT_BY_COMMAND["/flip_plan"] == "flip_plan_used"
    assert EVENT_BY_COMMAND["/budget_deals"] == "budget_deals_used"
    assert EVENT_BY_COMMAND["/sell_to_buy"] == "sell_to_buy_used"
    assert EVENT_BY_COMMAND["/compound_plan"] == "compound_plan_used"
    assert EVENT_BY_COMMAND["/m4_plan"] == "m4_plan_used"
