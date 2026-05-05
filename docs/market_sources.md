# Market Sources Discovery (Stage 5)

Документ фиксирует только подтвержденные или явно неполные данные по источникам.  
Если endpoint не подтвержден, он отмечен как TODO.

## Getgems

1. **Официальный API**  
   Да, обнаружена публичная документация: `https://api.getgems.io/public-api/docs`.

2. **Подтвержденные endpoints/методы**  
   Подтверждены в Swagger-списке:
   - `GET /v1/collection/stats/{collectionAddress}`
   - `GET /v1/nfts/on-sale/{collectionAddress}`
   - `GET /v1/nft/history/{nftAddress}`
   - `GET /v1/nfts/history/gifts`
   - и другие read endpoints.

3. **Какие данные доступны (по docs-списку)**  
   - collection floor: вероятно доступен через stats/collection endpoints  
   - trait floor: отдельный явно подтвержденный endpoint не выделен (TODO mapping)
   - active listings: есть endpoints on-sale
   - recent sales: есть history endpoints
   - gift attributes: есть attributes endpoints коллекции/NFT

4. **Нужен ли API key**  
   Не для большинства read endpoints в публичной документации.  
   Специальные API (GiftApi/StorageApi/FragmentApi в рамках Getgems) могут требовать отдельный доступ.

5. **Rate limits**  
   Явные лимиты в доступной странице docs не зафиксированы (TODO).

6. **Риски**  
   - возможные изменения структуры ответа
   - часть API методов партнерские/ограниченные

7. **Что реализовано в Stage 6**  
   - безопасный адаптер с HTTP helper, retries, timeout
   - подключение через registry `collection_name -> collection_address`
   - floor/listings через `GET /v1/nfts/on-sale/{collectionAddress}`
   - recent sales: безопасная попытка через `GET /v1/collection/history/{collectionAddress}`
   - мягкая обработка ошибок и пустой результат при неподходящих данных

8. **TODO**  
   - точное маппирование `floorPrice` и related полей по schema
   - trait floor extraction strategy
   - listings/sales нормализация по проверенным полям ответа

## Tonnel

1. **Официальный API**  
   В рамках Stage 5 публичная официальная документация endpoint-ов не подтверждена.

2. **Подтвержденные endpoints/методы**  
   Не зафиксированы (TODO).

3. **Какие данные доступны**  
   Не подтверждено напрямую через официальный публичный API (TODO).

4. **Нужен ли API key**  
   Не подтверждено документированно (TODO).

5. **Rate limits**  
   Не подтверждены (TODO).

6. **Риски**  
   - высокий риск reliance на неофициальные интеграции
   - нестабильность или недоступность endpoint-ов

7. **Что реализовано в Stage 5**  
   - безопасный адаптер-каркас с HTTP helper
   - endpoint-agnostic безопасный режим: возвращает пустые данные, не ломает бота

8. **TODO**  
   - добавить только официально подтвержденные read endpoints
   - описать требуемую auth модель и лимиты

## Fragment

1. **Официальный API**  
   Подтверждена публичная страница платформы (`fragment.com/about`).  
   Стабильный публичный read API для market floor/listings/sales в рамках Stage 5 не подтвержден.

2. **Подтвержденные endpoints/методы**  
   Для задач GiftSniper (floor/sales/listings по gifts) в Stage 5 не подтверждены (TODO).

3. **Какие данные доступны**  
   - данные о платформе/коллектиблах на уровне продукта подтверждены
   - прямые read endpoints под floor/trait floor/recent sales в этом этапе не подтверждены

4. **Нужен ли API key**  
   Не подтверждено в рамках reliable public read API для нужных методов (TODO).

5. **Rate limits**  
   Не подтверждены (TODO).

6. **Риски**  
   - риск scraping-подходов (не используется)
   - отсутствие подтвержденных read endpoints под нужные метрики

7. **Что реализовано в Stage 5**  
   - безопасный адаптер-каркас с HTTP helper
   - без Selenium/обхода защит/логина
   - мягкий empty result при отсутствии настроенных endpoint-ов

8. **TODO**  
   - подключить подтвержденные endpoint-ы при наличии официальной документации
   - реализовать строгий mapper под подтвержденный формат ответа

## Итог Stage 5

- Реализован безопасный foundation для real sources:
  - config flags + base URLs + optional keys
  - единый HTTP helper
  - normalization layer
  - source factory + aggregator fallback to mock
- Бот продолжает работать даже если real sources не готовы.
- При слабых/mock данных quality layer снижает confidence и показывает warnings.

## Stage 6 additions

- Добавлен collection registry:
  - `data/collections.example.json` (коммитится)
  - `data/collections.json` (локальный, не коммитится)
- Добавлен слой `app/sources/collections.py` для resolve aliases и source identifiers.
- Добавлен mapper слой `app/sources/mappers/getgems.py`.
- Без `getgems.collection_address` адаптер возвращает safe empty result и предупреждение в quality.

## Stage 7 additions

- Добавлен безопасный capture-скрипт:
  - `scripts/capture_getgems_payload.py --collection "Ice Cream"`
  - сохраняет sanitized payload в `tests/fixtures/getgems/real/`
- Добавлен registry-check скрипт:
  - `scripts/check_collection_registry.py`
- Усилен mapper Getgems:
  - калибровка по нескольким payload shapes
  - `parse_ton_price()` с поддержкой TON / nanoTON / dict-форматов
  - unknown shape не ломает парсер
- Analyzer получил confidence caps при слабых данных (mock/без sales).

## Stage 8 live calibration note

- Для Ice Cream в локальном `data/collections.json` можно использовать публичный пример address:
  `EQBUvskEvmWdp_V6HX-2Tyfp4mFSzMzdg9TaUz6zKVz6Ov3f`.
- Проверка:
  - `python scripts/check_collection_registry.py`
  - `python scripts/capture_getgems_payload.py --collection "Ice Cream"`
- Без Getgems API key публичные v1 market endpoints возвращают 401, поэтому capture может не получить payload.

## TonAPI (read-only source)

TonAPI подключен как вспомогательный on-chain источник:
- NFT metadata
- collection info
- owner/address
- account/NFT history (best-effort)

Ограничения:
- не используется как marketplace floor/listings source
- не рассчитывает trait floor/floor market напрямую
- не повышает confidence по цене без market data
