WELCOME_TEXT = "GiftSniper — бот для анализа Telegram Gifts.\n\n⚠️ Не финансовый совет. Решения о сделках принимаете вы."

HELP_TEXT = (
    "Команды:\n"
    "/start\n/help\n/privacy\n/disclaimer\n/my_plan\n/upgrade\n/billing_status\n/pay <starter|pro|trader>\n/payment_sent <request_id> | <tx_hash_or_note>\n/my_payments\n/add <collection> <number>\n/list\n/gift <id>\n/gift_set_buy <gift_id> <price>\n/gift_set_target <gift_id> <price>\n/bank_set <amount>\n/goal_set <amount>\n/risk_set <max_deal_percent> | <max_collection_percent> | <reserve_percent>\n/bank\n/universe\n/universe_add <collection>\n/universe_remove <collection>\n/universe_on <collection>\n/universe_off <collection>\n/market_regime\n/collection_strength\n/universe_report\n/analyze <id>\n/deal <collection> | <buy_price> | <trait_type?> | <trait_value?>\n/scan\n/scan_all\n/scan_universe\n/market_set_floor <collection> | <price>\n/market_set_trait_floor <collection> | <trait_type> | <trait_value> | <price>\n/market_set_sale <collection> | <number> | <price>\n/market_set_listing <collection> | <number> | <price> | <url?>\n/market_data <collection>\n/market_clear <collection>\n/alerts\n/alerts_check\n/smart_alerts\n/smart_alert_on <type>\n/smart_alert_off <type>\n/smart_alert_set <type> | <threshold> | <cooldown_minutes>\n/smart_alert_settings\n/notify_settings\n/notify_mode <instant|digest|smart>\n/quiet_hours_on 23:00 | 08:00\n/quiet_hours_off\n/min_severity <info|warning|critical>\n/digest_now\n/alert_history\n/incidents\n/incident <id>\n/incident_ack <id>\n/incident_mute <id> | <minutes> | <reason?>\n/incident_unmute <id>\n/incident_resolve <id> | <note?>\n/incident_false_positive <id> | <note?>\n/incident_note <id> | <note>\n/incident_actions <id>\n/incident_analytics\n/recoveries\n/scheduler_status\n/health_dashboard\n/prod_health\n/admin_grant_plan <telegram_id> | <plan> | <days> | <reason?>\n/admin_cancel_plan <telegram_id> | <reason?>\n/admin_extend_plan <telegram_id> | <days> | <reason?>\n/admin_billing_user <telegram_id>\n/admin_billing_events <telegram_id>\n/admin_webhook_events\n/admin_retry_webhook <event_id>\n/admin_payments\n/admin_payments_pending\n/admin_payments_submitted\n/admin_payments_stale\n/admin_payments_confirmed\n/admin_payments_rejected\n/admin_payment_search <query>\n/admin_payment <id>\n/admin_confirm_payment <id> | <days> | <note?>\n/admin_reject_payment <id> | <reason>\n/admin_finance\n/admin_reconcile\n/sources\n/collections\n/collection_info <name>\n/nft_check <address|collection number>\n/portfolio\n/portfolio_rank\n/capital_plan\n/capital_plan_universe\n/rebalance\n/sell_plan\n/settings\n\n⚠️ Бот не гарантирует прибыль и не выполняет автосделки."
)

ALERTS_EMPTY_TEXT = (
    "🚨 У вас пока нет уведомлений.\n\n"
    "Примеры создания:\n"
    "/alert_add Ice Cream | below | 180\n"
    "/alert_add Ice Cream | Symbol | Moon | below | 190"
)

ALERTS_HEADER_TEXT = "🚨 Мои уведомления"

ALERTS_COMMANDS_HINT = (
    "\n\nКоманды:\n"
    "/alert_add Ice Cream | below | 180\n"
    "/alert_add Ice Cream | Symbol | Moon | below | 190\n"
    "/alert_off <id>\n"
    "/alert_on <id>\n"
    "/alert_delete <id>\n"
    "/alert_test <id>\n"
    "/alerts_check"
)

