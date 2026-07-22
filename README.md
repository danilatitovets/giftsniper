# GiftSniper

Telegram bot for analytics and discovery of Telegram Gifts and TON NFTs — without wallet custody, signing, or auto-buying.

**Repository:** [github.com/danilatitovets/giftsniper](https://github.com/danilatitovets/giftsniper)

---

## Purpose

GiftSniper helps users inspect gift/NFT links and identifiers, track watchlists, estimate flip scenarios from market data, and receive alerts. The bot is analytics-oriented: it does not custody funds or execute trades.

---

## Main features

- Universal gift/NFT input parsing (links, addresses, collection + number)
- `/check`, `/add`, `/deal`, `/import_gifts`, watchlist and repair flows
- Market data integrations (TonAPI and marketplace source adapters)
- Confidence / freshness messaging for pricing scenarios
- Passive mode for shared links with inline actions
- Scheduler for alert rules with cooldown anti-spam
- Admin repair utilities
- Docker + Alembic migrations for deployment

---

## Architecture

- **Runtime:** Python async Telegram bot (`aiogram`)
- **Data:** PostgreSQL via SQLAlchemy + asyncpg
- **Migrations:** Alembic
- **Jobs:** APScheduler
- **HTTP:** httpx clients for market/NFT providers
- **Config:** pydantic-settings from environment

```
Telegram updates → aiogram handlers → analysis / market services → PostgreSQL
                                      └─ scheduler alerts
```

---

## Stack

| Area | Technologies |
| --- | --- |
| Bot | Python, aiogram 3 |
| DB | SQLAlchemy, asyncpg, Alembic, PostgreSQL |
| Jobs | APScheduler |
| Quality | pytest, pytest-asyncio |
| Deploy | Docker / docker-compose |

---

## Security & data

- Does **not** ask for seed phrases
- Does **not** store private keys
- Does **not** connect wallets or sign transactions
- Does **not** perform auto-purchases
- Secrets only in `.env` / runtime environment
- ROI and profit figures are scenario estimates — not guaranteed returns

---

## Local setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# set BOT_TOKEN and DATABASE_URL
alembic upgrade head
python -m app.main
```

### Docker

```bash
cp .env.example .env
docker compose up --build
```

### Environment variables (selected names from `.env.example`)

`BOT_TOKEN`, `DATABASE_URL`, `CHECK_INTERVAL_MINUTES`, `ALERT_COOLDOWN_MINUTES`, `DEFAULT_MARKETPLACE_FEE_PERCENT`, `ESTIMATED_EXTRA_COSTS_TON`, `MIN_PROFIT_TON`, `ENABLE_MOCK_SOURCE`, `GETGEMS_ENABLED`, `TONAPI_ENABLED`, `TONNEL_ENABLED`, `FRAGMENT_ENABLED`, `TONAPI_API_KEY`, `GETGEMS_API_KEY`, marketplace base URLs, pricing/confidence thresholds, full-market scan flags.

Do not commit real API keys or bot tokens.

---

## Scripts / commands

| Command | Description |
| --- | --- |
| `python -m app.main` | Run the bot |
| `alembic upgrade head` | Apply DB migrations |
| `pytest` | Test suite |
| `docker compose up --build` | Containerized run |

Additional utility scripts live under `scripts/` (registry checks, admin helpers).

---

## Status

**Actively developed Telegram product** with a large feature surface and market-data integrations. Capabilities depend on configured providers, API keys, and plan limits (e.g. TonAPI rate limits).
