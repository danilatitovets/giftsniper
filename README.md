# GiftSniper Bot

GiftSniper — Telegram-бот для аналитики и флипа Telegram Gifts / TON NFT.

**Репозиторий:** [github.com/danilatitovets/giftsniper](https://github.com/danilatitovets/giftsniper)

## Репозиторий и секреты

- В git **не** попадают: `.env`, `.env.*` (кроме шаблона `.env.example`), ключи и токены.
- Для продакшена задайте переменные окружения или смонтируйте `.env` на сервере вне VCS.

## Безопасность

- Бот не просит seed-фразы.
- Бот не хранит приватные ключи.
- Бот не подключает кошелек и не подписывает транзакции.
- Бот не делает автопокупки.
- Все секреты только в `.env`.
- Не коммитьте `.env` в git.

## 1) Установка зависимостей

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2) Создание `.env`

```bash
cp .env.example .env
```

Заполните значения:
- `BOT_TOKEN`
- `DATABASE_URL`

## 3) Запуск локально

```bash
alembic upgrade head
python -m app.main
```

## 4) Запуск через Docker

Соберите образ и поднимите бота (нужен файл `.env` рядом с `docker-compose.yml`):

```bash
cp .env.example .env
# отредактируйте .env: BOT_TOKEN, DATABASE_URL, при необходимости TONAPI_API_KEY и др.

docker compose up --build
```

Образ выполняет **`alembic upgrade head`** при старте контейнера (`docker/entrypoint.sh`), затем `python -m app.main`.

Опционально hero-картинка для `/start`: положите `imagen/hero.png` в корень репозитория (папка `imagen/` уже в образе).

Локально без Compose:

```bash
docker build -t giftsniper .
docker run --env-file .env giftsniper
```

## 5) Universal Gift Input (Stage 28–29)

Один и тот же «двигатель» парсинга и резолва используется для `/check`, `/add`, `/deal`, `/nft_check`, пассивных ссылок в чате и `/import_gifts`. Единый анализ для быстрого check — `app/services/gift_analysis_flow.py` (в т.ч. коллбеки пассивного режима для «Проверить»).

**Калибровка URL (beta):** в `tests/fixtures/urls/*.txt` лежат **синтетические** примеры без токенов и сессий. Для продакшн-калибровки замени их на реальные публичные ссылки из беты (не коммить приватные query/auth).

### Что можно присылать боту

- Одну строку: ссылка Getgems / Fragment / Tonviewer / Tonscan / TonAPI (путь к NFT) / `t.me/nft` / `t.me/gifts` / расшаренная `t.me/share/url?url=…`
- NFT address (`EQ` / `UQ` / `workchain:hex`)
- Текст вида `Ice Cream #217467` или с ценой в одной строке для `/deal`: `at 180`, `for 180 TON`, `price 180`, `?price=180`
- Несколько подарков: `/import_gifts` и многострочный ввод (поддерживаются префиксы `1)`, `buy:`, хвост `at 180`, выделение URL из шума)

### Если бот не понял ссылку

- Пришли **коллекцию + номер** (`/check Ice Cream #217467`) или **NFT address**
- Убедись, что ссылка полная (`https://…`), без обрезки
- Напиши **`/feedback`**, если паттерн нужно добавить в парсер

**Поддерживаемые форматы (примеры):**

- Текст: `Ice Cream 217467`, `Ice Cream #217467`, `ice cream / 217467`, `Ice Cream №217467`
- NFT address: `EQ...`, `UQ...`, сырой `workchain:hex`
- Ссылки (только разбор URL, без агрессивного scraping): Getgems, Fragment/Tonnel (эвристики), Tonviewer/Tonscan, `t.me/nft/...`

**Команды:**