ALERT_ADD_USAGE_TEXT = (
    "Неверный формат.\n\n"
    "Используйте один из примеров:\n"
    "/alert_add Ice Cream | below | 180\n"
    "/alert_add Ice Cream | above | 250\n"
    "/alert_add Ice Cream | Symbol | Moon | below | 190\n"
    "/alert_add Ice Cream | Symbol | Moon | above | 260"
)

ALERT_ID_REQUIRED_DELETE_TEXT = "Используйте: /alert_delete <id>"
ALERT_ID_REQUIRED_ON_TEXT = "Используйте: /alert_on <id>"
ALERT_ID_REQUIRED_OFF_TEXT = "Используйте: /alert_off <id>"
ALERT_ID_REQUIRED_TEST_TEXT = "Используйте: /alert_test <id>"
ALERT_NOT_FOUND_TEXT = "Правило не найдено."
ALERT_CREATED_TEXT = "✅ Уведомление создано"
ALERT_DELETED_TEXT = "🗑 Уведомление #{rule_id} удалено."
ALERT_ON_TEXT = "✅ Уведомление #{rule_id} включено."
ALERT_OFF_TEXT = "⏸ Уведомление #{rule_id} выключено."
ALERTS_CHECK_EMPTY_TEXT = "У вас нет активных уведомлений для проверки."
ALERTS_CHECK_HEADER_TEXT = "🧪 Проверка моих уведомлений"

EXAMPLES_TEXT = (
    "📋 Быстрые сценарии\n\n"
    "1) Проверить подарок:\n"
    "   /check Ice Cream #217467\n"
    "   /check <ссылка>\n\n"
    "2) Посчитать сделку:\n"
    "   /deal Ice Cream #217467 | 180\n\n"
    "3) План на бюджет (Pro/Starter+ полный, Free — /lite_plan):\n"
    "   /flip_plan 300\n"
    "   /lite_plan 300\n\n"
    "4) Найти сделки:\n"
    "   /budget_deals 300\n"
    "   /deals\n\n"
    "5) Продать и переложиться:\n"
    "   /sell_to_buy\n\n"
    "6) Портфель:\n"
    "   /add <ссылка>\n"
    "   /portfolio\n\n"
    "7) Оценить сигнал:\n"
    "   /signal_good <id>\n"
    "   /signal_bad <id>\n\n"
    "8) Оплата:\n"
    "   /upgrade\n"
    "   /pay pro\n\n"
    "Ещё: /quick_start · /how_it_works · /commands"
)

HOW_IT_WORKS_TEXT = (
    "🧠 Как это работает (простыми словами)\n\n"
    "• Бот подтягивает рыночные данные (пол, листинги, недавние продажи — где доступно).\n"
    "• Считает зоны входа: safe buy, max buy, варианты листинга, quick sell и ориентир stop.\n"
    "• Оценивает риск, ликвидность и грубую вероятность продажи — это сценарии, не обещания.\n"
    "• Может собрать план под твой бюджет с резервом и лимитами на сделку.\n"
    "• После покупки можно занести сделку в журнал и позже закрыть с фактической ценой.\n"
    "• Чем больше честных сделок и отзывов по сигналам (/signal_good /signal_bad), тем полезнее калибровка модели.\n\n"
    "Не финансовый совет; автосделок и гарантий прибыли нет."
)

QUICK_START_TEXT = (
    "⚡ Quick start\n\n"
    "Шаг 1 — пришли ссылку или:\n"
    " /check Ice Cream #217467\n\n"
    "Шаг 2 — посчитай сделку:\n"
    " /deal Ice Cream #217467 | 180\n\n"
    "Шаг 3 — задай банк:\n"
    " /bank_set 300\n\n"
    "Шаг 4 — план на бюджет:\n"
    " /lite_plan 300  (Free)\n"
    " /flip_plan 300   (Pro/Starter+)\n\n"
    "Шаг 5 — если купил:\n"
    " /trade_add <signal_id> | <buy_price>\n\n"
    "Шаг 6 — если продал:\n"
    " /trade_sell <trade_id> | <sell_price>\n\n"
    "Домой: /home · примеры: /examples"
)


