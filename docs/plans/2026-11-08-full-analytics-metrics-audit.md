# Аудит плана `2026-11-08-full-analytics-metrics.md`

Аудит не независимый: план и аудит сделаны в одной сессии. Для независимой проверки нужна свежая сессия, которой передаются план и код без этих выводов.

**Вердикт:** делать с правками. Код плана проходит тесты и ruff на копии, мутации ловятся; три подсказки для модели расходятся с документацией Google, и одно обещание (листание отчёта по видео) документацией не подтверждено.

**Правки плана**
- `docs/plans/2026-11-08-full-analytics-metrics.md`, задача 3, описание `dimensions`, строка про `insightTrafficSourceDetail`. Google требует для этого отчёта `maxResults` ≤ 25 (channel_reports: «requires you to set the maxResults parameter to an integer value of 25 or less»), подсказка об этом молчит, а схема разрешает до 200. Сценарий: модель запросит `max_results=50` → ошибка 400 вместо данных. Правка: дописать «max_results не больше 25».
- Там же, список типов для `insightTrafficSourceDetail`. Страницы Google противоречат друг другу: `analytics/dimensions` перечисляет `NOTIFICATION`, `END_SCREEN`, `VIDEO_REMIXES` как поддерживаемые, `channel_reports` называет их «unsupported». Правка: оставить в подсказке только бесспорные `YT_SEARCH`, `EXT_URL`, `RELATED_VIDEO`, `SUBSCRIBER`, `YT_CHANNEL`, `ADVERTISING`; остальное Google отклонит сам, текст ошибки дойдёт до модели.
- Там же, про `dimensions=video`. Отчёт топ-видео требует `sort` и `maxResults` ≤ 200 (channel_reports). В README пример с `sort` есть, в подсказке нет. Правка: «video (нужен sort, max_results ≤ 200)».
- Задача 3, шаг 1. Тест проверяет `"start_index" in hints`, то есть задача 3 зависит от задачи 2. Для `subagent-driven-development` порядок обязателен; добавить в заголовок задачи 3 «после задачи 2».

**Альтернатива:** не добавлять `yt-analytics-monetary.readonly` (задача 1), оставить три задачи. Убирается повторный `auth` и чувствительный scope на экране согласия. Цена: без дохода, `cpm` и `monetizedPlaybacks`, то есть «полная аналитика» не достигается для каналов в партнёрке. Слабое место: для немонетизированного канала scope бесполезен в любом случае. Рекомендация: оставить задачу 1, но выполнять её последней, чтобы при отказе от неё остальное уже работало.

**Замеры:** после `auth` (или после реализации задачи 2) проверить, что `startIndex` работает с измерением `video`:

```bash
YOUTUBE_SECRETS_DIR=~/.config/youtube-insights uv run python -c "from youtube_insights import google; from youtube_insights.constants import ANALYTICS_API; r=google.get(ANALYTICS_API, ids='channel==MINE', startDate='2025-01-01', endDate='2026-11-01', metrics='views', dimensions='video', sort='-views', maxResults=2, startIndex=3); print(r.get('rows'))"
```

Две строки с видео, отличными от первых двух → листание работает, пример «Весь архив видео» в README верен. Ошибка 400 или те же два видео → `startIndex` для этого отчёта не поддерживается: убрать пример из README, оставить `start_index` для отчётов по дням и странам.

**Входы решения**
- `src/youtube_insights/google.py:78` `get`: отбрасывает `None` — измерено `test_get_drops_none_and_sends_bearer`. Новые `startIndex=None`, `currency=None` не попадут в URL, старые вызовы не меняются.
- `src/youtube_insights/server.py:166` `tool(**params.get("arguments", {}))`: единственный вызов `analytics` в коде, аргументы приходят от модели по схеме — измерено `test_serve_speaks_newline_json`.
- `src/youtube_insights/google.py:116` `"scope": SCOPES`: единственное место, где scope уходит в Google — измерено `test_login_asks_only_readonly_and_rejects_wrong_state`.
- Доход для канала вне партнёрки: ответ Google — предположено (нет канала для замера). План в README пишет «ошибка или пустой отчёт», обе ветки покрыты.

**Подтверждено**
- Код задач 1–3, применённый на копии в scratchpad: `8 passed`, `ruff: All checks passed!`. Мутация «не передавать startIndex» → `1 failed`; мутация «убрать третий scope» → `1 failed`.
- Текст третьего разрешения на экране согласия → `developers.google.com/identity/protocols/oauth2/scopes`: «View monetary and non-monetary YouTube Analytics reports for your YouTube content». Совпадает с README из задачи 1 дословно.
- `startIndex`, `currency` (только денежные метрики, по умолчанию USD) → `analytics/reference/reports/query`.
- `month` требует первое число месяца в обеих датах; `province` только с `country==US`; `creatorContentType` ∈ {LIVE_STREAM, SHORTS, STORY, VIDEO_ON_DEMAND, UNSPECIFIED} → `analytics/dimensions`.
- `viewerPercentage` с `ageGroup` и/или `gender` («Use 1 or more ageGroup, gender») → `channel_reports`.
- Список метрик дохода и удержания из подсказки → `analytics/metrics`, все имена существуют.
- `jobs.create` — POST, нужен для показов и CTR → `reporting/v1/reference/rest/v1/jobs/create`. Вынос в отдельный план обоснован.
- Исходный план фиксирует «scope ровно два» (`docs/plans/2026-11-03-readonly-youtube-mcp.md:26`). План 2026-11-08 это меняет осознанно и не редактирует исторический документ; ADR в репозитории нет.

**Не удалось проверить**
- `startIndex` с `dimensions=video`: документация молчит, токена на машине нет (`~/.config/youtube-insights` отсутствует). Замер выше.
- Нужно ли регистрировать `yt-analytics-monetary.readonly` на экране согласия в Google Cloud. В режиме Testing незарегистрированные scope обычно работают; если Google вернёт `invalid_scope` при `auth`, scope добавляется в Consent screen → Scopes.
- Подсказка в задаче 3 проверяется тестом только по двум именам (`estimatedRevenue`, `insightTrafficSourceDetail`). Опечатка в любом другом имени тестом не ловится; цена — ошибка Google в ответе модели, не сбой сервера. Принято.