- `/check Ice Cream #217467` — при включённом TonAPI и `FULL_MARKET_SCAN_ENABLED` для NFT-ввода (адрес, ссылка, «Коллекция #номер», id из watchlist) только **реальный** отчёт по листингам TonAPI; flip-карточка с mock-ценами для такого ввода не показывается. Для прочего текста `/check` по-прежнему может использовать обычный анализатор (в dev — с mock, если разрешено настройками).
- `/check <NFT address>` или `/check <ссылка>` — то же после резолва
- `/add <то же самое>` — в watchlist; дубликаты по `canonical_key` / `nft_address` / `collection+#` обновляют запись
- `/deal Ice Cream #217467 | 180`, `/deal buy Ice Cream #217467 for 180 TON`, `/deal <url> price 180` или цена из `?price=` / `listing_price=` в URL, если есть
- `/import_gifts` + до 20 строк (или через `;`) — пакетное добавление с учётом `max_gifts` плана
- `/repair_gifts` — починка `canonical_key` / `normalized_collection`, TonAPI enrich при наличии `nft_address`
- Админ: `/admin_repair_user_gifts <telegram_id>`

**Качество данных и confidence:**

- В карточке кратко: Market (real/manual/mock), Sales (recent / no recent), Freshness (fresh/stale/old), причина cap confidence (если есть).
- **Не гарантируем прибыль:** ROI и профит — сценарные оценки, не обещание дохода. При низкой confidence формулировки смягчаются.

**Пассивный режим:** одна строка без команды — мини-карточка, сохранение ввода в **pending** (TTL 15 мин) и inline-кнопки `gift:check:` / `gift:add:` / `gift:deal:` / `gift:cancel:` с коротким id; «Проверить» вызывает тот же `run_gift_check`, что и `/check`. На произвольный текст бот не отвечает.

## 6) Как включить mock-данные

Установите в `.env`:

```env
ENABLE_MOCK_SOURCE=true
```

Периодические проверки уведомлений:
- `CHECK_INTERVAL_MINUTES` — как часто scheduler проверяет правила.
- `ALERT_COOLDOWN_MINUTES` — антиспам-пауза между повторными уведомлениями по одному правилу.
- `DEFAULT_MARKETPLACE_FEE_PERCENT` — комиссия маркетплейса для расчета чистой выручки.
- `ESTIMATED_EXTRA_COSTS_TON` — дополнительные издержки на сделку.
- `MIN_PROFIT_TON` — минимальная целевая прибыль для flip-рекомендаций.
- `GETGEMS_ENABLED` / `TONNEL_ENABLED` / `FRAGMENT_ENABLED` — включение источников.
- `GETGEMS_BASE_URL` / `TONNEL_BASE_URL` / `FRAGMENT_BASE_URL` — base URL источников.
- `GETGEMS_API_KEY` / `TONNEL_API_KEY` / `FRAGMENT_API_KEY` — опциональные ключи.
- `TONAPI_ENABLED`, `TONAPI_BASE_URL`, `TONAPI_API_KEY` — настройки TonAPI (on-chain metadata/history).
- `MARKET_HTTP_TIMEOUT_SECONDS`, `MARKET_HTTP_RETRIES`, `MARKET_HTTP_USER_AGENT` — безопасные HTTP-параметры.
- `COLLECTION_REGISTRY_PATH` — путь к локальному registry с source identifiers.
- `FRESH_FLOOR_MAX_MINUTES`, `STALE_FLOOR_MAX_MINUTES`, `OLD_FLOOR_MAX_MINUTES` — пороги свежести floor/trait/listings.
- `RECENT_SALES_MAX_DAYS` — продажи старше этого окна считаются старыми для confidence.

## 7) Как подключить реальные источники позже

- Реализуйте методы в `app/sources/getgems.py`
- Реализуйте методы в `app/sources/tonnel.py`
- Реализуйте методы в `app/sources/fragment.py`
- Оставьте fallback на `app/sources/mock.py`

## Registry коллекций

1. Скопируйте `data/collections.example.json` в `data/collections.json`.
2. Для нужной коллекции заполните `getgems.collection_address`.
   Пример публичного адреса (Ice Cream): `EQBUvskEvmWdp_V6HX-2Tyfp4mFSzMzdg9TaUz6zKVz6Ov3f`.
3. Без `collection_address` Getgems не сможет дать real floor и вернет safe empty result.
4. `data/collections.json` локальный и не коммитится в git.
5. Для проверки registry используйте:
   - `python scripts/check_collection_registry.py`
   - `/collections`
   - `/collection_info Ice Cream`

## Capture реальных Getgems payload

- Команда: `python scripts/capture_getgems_payload.py --collection "Ice Cream"`
- Скрипт сохраняет sanitized fixtures в `tests/fixtures/getgems/real/`.
- Для Getgems v1 нужен API key; без него capture корректно завершится с предупреждением.
- Если `collection_address` не задан, скрипт корректно сообщает об этом и завершается без падения.
- Real fixtures необязательны для обычного CI: тесты с ними автоматически `skip`, если файлов нет.

## Market Source Aggregator

- `app/sources/aggregator.py` объединяет данные из нескольких источников.
- Агрегатор делает дедупликацию listing/sales, сортирует данные и выбирает лучший floor.
- Если часть источников недоступна, бот не падает и помечает это в data quality warnings.
- Если реальные источники пока пустые, используется fallback на mock-данные.
- Quality layer снижает confidence, когда данные частичные или только mock.
- Это защищает от излишне уверенных рекомендаций на слабых данных.
- Команда `/sources` показывает состояние источников и предупреждения без вывода API ключей.
- Отдельный discovery-отчет по источникам: `docs/market_sources.md`.

## TonAPI (read-only)

- TonAPI используется для on-chain данных: metadata, collection info, owner, history.
- Для агрегатора `/check` основной маркетплейс-поток по-прежнему идёт через Getgems и другие market sources; TonAPI **не подменяет** их как единственный источник цен для вердикта сделки.
- Отдельно: полный скан **активных листингов** коллекции (`sale.price` в TonAPI) используется только командами **`/sell_price`**, **`/price_nft`**, **`/value_nft`** — это read-only оценка листинга, без автопокупки и без mock-цен для этого режима.
- Получите API key в TonAPI и добавьте в `.env`:
  - `TONAPI_ENABLED=true`
  - `TONAPI_BASE_URL=https://tonapi.io`
  - `TONAPI_API_KEY=...`
- Проверка через бота:
  - `/sources`
  - `/nft_check <nft_address>`

## Real Full Market NFT Pricing (/sell_price)

Команды:

- `/sell_price <NFT>` — рекомендация цены листинга по **реальным** активным продажам TonAPI (`sale.price`), полный проход коллекции с пагинацией.
- `/price_nft <NFT>` и `/value_nft <NFT>` — те же алиасы.

Что делает:

- Принимает NFT address (`workchain:hex`, EQ/UQ), ссылку (через Universal Gift Input), или текст вида `Ice Cream #217467`.
- Тянет метаданные NFT и адрес коллекции; при вводе по названию ищет **`tonapi.collection_address`** в `data/collections.json` (см. `collections.example.json`).
- Сканирует коллекцию через TonAPI (`/v2/nfts/collections/{address}/items`), считает floor/медиану листингов, сравнивает по **Model / Backdrop / Symbol** (Model важнее Backdrop).
- Выдаёт ориентиры: быстрый листинг, нормальный, «дорого/терпеливо», нижнюю границу; помечает confidence и предупреждает про выбросы по цене.
- Использует **in-memory TTL-кэш** рынка коллекции (`FULL_MARKET_CACHE_TTL_SECONDS`, по умолчанию 15 минут), чтобы не дергать десятки тысяч NFT на каждый запрос.
- Длинный скан сопровождается сообщением прогресса в чате; при **429** TonAPI бот делает backoff и может показать статус ожидания.

Ограничения:

- Нужен **`TONAPI_API_KEY`**; без ключа бот честно сообщает, что реальный рынок недоступен.
- Это оценка по **активным листингам**, не гарантия продажи и не замена истории сделок.
- Для этого режима **не используются mock-источники** торговых цен.

Связанные переменные `.env`: `FULL_MARKET_SCAN_ENABLED`, `FULL_MARKET_MAX_ITEMS`, `FULL_MARKET_PAGE_LIMIT`, `FULL_MARKET_CACHE_TTL_SECONDS`, `FULL_MARKET_REQUEST_SLEEP_MS`, `FULL_MARKET_PROGRESS_EVERY_ITEMS`, и др. — см. `.env.example`.

## Manual Market Data Mode

Если нет `GETGEMS_API_KEY`, можно использовать ручные данные рынка:
- `/market_set_floor Ice Cream | 186`
- `/market_set_trait_floor Ice Cream | Symbol | Moon | 240`
- `/market_set_sale Ice Cream | 217467 | 230`
- `/market_set_listing Ice Cream | 217467 | 220 | https://...`
- `/market_data Ice Cream`
- `/market_clear Ice Cream`

Manual данные user-scoped: каждый пользователь видит и меняет только свои записи.
Ручные данные могут устаревать, это отражается в warnings и confidence caps.
Обновляйте floor/trait/sales регулярно, иначе бот снижает confidence и повышает риск.

## Data Freshness Layer

GiftSniper оценивает возраст floor/trait/listings/sales:
- `fresh` — младше 60 минут
- `stale` — от 1 часа до 12 часов
- `old` — старше 12 часов
- `unknown` — нет timestamp

Почему это важно:
- старые данные опасны: рынок мог сдвинуться, а расчет останется слишком оптимистичным;
- поэтому бот автоматически снижает confidence, повышает risk и ограничивает рекомендации на старых данных;
- `BUY_FOR_FLIP` блокируется, если данные old и нет актуальных recent sales.

## Opportunity Score & Tiers

GiftSniper ранжирует сделки по `Opportunity Score (0-100)`:
- ROI: 25%
- Expected profit: 20%
- Liquidity: 15%
- Confidence: 15%
- Freshness: 10%
- Source quality: 10%
- Risk penalty: -15%

Тиры:
- `S_TIER` — сильный real/fresh сигнал
- `A_TIER` — хороший кандидат
- `B_TIER` — рабочий, но с ограничениями
- `C_TIER` — слабый/сомнительный
- `AVOID` — сделку лучше пропустить

Почему высокий ROI не всегда хорошо:
- низкая ликвидность, stale/old данные, manual/mock сигнал и слабый confidence снижают итоговый score.
- mock сигналы ограничиваются максимумом `C_TIER`.
- manual stale сигналы ограничиваются максимумом `B_TIER`.

## Bankroll & Portfolio Management

Настройка капитала:
- `/bank_set 500` — задать банк в TON
- `/goal_set 50000` — задать цель
- `/risk_set 25 | 40 | 20` — max per deal / max per collection / reserve
- `/bank` — проверить текущие лимиты

Планирование:
- `/portfolio_rank` — ранжирование текущих подарков, действия и downside-сценарии
- `/capital_plan` — как распределить доступный капитал по топ-идеям
- `/sell_plan` — что продавать первым, где list/quick/stop

Почему не стоит заходить всем банком в одну сделку:
- даже высокий ROI может быть на неликвидном или stale сигнале;
- лимиты по сделке/коллекции снижают риск концентрации;
- reserve нужен, чтобы пережить просадку и не продавать в панике.

## Universe & Dynamic Budgeting

Команды universe:
- `/universe`
- `/universe_add <collection>`
- `/universe_remove <collection>`
- `/universe_on <collection>`
- `/universe_off <collection>`

Скан и капитал по нескольким коллекциям:
- `/scan_universe` — единый рейтинг лучших сделок по active коллекциям.
- `/capital_plan_universe` — dynamic allocation по tier/quality/freshness/risk.
- `/rebalance` — подсказки по снижению концентрации риска.

Dynamic allocation:
- `S_TIER` до 100% max per deal
- `A_TIER` до 75%
- `B_TIER` до 40%
- `C_TIER/AVOID` не берутся в основной план
- stale/no-sales/low-confidence/high-risk дополнительно режут размер входа.

Diversification score учитывает концентрацию по коллекциям и traits.
Если подходящих сделок нет, бот честно рекомендует держать кэш.

## Market Regime Awareness

Новые режимы рынка:
- `risk_on`
- `neutral`
- `risk_off`
- `illiquid`
- `data_poor`

Команды:
- `/market_regime` — общий режим по universe и рекомендации по риску.
- `/collection_strength` — сравнительная сила коллекций и их статус.
- `/universe_report` — полный отчет: regime, сильные/слабые коллекции, top opportunities, риски концентрации.

Как режим влияет на allocation:
- `risk_on`: 100%
- `neutral`: 75%
- `risk_off`: 45%
- `illiquid`: 25%
- `data_poor`: 30%

В слабых режимах бот поднимает требования к ROI и чаще советует держать кэш.
Collection strength помогает понять, какие коллекции приоритизировать, а какие временно не трогать.

## Smart Alerts & Health Dashboard

Smart alerts:
- `/smart_alerts`
- `/smart_alert_on <type>`
- `/smart_alert_off <type>`
- `/smart_alert_set <type> | <threshold> | <cooldown_minutes>`
- `/smart_alert_settings`

Типы smart alerts:
- `regime_change`
- `strength_drop`
- `liquidity_crash`
- `data_stale`
- `concentration_risk`
- `rebalance_needed`
- `stay_in_cash`

Anti-noise:
- cooldown по каждому типу
- payload hash: одинаковые сигналы повторно не отправляются

`/health_dashboard` показывает market regime, статус universe, число активных smart alerts, freshness summary и ключевые риски.

Дисклеймер: все alerts носят аналитический характер и не являются финансовым советом.

## Incidents, Escalation, Recovery

Event vs Incident:
- Event — единичный сигнал smart alert.
- Incident — продолжающаяся проблема (группа повторяющихся событий).

Команды:
- `/incidents`
- `/incident <id>`
- `/recoveries`
- `/incident_ack <id>`
- `/incident_mute <id> | <minutes> | <reason optional>`
- `/incident_unmute <id>`
- `/incident_resolve <id> | <note optional>`
- `/incident_false_positive <id> | <note optional>`
- `/incident_note <id> | <note>`
- `/incident_actions <id>`
- `/incident_analytics`

Как работает escalation:
- повторяющиеся warning могут эскалироваться в critical;
- одинаковые payload suppress-ятся, чтобы не спамить;
- digest группирует ongoing incidents отдельно.

Recovery:
- при улучшении условий incident закрывается (`recovered`);
- бот отправляет recovery notification.

Почему бот не спамит:
- payload hash anti-duplicate
- cooldown
- incident grouping + suppression

Operator controls и шум:
- `ack` помечает incident как просмотренный и подавляет повторы warning/info до escalation.
- `mute` временно отключает delivery по incident (саму проблему не исправляет).
- `resolve` закрывает incident вручную с заметкой.
- `false_positive` исключает incident из recurring analytics и подавляет одинаковые payload в будущем.
- `/incident_analytics` показывает open/critical/recovered, average TTR, recurring типы и false-positive rate.

## Deal Calculator

- `/deal Ice Cream | 170`
- `/deal Ice Cream | 170 | Symbol | Moon`
- `/deal <url> | 180` или текст с `price 180` / `for 180 TON`

Команда показывает safe buy / max buy, list-диапазон, quick sell, stop, net sale, profit/ROI, liquidity/risk/confidence, `decision_type` и tier/score.
Это read-only аналитика: нет гарантий прибыли, нет автопокупки и wallet connect.

### Precision Pricing Brain (Stage 30)

- **Safe buy** — консервативный потолок входа с учётом комиссии, min profit, целевого ROI и штрафов за слабые данные.
- **Max buy** — верхняя граница, выше которой сделка обычно слабеет относительно модели.
- **Aggressive buy** — узкая зона между safe и max (не призыв к действию).
- **Quick flip / normal / high list** — уровни выставления; high list только при сильной ликвидности и подтверждённых продажах.
- **Quick sell** — ориентир быстрого выхода; **stop** — ориентир риск-менеджмента (не гарантирует исполнение).
- **Confidence / liquidity** — насколько модель доверяет данным и глубине рынка.
- **Rare but illiquid** — редкий trait без продаж не должен один удваивать цену; бот помечает спекулятивные сценарии.

Команды market brain:
- `/market_intel Ice Cream` — профиль коллекции: floor, sales, spread, liquidity, stability, warnings.
- `/trait_intel Ice Cream | Backdrop | Monochrome` — профиль trait: premium, sales, liquidity, overpay risk.
- `/rare_deals Ice Cream` — эвристический поиск trait-gap возможностей (нужны атрибуты в листингах).
- `/price_plan Ice Cream #217467 | 180` — только precision plan (можно без цены для ориентиров).

### Market Intelligence & Rarity Engine 2.0

- Коллекционный профиль сочетает листинги и продажи: много листингов при малых sales → предупреждение о неликвидности.
- Trait premium без sales помечается как возможный «фейковый» премиум.
- Важные traits задаются `IMPORTANT_TRAIT_KEYWORDS` в `.env` (Monochrome — частный случай keyword, не отдельный хардкод-движок).

### Decision types

`STRONG_BUY`, `BUY_IF_UNDER`, `SPECULATIVE_BUY`, `HOLD`, `LIST_NOW`, `LIST_HIGH`, `QUICK_SELL`, `AVOID`, `NEED_MORE_DATA` — отображаются в карточках и влияют на tier/capital rules. При низком confidence агрессивный зелёный buy не показывается.

### Safety rules

- Нет формулировок «точно», «гарантированно», «100%».
- Mock-only и stale/manual данные режут confidence и tier.
- Нет советов по манипуляциям рынком.

`/scan` показывает строгий топ-5 кандидатов (учитывается `decision_type` и max buy).
`/scan_all` показывает и сильные, и сомнительные варианты для отладки.

## Purchase Price / Target

- `/gift_set_buy <gift_id> <price>`
- `/gift_set_target <gift_id> <price>`

`/gift` и `/analyze` показывают buy/target и считают ROI от фактической цены покупки.
Если buy price не задан, бот пишет: `ROI расчетный, потому что цена покупки не указана`.

## 8) Предупреждение

Никогда не коммитьте `.env` и не печатайте `BOT_TOKEN`/`DATABASE_URL` в логах.

## Plans, Limits, and Admin

Планы:
- `free`: до 3 gifts, до 2 universe collections, без smart alerts и incidents.
- `starter`: до 10 gifts, до 5 collections, базовые alerts.
- `pro`: smart alerts, scan_universe, incidents, расширенный capital plan.
- `trader`: повышенные лимиты и production-ready режим использования.

Админ-настройка:
- задайте `ADMIN_TELEGRAM_IDS` в `.env` (comma-separated);
- или назначьте пользователю `role=admin`.

Admin команды:
- `/admin_user <telegram_id>`
- `/admin_set_plan <telegram_id> | <plan> | <days?>`
- `/admin_set_role <telegram_id> | <role>`
- `/admin_block <telegram_id>`
- `/admin_unblock <telegram_id>`
- `/admin_stats`

Rate limiting:
- `RATE_LIMIT_COMMANDS_PER_MINUTE`
- `RATE_LIMIT_HEAVY_COMMANDS_PER_HOUR`
- heavy commands: `/scan`, `/scan_universe`, `/capital_plan_universe`, `/universe_report`, `/market_regime`, `/collection_strength`
- MVP реализация in-memory, TODO для production: Redis.

Privacy и disclaimer:
- `/privacy`
- `/disclaimer`

Production checklist:
- `/prod_health` (admin only) для DB/migrations/runtime/env sanity.
- Убедитесь, что `PRODUCTION_MODE=true` в проде.
- Убедитесь, что `.env` исключен из git.
- Если токен бота когда-либо попадал в README, чат или логи — **ROTATE TELEGRAM BOT TOKEN** перед продом (выпустите новый токен у @BotFather и обновите `BOT_TOKEN`).

### Почему бот может не назвать цену? (Stage 37)

- Нет **real** или **manual** рыночных данных (floor / listings / sales) — TonAPI даёт метаданные, но **не** заменяет цену листинга.
- В **production** при `BLOCK_TRADING_VERDICT_ON_MOCK=true` и без `ALLOW_MOCK_IN_PRODUCTION` mock **не** используется для торговых цен; бот честно пишет, что данных недостаточно.
- Быстрый ручной ввод: `/market_quick <коллекция> | floor=… | sale=… | listing=… | num=…` или отдельные `/market_set_*`; проверка источников: `/sources`.

Secret rotation checklist:
- **ROTATE TELEGRAM BOT TOKEN** (обязательно, если токен мог утечь)
- rotate TonAPI key
- rotate Supabase password
- validate `.env` ignore rules and revoke leaked tokens immediately

## Billing / Entitlements

Stage 21 adds subscription architecture (no real payments yet):
- `user_entitlements` (state machine): `active / trialing / past_due / grace / expired / canceled / manual`
- `billing_events` (billing trail and anti-spam event history)
- `entitlement_overrides` (admin/manual overrides with optional expiry)

Lifecycle:
- active plan works until `expires_at`
- after expiry -> `grace` (`BILLING_GRACE_PERIOD_DAYS`, default 3)
- after grace -> `expired` and downgrade to `free`
- admin override has highest priority

User commands:
- `/my_plan`
- `/upgrade`
- `/billing_status`

Admin billing commands:
- `/admin_grant_plan <telegram_id> | <plan> | <days> | <reason?>`
- `/admin_cancel_plan <telegram_id> | <reason?>`
- `/admin_extend_plan <telegram_id> | <days> | <reason?>`
- `/admin_billing_user <telegram_id>`
- `/admin_billing_events <telegram_id>`

Provider abstraction:
- `app/services/billing_providers/base.py`
- `app/services/billing_providers/manual.py` (MVP provider, no real webhook payment flow)

Compliance:
- no card data storage
- no seed/private keys
- no wallet connect
- no auto-buy

TODO (future Stage 22):
- real provider webhook verification and idempotency
- dedicated web endpoint for billing callbacks
- retry and dead-letter strategy for webhook processing

## Stage 22 Webhook Infrastructure (Mock)

Added secure webhook pipeline for future providers, currently using mock only:
- `payment_webhook_events` table stores sanitized payload/headers and processing state.
- Idempotency via `(provider, provider_event_id)` and duplicate handling.
- Status flow: `received -> processing -> processed` or `failed -> dead_letter`, plus `duplicate/ignored`.
- Retry support for failed events with max attempts (`BILLING_WEBHOOK_MAX_ATTEMPTS`).

Mock provider:
- `app/services/billing_providers/mock.py`
- HMAC SHA256 signature with `MOCK_BILLING_WEBHOOK_SECRET`
- Supported events:
  - `mock.checkout.completed`
  - `mock.subscription.renewed`
  - `mock.subscription.canceled`
  - `mock.payment.failed`

Webhook service:
- `app/services/billing_webhooks.py`
- sanitizes payload/headers
- verifies signature
- maps provider events to entitlement actions
- writes `billing_events` + `payment_webhook_events`

Web skeleton:
- `app/web/app.py`
- `app/web/billing.py`
- endpoint design: `POST /webhooks/billing/{provider}`
- bot polling startup unchanged; web server should run separately.

Test sender:
- `python scripts/send_mock_billing_webhook.py --telegram-id 123456 --plan pro --days 30 --event checkout.completed`

Why no real payments yet:
- no real provider keys/charges in Stage 22
- no card data storage
- no crypto auto-payments
- safe architecture first, provider integration later

## Stage 23 Manual Crypto Payments + Owner Access

Owner setup (после деплоя):
- `/admin_set_role 943071273 | owner`
- `/admin_grant_plan 943071273 | trader | 36500 | owner lifetime access`

Owner/Admin bypass:
- `owner` и `admin` имеют unlimited feature access (кроме blocked users).
- blocked user остается blocked даже с role owner/admin.

Manual crypto payment (TON) flow:
- user: `/pay pro` или `/pay trader`
- user sends payment to TON wallet from config:
  - `OWNER_CRYPTO_WALLET_TON=UQBE72wYg608Yc6SfddpPI-_3A0f8Gv9Ap3zjr5f7xu5yec8`
- user confirms: `/payment_sent <request_id> | <tx_hash_or_note>`
- admin reviews: `/admin_payments`, `/admin_payment <id>`
- admin confirms: `/admin_confirm_payment <id> | <days> | <note?>`
- admin rejects: `/admin_reject_payment <id> | <reason>`

Pricing MVP:
- starter = 10 TON / 30 days
- pro = 25 TON / 30 days
- trader = 60 TON / 30 days

Safety:
- no wallet connect
- no seed/private key storage
- no auto-buy
- access activates only after manual admin confirmation
- if user sends to wrong address/network, bot cannot auto-refund

## Команды бота

- `/start`
- `/add`
- `/list`
- `/gift <id>`
- `/analyze <id>`
- `/scan`
- `/alerts`
- `/alerts_check`
- `/sources`
- `/collections`
- `/collection_info <name>`
- `/portfolio`
- `/settings`

Быстрая проверка:
- `/sources`
- `/collections`
- `/collection_info Ice Cream`
- `/analyze 1`

Scheduler проверяет активные alert rules каждые `CHECK_INTERVAL_MINUTES` и отправляет уведомления только при выполнении условий с антиспам-кулдауном.

Бот только анализирует и уведомляет. Он не покупает и не продает активы автоматически.

## Profit Engine

`/analyze` считает flip-экономику:
- buy zone, quick/fair/list/optimistic/stop цены
- чистую выручку после комиссии
- ожидаемый профит и ROI
- liquidity/risk/confidence score
- рекомендацию `BUY_FOR_FLIP`, `BUY_ONLY_CHEAP`, `HOLD`, `LIST_HIGHER`, `SELL_FAST`, `AVOID`

Profit Engine учитывает не только редкость, но и ликвидность, продажи, похожие листинги и комиссию.

Confidence ограничивается quality caps:
- mock data: максимум 60
- manual floor only: максимум 65
- manual floor + trait floors: максимум 70
- manual floor + trait floors + sales: максимум 75
- real floor only, no sales: максимум 70
- real floor + listings, no sales: максимум 75
- выше только при более полной real data картине.

Бот не гарантирует прибыль. Это аналитический инструмент, сделки пользователь принимает вручную.

## Windows команды

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python -m app.main
```

## Stage 24: Ops & Financial Control Layer

Manual crypto payment operations upgraded for production control:
- `MANUAL_PAYMENT_REQUEST_TTL_HOURS` expires old `pending` requests via scheduler.
- `MANUAL_PAYMENT_SUBMITTED_SLA_HOURS` marks late `submitted` requests as stale for moderation.
- `ADMIN_PAYMENT_ALERT_COOLDOWN_MINUTES` prevents admin alert spam for stuck requests.

Admin moderation queue:
- `/admin_payments` (pending + submitted short queue)
- `/admin_payments_pending`
- `/admin_payments_submitted`
- `/admin_payments_stale`
- `/admin_payments_confirmed`
- `/admin_payments_rejected`
- `/admin_payment_search <query>`

Finance / reconciliation:
- `/admin_finance` shows confirmed 30d revenue, MRR estimate, ARPU, status counts, revenue by plan.
- `/admin_reconcile` shows mismatches between confirmed manual payments, entitlements, billing events and user plan sync.

User visibility:
- `/my_payments` now highlights `expired`, stale submitted requests and reject notes.
- `/billing_status` now includes payment summary and mismatch warning.

Security model remains strict:
- no wallet connect,
- no seed phrase requests,
- no private key storage,
- no auto-charge,
- no automatic crypto payment confirmation without manual operator validation.

## Stage 25: UX Simplification & Closed Beta Launch

User UX shortcuts:
- `/menu` opens main keyboard menu.
- `/home` shows compact dashboard (plan, watchlist, universe, alerts, incidents, bankroll/goal).
- `/check` is a friendly alias for quick gift checks.
- `/deals` auto-picks best scan mode (`/scan_universe` for Pro/Trader with universe, else `/scan`).
- `/plan` alias for `/my_plan`.
- `/payments` alias for `/my_payments`.

Closed beta invite flow:
- Admin creates invite code: `/admin_create_invite <code> | <plan> | <days> | <max_uses>`
- Admin lists active invites: `/admin_invites`
- Admin disables invite: `/admin_disable_invite <code>`
- User redeems invite: `/redeem <code>`

Feedback collection:
- `/feedback <text>`
- `/bug <text>`
- `/feature <text>`
- `/deal_case <text>`
- Admin moderation: `/admin_feedback`, `/admin_feedback <id>`, `/admin_feedback_close <id> | <note?>`

Beta readiness:
- `/admin_beta_status` shows beta operational counters and warnings.

### Beta Checklist
1. Set owner:
   - `/admin_set_role 943071273 | owner`
   - `/admin_grant_plan 943071273 | trader | 36500 | owner lifetime access`
2. Create invite:
   - `/admin_create_invite beta100 | pro | 14 | 100`
3. Give users:
   - `/redeem beta100`
4. Collect:
   - `/feedback`
   - `/bug`
   - `/deal_case`

## Stage 26: Closed Beta Operations & Retention

Closed beta operations now include cohort analytics, retention tracking, triage SLA, signal quality feedback, smarter UX actions, and owner reporting.

### Activation definition

User is considered **activated** when they use at least 2 commands from:
- `/add`
- `/check`
- `/deal` or `/deals`
- `/portfolio`
- `/bank_set`
- `/redeem`

### Product analytics and metrics

- `product_events` table stores key product events for beta operations.
- Command activity tracking on each command updates:
  - `users.last_seen_at`
  - `users.first_seen_at` (if empty)
  - `users.command_count += 1`
- Admin metrics command:
  - `/admin_beta_metrics`
  - includes new users, active users, activated users, activation rate, retained users, funnel and top commands.

### Feedback triage SLA

Feedback triage fields:
- `feedback_items.reviewed_at`
- `feedback_items.reviewed_by_user_id`
- `feedback_items.priority` (`low|normal|high|urgent`)

Admin SLA commands:
- `/admin_feedback_review <id> | <priority optional> | <note optional>`
- `/admin_feedback_priority <id> | <low|normal|high|urgent>`
- `/admin_feedback_sla`

### Signal quality feedback

Users can quickly report signal quality:
- `/signal_good <text optional>`
- `/signal_bad <text optional>`

Admin review:
- `/admin_signal_feedback`

### One-tap UX and smarter home

- `/menu` buttons map to command hints and quick actions:
  - check, portfolio, deals, capital plan, alerts, my plan, settings, help.
- `/home` next actions adapt to current state:
  - no gifts, no bank, free plan limit reached, stale payment submissions, open incidents, pro universe scan readiness, no feedback after 3+ commands.

### Owner weekly summary

Manual command:
- `/admin_weekly_summary`

Optional scheduler:
- `OWNER_WEEKLY_SUMMARY_ENABLED=false`
- `OWNER_WEEKLY_SUMMARY_DAY=MON`
- `OWNER_WEEKLY_SUMMARY_HOUR=10`

Sent only to `ADMIN_TELEGRAM_IDS`.

### Beta health dashboard

Command:
- `/admin_beta_health`

Shows:
- activation health
- feedback health
- payment ops health
- incident noise health
- data quality health
- top problems
- recommended actions

### Closed beta operating guide

Daily checklist:
1. `/admin_beta_health`
2. `/admin_payments_stale`
3. `/admin_feedback_sla`
4. `/admin_reconcile`

Weekly checklist:
1. `/admin_weekly_summary`
2. Review activation rate
3. Review signal feedback
4. Update UX/pricing/limits

## Stage 27: Closed Beta Launch Readiness, QA Gate & Owner OS

### Beta mode and access gate

Environment flags:
- `BETA_MODE=true`
- `BETA_MAX_USERS=50`
- `BETA_REQUIRE_INVITE=true`
- `BETA_SUPPORT_USERNAME=@deliverrrrrr`
- `BETA_FEEDBACK_REMINDER_COMMAND_THRESHOLD=5`

Access rules:
- owner/admin/tester bypass gate
- users with active paid/promo/manual access are allowed
- redeemed invite users are allowed
- if invite is required and user has no access, bot shows a soft beta-gate message and `/redeem` hint

### Owner setup and release checks

Commands:
- `/owner_setup_check`
- `/release_check`
- `/smoke_test`
- `/beta_go_no_go`

`/release_check` returns:
- `GO`
- `GO_WITH_WARNINGS`
- `NO_GO`

### Signal quality and cohort control

Commands:
- `/admin_signal_quality`
- `/admin_cohort_report`

Signal quality report includes good/bad ratio, latest reasons/examples, and recommendations.

### Payment funnel instructions

Upgrade/payment flow:
- `/upgrade` explains plan fit and manual TON process
- `/pay <plan>` returns wallet, request id, amount, and short checklist
- after payment send `/payment_sent <id> | <tx_hash>`

### Closed Beta Runbook

Day 0 — preparation:
1. rotate secrets
2. set owner
3. run `/owner_setup_check`
4. run `/release_check`
5. run `/smoke_test`
6. create invite
7. test redeem on second account

Day 1 — 5 users:
1. issue invites
2. monitor `/admin_beta_health`
3. check `/admin_feedback_sla`
4. check `/admin_payments_stale`
5. check `/admin_reconcile`

Day 3 — review:
1. `/admin_beta_metrics`
2. `/admin_weekly_summary`
3. signal feedback (`/admin_signal_quality`)
4. decide UX fixes

Day 7 — scale to 20-50 users:
1. fix top 3 problems
2. update onboarding copy
3. create new invite
4. monitor payment funnel

### Stage 31 — Pricing calibration, backtesting, trade journal

**Pricing calibration** — scenario JSON under `tests/fixtures/calibration/scenarios/`. Service: `app/services/pricing_calibration.py` (`load_calibration_scenarios`, `run_calibration_scenario`, `format_calibration_report`). Used to QA that safe/max/list bands and decisions stay aligned after changes.

**Backtesting** — `app/services/backtesting.py` pairs synthetic or real trades with `BacktestPrediction` and aggregates win rate, pricing error, heuristics (`run_backtest`, `format_backtest_report`). No live execution.

**Trade journal** — table `trade_journal` (migration `0026_trade_journal`): `/trade_add`, `/trade_sell`, `/trade_cancel`, `/trades`, `/trade <id>`, `/trade_stats`. On add, a prediction snapshot is stored (`prediction_json` + typed columns) for later comparison.

**Accuracy report** — `/accuracy_report` (per user), `/admin_accuracy_report` (admin aggregate). Compares closed trades to predicted max buy / list; suggestions are heuristic, not financial advice.

**Confidence calibration** — `app/services/confidence_calibration.py`: coverage score, caps when sales/trait sales/mock/stale are weak. `/price_plan` includes a short confidence explanation via `format_confidence_explanation`.

**Decision quality gates** — `app/services/decision_engine.py`: `STRONG_BUY` requires config thresholds (`PRICING_STRONG_BUY_*`), recent sales when enabled, liquidity, risk, and no critical warnings; rare traits without sales do not unlock aggressive strong buy in the analyzer/scanner path.

**Market cache** — `app/services/market_cache.py` in-memory TTL cache for collection/trait intel and rare-deals scan. Admin: `/market_cache_status`, `/market_cache_clear` (optional collection filter). TODO: Redis for multi-worker.

**Why price changed** — `app/services/price_explain.py`; `/recheck_trade <id>` compares stored `precision_plan_json` to a fresh analysis.

**Disclaimers (important)**:
- Safe buy is a risk anchor, not a promise of profit.
- Max buy is a deal ceiling, not a target to chase regardless of liquidity.
- `STRONG_BUY` is suppressed without recent sales when `PRICING_STRONG_BUY_REQUIRE_RECENT_SALES=true`.
- Rare trait without confirming sales stays speculative; Monochrome-like keywords can justify attention but not automatic buys.
- The bot may effectively say “hold cash” when data is stale, spread is huge, or confidence is capped.

### Stage 32 — Real trade import, pricing tuning, accuracy optimization

**CSV import** — `app/services/trade_import.py`: `parse_trade_csv`, `validate_trade_row`, `import_trades_for_user`. Commands: `/trade_import_help`, `/trade_import_preview` (CSV in lines after the command), `/trade_import_commit`. Admin: `/admin_trade_import_preview <telegram_id> | <CSV>` and `/admin_trade_import_commit` (same shape). Плохие строки пропускаются, хорошие импортируются. Вложения `.csv` в MVP не требуются — текстом.

**Export** — `/trade_export`: CSV с id, ценами, статусом, realized PnL/ROI (если есть), прогнозными полями.

**Pricing tuning** — `app/services/pricing_tuner.py`: `analyze_pricing_accuracy`, эвристики max buy / list / no-sales / stale. Команды: `/pricing_tuning_report`, `/admin_pricing_tuning_report` (все пользователи). Рекомендации **не** пишут `.env` сами.

**Admin config hints** — `/admin_pricing_config_current`, `/admin_pricing_config_suggest` (после tuning — текст «добавьте в .env …»).

**Calibration dataset** — `app/services/calibration_dataset_builder.py`, `/admin_build_calibration_dataset` → `tests/fixtures/calibration/scenarios/generated/`.

**Accuracy** — сегменты (коллекция, decision, confidence bucket, traits, hold time) встроены в `/accuracy_report` при ≥3 закрытых. `/trade_stats` расширен (open/sold, PnL, best/worst, hold).

**Accuracy tags** — миграция `0027_trade_journal_accuracy_tags`: теги и realized метрики при `/trade_sell` (и для импортированных sold).

**Backtest from journal** — `/backtest_trades`, `/admin_backtest_trades`: `journal_rows_to_backtest_pairs` + `run_backtest`.

**Важно:** бот не «самообучается» без контроля; чем больше **реальных** закрытых сделок, тем полезнее отчёты (10 мало, 50+ лучше, 100+ уже ощутимо).

### Stage 33 — Production accuracy loop, signal review queue & beta dataset workflow

**Signal snapshot** — таблица `signal_snapshots` (миграция `0028_signal_snapshots`): короткий снимок прогноза при `/check`, `/deal`, `/price_plan`, топ-3 `/scan`, топ-1 `/rare_deals`. В ответе: `Signal ID: #…` и подсказка `/signal_good|bad|unclear <id>`.

**Signal feedback с ID** — миграция `0029_feedback_signal_link`: `signal_snapshot_id`, `signal_rating`, `outcome_hint`, `reviewer_note` на `feedback_items`. Команды: `/signal_good`, `/signal_bad`, `/signal_unclear` (с ID или legacy текстом без привязки).

**Очередь ревью** — `app/services/signal_review.py`, admin: `/admin_signal_queue`, `/admin_signal <id>`, `/admin_signal_mark`, `/admin_signal_note`, `/admin_signal_outcomes`.

**Таксономия проблем** — `classify_signal_issue` (цены, stale, trait sales, liquidity, parser, и т.д.).

**Trade ↔ signal** — миграция `0030_trade_signal_link`: `trade_journal.signal_snapshot_id`. `/trade_add <signal_id> | buy_price` подтягивает прогноз из снимка.

**Signal outcome** — `/signal_outcome <id> | bought|skipped|…` пишет `signal_outcome` feedback с привязкой.

**Owner dashboard** — `/admin_signal_accuracy` (агрегаты по командам, decision, confidence, коллекциям, паттернам риска).

**Beta dataset** — `app/services/beta_dataset_workflow.py`: `/admin_dataset_status`, `/admin_export_bad_signals`, `/admin_export_good_signals`, `/admin_export_reviewed_signals` → `tests/fixtures/calibration/signals/generated/` (JSONL + CSV).

**Weekly digest** — `send_owner_accuracy_digest_job` в scheduler; `.env`: `OWNER_ACCURACY_DIGEST_ENABLED`, `OWNER_ACCURACY_DIGEST_DAY`, `OWNER_ACCURACY_DIGEST_HOUR`; ручной запуск: `/admin_accuracy_digest_now`.

**Pricing change policy** — `app/services/pricing_change_policy.py`, `/admin_pricing_change_policy` (готовность к осознанным правкам `PRICING_*`, без автозаписи в `.env`).

**Home / beta health** — `/home` напоминает оценить последний сигнал за 24ч; `/admin_beta_health` показывает размер очереди, bad rate 7d, pricing readiness.

**Beta workflow (кратко):**
1. Пользователь: `/deal` или `/check` → получает Signal ID.
2. Оценка: `/signal_good <id>` или `/signal_bad <id>`.
3. Покупка: `/trade_add <signal_id> | цена`.
4. Продажа: `/trade_sell`.
5. Owner: `/admin_signal_accuracy`, `/pricing_tuning_report` (как раньше).
6. Менять `PRICING_*` только после `/admin_pricing_change_policy` и вручную в `.env`.

**Ограничения:** нет автопокупки, нет сбора ключей/подключения кошелька, отчёты не обещают прибыль.

### Stage 34 — Capital Multiplier, Flip Ladder & Budget-Aware Deal Hunting

**Команды**

| Команда | Назначение |
|--------|------------|
| `/flip_plan <budget_ton>` | Полный план: резерв, рабочий капитал, топ сделки из universe/watchlist, buy/safe/list/quick/stop, оценка p(sale), capital efficiency, пропуски, next steps. |
| `/budget_deals <budget_ton>` | Короткая версия того же плана. |
| `/compound_plan <start> \| <goal>` | Сценарий раундов роста капитала (не гарантия срока/доходности). |
| `/sell_to_buy` | Что в портфеле продавать осмысленнее и какие replacement-кандидаты сильнее по модели (если улучшение есть). |
| `/m4_plan <budget_ton>` | Путь к цели из `/goal_set` + flip-plan на бюджет (с дисклеймером). |

**Метрики**

- **Sale probability** — эвристическая оценка 5–90% из ликвидности, confidence, risk, sales/trait sales, спреда, режима рынка, качества источника и свежести; жёсткие потолки для mock, stale manual, без sales, rare без trait sales, old, illiquid, data_poor.
- **Capital efficiency** — сжатый скоринг из ROI × p(sale) × confidence × liquidity с штрафом за risk/warnings (0–100), для сортировки кандидатов.
- **Reserve / max per deal** — из `user.reserve_percent` и `user.max_deal_percent` (fallback 20% / 25% от **заявленного** бюджета в команде).
- **Speculative cap** — доля бюджета ограничена `CAPITAL_MULTIPLIER_SPECULATIVE_MAX_PERCENT` (default 15%); при маленьком бюджете не более одной спекулятивной позиции.

**Почему бот говорит «держать кэш»**

Фильтры отсекают сделки выше max buy, с низкой ожидаемой прибылью, низкой confidence/p(sale), AVOID/NEED_MORE_DATA, высоким risk, stale без продаж; allocator уважает max per deal и спекулятивный лимит — остаток показывается как unallocated.

**Почему rare без sales рискованно**

Модель режет p(sale) и помечает спекулятивные позиции; такие входы получают меньший общий лимит.

**Почему «x2» — только сценарий**

Все формулировки про прибыль/сроки — оценки и сценарии, не обещание дохода или продажи.

**Сервисы:** `app/services/capital_multiplier.py`, `flip_ladder.py`, `sell_to_buy_planner.py`, общий сбор кандидатов `universe_opportunities.py`. **Signal snapshots** для топ-кандидатов в `/flip_plan`, `/budget_deals`, `/m4_plan` (до `CAPITAL_MULTIPLIER_SIGNAL_SNAPSHOTS_TOP_N`).

**Конфиг (.env):** `CAPITAL_MULTIPLIER_*`, `COMPOUND_PLAN_*` (см. `.env.example`).

**Миграций Stage 34 нет.**

### Stage 35 — UX polish, discoverability & Free lite flow

**Цель:** закрытая бета с понятным первым шагом, без перегруза командами; Free получает `/lite_plan`, Pro — полный `/flip_plan` и universe-scan (логика цен не менялась).

**Новые и обновлённые команды**

| Команда | Назначение |
|--------|------------|
| `/start` | Короткое описание, 3 сценария, примеры, дисклеймер, клавиатура меню. |
| `/menu`, `/home` | Меню с кнопками (проверка, план, сделки, портфель, сигналы, оплата, помощь); home — план, лимиты, банк/цель, последний signal id, открытые trades, next actions. |
| `/examples` | Быстрые сценарии (check, deal, lite/flip, deals, sell_to_buy, сигналы, оплата). |
| `/quick_start` | Пошаговый онбординг. |
| `/how_it_works` | Простое объяснение без технических деталей. |
| `/commands` | Полный список по категориям; блок Admin только для admin/owner. |
| `/lite_plan <budget_ton>` | **Free-friendly:** план только по коллекциям из watchlist (без полного universe scan), до нескольких кандидатов + teaser Pro. |
| `/admin_beta_checklist` | Admin/owner: чеклист беты (owner, invites, users, feedback, bad rate, stale payments, инциденты, digest). |

**Free vs Pro (кратко)**

- **Free:** `/check`, `/deal`, `/add`, `/lite_plan`, ручные market-команды, лимиты watchlist/universe по `feature_limits`.
- **Pro/Trader:** полный `/flip_plan`, `/budget_deals`, `/m4_plan`, `/sell_to_buy` (где требуется `capital_plan`), universe scan — как в Stage 34.

**Paywall UX:** сообщения вида «что закрыто → что сделать на Free (например `/lite_plan`) → `/upgrade` без давления».

**События аналитики:** `examples_viewed`, `how_it_works_viewed`, `quick_start_viewed`, `commands_viewed`, `lite_plan_used`, `flip_plan_used`, `budget_deals_used`, `sell_to_buy_used`, `compound_plan_used`, `m4_plan_used` (без чувствительного payload).

**Fallback:** неизвестные `/команды` — подсказка с `/check` и `/examples`; обычный текст (не похожий на gift) — короткая подсказка; `passive_gift` без изменений по смыслу.

**Что дать бета-пользователю**

1. Пришли ссылку на NFT или `/check <ссылка>`.
2. Нажми `/menu` или `/home`.
3. Попробуй `/lite_plan 300` (Free) или `/flip_plan 300` (Pro+).
4. Если сигнал полезен — `/signal_good <id>`.
5. Если нет — `/signal_bad <id>`.
6. Если купил — `/trade_add <signal_id> | цена`.
7. Если продал — `/trade_sell <trade_id> | цена`.

**Миграций Stage 35 нет.**

### Stage 36 — Beta Launch QA Gate, Deploy Readiness & Smoke Suite

**Цель:** без новой бизнес-логики цен — только проверки конфигурации, инвайтов, оплат, источников и read-only smoke перед закрытой бетой/production.

**Сервисы**

- `app/services/beta_launch_readiness.py` — отчёт GO / GO_WITH_WARNINGS / NO_GO, чеклисты, рекомендации.
- `app/services/smoke_suite.py` — лёгкие проверки (фабрика источников, таблицы, runtime state) **без** реальных HTTP к маркетплейсам.
- `app/services/beta_invite_readiness.py`, `payment_readiness.py`, `source_readiness.py` — хелперы для инвайтов, manual payments, источников.

**Команды (admin/owner, кроме где указано)**

| Команда | Назначение |
|--------|------------|
| `/beta_launch_check`, `/launch_check` | Полный текст readiness (env, DB/migrations, owner/admin, wallet, инвайты, предупреждения in-memory/Redis). |
| `/smoke_suite` | Краткий smoke-отчёт (read-only). |
| `/beta_smoke_plan` | Ручной чеклист шагов в Telegram для тестера. |
| `/beta_user_script` | Готовый текст для отправки бета-пользователю. |
| `/prod_health` | Расширен: статус launch, инвайты, owner/admin, wallet set/missing, mock, scheduler, счётчики сигналов/feedback, оплаты. |
| `/admin_beta_checklist` | Дополнено строками invites + payment readiness. |

**Условия overall (beta launch)**

- Любой **fail** (нет BOT_TOKEN/DATABASE_URL, DB/migrations, owner/admin, wallet при manual payments, production без admin ids, инвайт-gate без валидного инвайта) → **NO_GO**.
- Иначе при предупреждениях (ключи API, mock+prod, пустые сигналы/trades/feedback, in-memory лимиты) → **GO_WITH_WARNINGS**.
- Без fail и с минимумом warn → **GO**.

**Миграций Stage 36 нет.**

#### Day 0 Launch Checklist

1. Rotate secrets (bot token, DB, API keys).
2. Set `ADMIN_TELEGRAM_IDS`.
3. Owner: `/admin_set_role <telegram_id> | owner` и при необходимости `/admin_grant_plan …`.
4. Задать TON wallet (`OWNER_CRYPTO_WALLET_TON`).
5. Создать инвайт: `/admin_create_invite beta10 | pro | 14 | 10`.
6. Запустить: `/beta_launch_check`, `/smoke_suite`, `/prod_health`.
7. Пройти пользовательский flow вторым аккаунтом (см. `/beta_smoke_plan`).
8. Пригласить небольшую группу (например 5 пользователей).
9. Мониторинг: `/admin_beta_health`, `/admin_feedback_sla`, `/admin_signal_accuracy`, `/admin_payments_stale`.

#### What to send beta users

Используй текст из `/beta_user_script` (кратко: что делает бот, `/check`, `/lite_plan`, feedback по сигналам, не финсовет, без кошелька/seed).

### Security checklist before beta

1. rotate Telegram bot token
2. rotate Supabase password
3. rotate TonAPI key if exposed
4. verify `.env` is ignored
5. verify no secrets in README/logs
6. verify no seed/private keys stored
7. verify owner wallet is receive-only public address
8. verify admin ids are correct
9. verify backup/export strategy

## Production quick checklist

1. Configure `.env`:
   - `PRODUCTION_MODE=true`
   - `ENABLE_MOCK_SOURCE=false`
   - `ALLOW_MOCK_IN_PRODUCTION=false`
   - `TONAPI_ENABLED=true`
   - `TONAPI_API_KEY=...`
   - `FULL_MARKET_SCAN_ENABLED=true`
   - `NFT_GLOBAL_INDEX_ENABLED=true`
2. Apply schema: `alembic upgrade head`
3. Warm NFT index (optional but recommended):
   - `python -m app.tools.sync_all_nft_collections`
   - `python -m app.tools.sample_all_collection_aliases`
4. If you use start hero/media generation, run the project-specific generation step.
5. Run readiness smoke: `python -m app.tools.readiness_check`
6. Start bot: `python -m app.main`