def build_commands_text(*, is_admin: bool) -> str:
    lines = [
        "📚 Команды по разделам\n",
        "Быстрые:",
        "- /check · /deal · /lite_plan · /flip_plan · /budget_deals · /deals",
        "",
        "Портфель:",
        "- /add · /list · /portfolio · /sell_to_buy · /portfolio_rank",
        "",
        "Бюджет:",
        "- /bank_set · /goal_set · /bank · /compound_plan · /m4_plan · /risk_set",
        "",
        "Universe (Pro):",
        "- /universe_add · /scan_universe · /capital_plan_universe",
        "",
        "Сигналы:",
        "- /signal_good · /signal_bad · /signal_unclear · /signal_outcome",
        "",
        "Журнал:",
        "- /trade_add · /trade_sell · /trades · /trade_stats",
        "",
        "Оплата:",
        "- /my_plan · /upgrade · /pay · /payments · /billing_status",
        "",
        "Справка:",
        "- /examples · /quick_start · /how_it_works · /ref · /help · /home · /menu",
    ]
    if is_admin:
        lines.extend(
            [
                "",
                "Admin (кратко):",
                "- /admin_beta_checklist · /admin_beta_health · /admin_stats · /admin_payments",
                "- /admin_signal_accuracy · /admin_signal_queue · /owner_setup_check",
            ]
        )
    return "\n".join(lines)


UNKNOWN_SLASH_COMMAND_TEXT = (
    "Не знаю такую команду. Я умею проверять NFT/Gift и считать сделки.\n"
    "Пришли ссылку или: /check <ссылка>\n"
    "Примеры: /examples · Меню: /menu"
)

UNKNOWN_PLAIN_TEXT = (
    "Я могу проверить NFT/Gift. Пришли ссылку или используй /check <ссылка>.\n"
    "Примеры: /examples · Быстрый старт: /quick_start"
)

FREE_FLIP_PLAN_TEASER = (
    "На Free полный /flip_plan недоступен (нужен scan по universe).\n\n"
    "Попробуй облегчённый план только по watchlist:\n"
    "/lite_plan <budget_ton>\n\n"
    "Полный план и scan: /upgrade (без давления)."
)

FREE_BUDGET_DEALS_TEASER = (
    "На Free полный /budget_deals недоступен.\n\n"
    "Короткий план по watchlist:\n"
    "/lite_plan <budget_ton>\n\n"
    "Полный топ по universe: /upgrade"
)

LITE_PLAN_TEASER_FOOTER = (
    "\n\n---\nПолный universe scan, regime refresh и capital plan — в Pro (/upgrade). "
    "Сейчас lite смотрит только коллекции из твоего watchlist."
)

BETA_SMOKE_PLAN_TEXT = (
    "📋 Ручной smoke в Telegram (второй аккаунт / тестер)\n\n"
    "1. /start\n"
    "2. /menu\n"
    "3. /check Ice Cream #217467\n"
    "4. /lite_plan 300\n"
    "5. /bank_set 300\n"
    "6. /flip_plan 300 (если план позволяет)\n"
    "7. /signal_good <id>\n"
    "8. /trade_add <signal_id> | 150\n"
    "9. /trade_sell <trade_id> | 180\n"
    "10. /upgrade\n"
    "11. /pay pro\n"
    "12. /payment_sent <id> | test proof\n"
    "13. admin: подтвердить/отклонить оплату\n"
    "14. /admin_beta_health\n"
    "15. /admin_signal_accuracy\n\n"
    "Перед запуском: /beta_launch_check и /smoke_suite"
)

BETA_USER_SCRIPT_TEXT = (
    "📩 Текст для бета-пользователя (скопируй и отправь)\n\n"
    "GiftSniper помогает разобрать Telegram Gift/NFT: рыночные данные, оценка зон входа/выхода, "
    "сценарии сделок и план под бюджет. Это не финансовый совет и не автоторговля — решения только твои.\n\n"
    "Как начать:\n"
    "• Пришли ссылку на подарок или: /check Ice Cream #217467\n"
    "• План на Free: /lite_plan 300 · полный план: /flip_plan 300 (если доступен план)\n"
    "• Обратная связь по сигналам: /signal_good <id> или /signal_bad <id>\n\n"
    "Поддержка и вопросы по бете: см. контакт в объявлении бета-запуска или /help.\n\n"
    "Дисклеймер: бот не гарантирует прибыль, не подключает кошелёк и не просит seed/private key."
)

