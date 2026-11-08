# Полный набор метрик YouTube Analytics: план реализации

> **Для агентов:** выполнять через `subagent-driven-development` (рекомендуется) или `executing-plans`, задача за задачей. Шаги помечены чекбоксами.

**Цель:** инструмент `analytics` отдаёт модели всё, что умеет YouTube Analytics API для своего канала, включая доход, и позволяет листать длинные отчёты.

**Архитектура:** код не меняет форму. Три правки: третий read-only scope (деньги), два новых параметра запроса (`start_index`, `currency`), расширенные описания метрик и измерений в схеме инструмента. Документация приводится в соответствие с фактами API.

**Стек:** Python ≥ 3.15, uv, stdlib. Dev: pytest, ruff. Без новых зависимостей.

**Спецификация:** раздел «Что не так сейчас» ниже; отдельного spec-файла нет. Исходный план проекта: `docs/plans/2026-11-03-readonly-youtube-mcp.md`.

## Глобальные ограничения

- Scope только с суффиксом `.readonly`: `youtube.readonly`, `yt-analytics.readonly`, `yt-analytics-monetary.readonly`.
- Только HTTP GET к `googleapis.com`; единственный POST — обмен кода/refresh на `oauth2.googleapis.com/token`.
- `dependencies = []`.
- Обязательный ENV `YOUTUBE_SECRETS_DIR` без дефолта.
- Код и комментарии короткие, по-русски. Каждой изменённой функции докстринг.
- Коммиты: сессия в собственном worktree коммитит каждую задачу в свою ветку. В основной папке только по просьбе.
- Проверка перед «готово»: `uv run pytest -q` и `uv run ruff check .`.

## Что не так сейчас

Проверено по `src/youtube_insights/server.py`, `constants.py` и документации Google (`analytics/metrics`, `analytics/dimensions`, `reference/reports/query`, `reporting/v1/reports/channel_reports`) 2026-11-08.

| Пробел | Где | Факт |
| --- | --- | --- |
| Доход не запросить | `constants.py:6` `SCOPES` | `estimatedRevenue`, `estimatedAdRevenue`, `estimatedRedPartnerRevenue`, `grossRevenue`, `cpm`, `playbackBasedCpm`, `adImpressions`, `monetizedPlaybacks` требуют `yt-analytics-monetary.readonly`. Scope только на чтение. |
| Нет пагинации | `server.py:58-77` `analytics` | Query API принимает `startIndex` (с 1) и `maxResults`. Параметра нет, отчёт по видео обрывается на `max_results`. |
| Нет валюты | там же | `currency` (ISO 4217, по умолчанию USD) влияет только на денежные метрики. |
| Модель видит 12 метрик и 10 измерений | `server.py:122-139` | API отдаёт ~45 метрик и ~30 измерений. Модель запрашивает только то, что видит в описании. Не названы: `insightTrafficSourceDetail` (поисковые запросы, внешние сайты), `subscribedStatus`, `insightPlaybackLocationType`, `liveOrOnDemand`, `sharingService`, `operatingSystem`, `playlist`, `relativeRetentionPerformance`, `startedWatching`/`stoppedWatching`, `averageConcurrentViewers`/`peakConcurrentViewers`, `videosAddedToPlaylists`, `card*`, `dislikes`, `redViews`, весь доход. |
| Неточная подсказка | `server.py:126` | `viewerPercentage` работает с `ageGroup` и/или `gender`, не только с парой. |
| Нет данных эфира | `constants.py:15` `VIDEO_PARTS` | `liveStreamingDetails` (начало, конец, пик зрителей) не запрашивается. |
| README ошибается про показы и CTR | `README.md`, раздел «Ограничения» | Метрик нет в Analytics API, но они есть в Reporting API: отчёты `channel_reach_basic_a1` и `channel_reach_combined_a1`, поля `video_thumbnail_impressions`, `video_thumbnail_impressions_ctr`. Scope `yt-analytics.readonly` хватает. |

### Что сознательно не делаем в этом плане

| Что | Почему |
| --- | --- |
| Показы и CTR через Reporting API | Требует `POST jobs.create` (нарушает правило «только GET»), первый отчёт через ~48 часов, данные приходят CSV-файлами раз в сутки, хранятся 60 дней. Это отдельная подсистема: задание, список отчётов, скачивание, разбор CSV. Отдельный план после решения о POST-исключении. В этом плане только исправляем формулировку README. |
| Комментарии, субтитры | Требуют write-scope, не изменилось. |
| Группировка метрик в отдельные инструменты | Один `analytics` покрывает всё, Google сам отклоняет недопустимые сочетания. |

## Структура файлов

```
src/youtube_insights/constants.py   # SCOPES, VIDEO_PARTS           — задачи 1, 3
src/youtube_insights/server.py      # analytics(), схема TOOLS       — задачи 2, 3
tests/test_server.py                # 3 новых/изменённых теста       — задачи 1, 2, 3
README.md                           # scope, примеры, ограничения    — задачи 1, 4
```

---

### Задача 1: третий scope для дохода

**Файлы:**
- Изменить: `src/youtube_insights/constants.py:6-9`
- Изменить: `tests/test_server.py:127-130` (`test_login_asks_only_readonly_and_rejects_wrong_state`)
- Изменить: `README.md:3`, `README.md:34-39`

**Интерфейсы:**
- Производит: `SCOPES: str` с тремя URL через пробел. Используется `google.login()` без изменений.

- [ ] **Шаг 1: обновить тест на scope**

В `tests/test_server.py` заменить ожидаемый список:

```python
    assert opened["scope"][0].split() == [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
        "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
    ]
```

- [ ] **Шаг 2: убедиться, что тест падает**

```bash
uv run pytest tests/test_server.py::test_login_asks_only_readonly_and_rejects_wrong_state -q
```

Ожидание: FAIL, в diff списков не хватает `yt-analytics-monetary.readonly`.

- [ ] **Шаг 3: добавить scope**

`src/youtube_insights/constants.py`:

```python
SCOPES = (
    "https://www.googleapis.com/auth/youtube.readonly "
    "https://www.googleapis.com/auth/yt-analytics.readonly "
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly"
)
```

- [ ] **Шаг 4: убедиться, что тест проходит**

```bash
uv run pytest tests/test_server.py::test_login_asks_only_readonly_and_rejects_wrong_state -q
```

Ожидание: PASS.

- [ ] **Шаг 5: README**

Строка 3: заменить «два read-only scope» на «три read-only scope».

Раздел «Вход», список разрешений:

```markdown
На экране Google должны быть только три разрешения:

- View your YouTube account
- View YouTube Analytics reports for your YouTube content
- View monetary and non-monetary YouTube Analytics reports for your YouTube content

Если видите «edit», «delete» или «manage», остановитесь и не подтверждайте.
Если вход уже выполнялся, повторите `auth`: старый токен выдан на два разрешения, и Google откажет в денежных метриках.
```

Точную формулировку третьего пункта сверить с экраном согласия при ручном прогоне (задача 4, шаг 3) и исправить в README, если Google показывает другой текст.

- [ ] **Шаг 6: коммит**

```bash
git add src/youtube_insights/constants.py tests/test_server.py README.md
git commit -m "feat: scope yt-analytics-monetary.readonly для метрик дохода"
```

---

### Задача 2: пагинация и валюта в `analytics`

**Файлы:**
- Изменить: `src/youtube_insights/server.py:58-77` (функция `analytics`)
- Изменить: `src/youtube_insights/server.py:140-146` (схема `analytics` в `TOOLS`)
- Изменить: `tests/test_server.py:52-56` (`test_analytics_rows_as_dicts`)

**Интерфейсы:**
- Производит: `analytics(start_date, end_date, metrics, dimensions=None, filters=None, sort=None, max_results=None, start_index=None, currency=None) -> list[dict]`. В Google уходят `startIndex` и `currency`; `None` отбрасывает `google.get`.

- [ ] **Шаг 1: расширить тест**

Заменить `test_analytics_rows_as_dicts`:

```python
def test_analytics_rows_as_dicts_and_passes_paging(monkeypatch):
    report = {"columnHeaders": [{"name": "day"}, {"name": "views"}], "rows": [["2026-11-01", 5]]}
    sent = {}
    monkeypatch.setattr(google, "get", lambda url, **params: sent.update(params) or report)
    rows = server.analytics(
        "2026-11-01", "2026-11-02", "views", dimensions="day", start_index=201, currency="EUR"
    )
    assert rows == [{"day": "2026-11-01", "views": 5}]
    assert (sent["startIndex"], sent["currency"]) == (201, "EUR")
```

- [ ] **Шаг 2: убедиться, что тест падает**

```bash
uv run pytest tests/test_server.py::test_analytics_rows_as_dicts_and_passes_paging -q
```

Ожидание: FAIL, `TypeError: analytics() got an unexpected keyword argument 'start_index'`.

- [ ] **Шаг 3: добавить параметры**

`src/youtube_insights/server.py`, функция `analytics`:

```python
def analytics(
    start_date: str,
    end_date: str,
    metrics: str,
    dimensions: str | None = None,
    filters: str | None = None,
    sort: str | None = None,
    max_results: int | None = None,
    start_index: int | None = None,
    currency: str | None = None,
) -> list[dict]:
    """Отчёт YouTube Analytics по своему каналу; строки возвращаются как словари.

    start_index листает длинные отчёты (с 1), currency влияет только на денежные метрики.
    """
    report = google.get(
        ANALYTICS_API,
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        metrics=metrics,
        dimensions=dimensions,
        filters=filters,
        sort=sort,
        maxResults=max_results,
        startIndex=start_index,
        currency=currency,
    )
    names = [column["name"] for column in report["columnHeaders"]]
    return [dict(zip(names, row, strict=True)) for row in report.get("rows", [])]
```

В схеме `TOOLS` после `"max_results"`:

```python
                "max_results": {"type": "integer", "minimum": 1, "maximum": 200},
                "start_index": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Номер первой строки (с 1), для листания вместе с max_results",
                },
                "currency": {
                    "type": "string",
                    "description": (
                        "ISO 4217, например EUR; только для денежных метрик, по умолчанию USD"
                    ),
                },
```

- [ ] **Шаг 4: убедиться, что тесты проходят**

```bash
uv run pytest -q && uv run ruff check .
```

Ожидание: `8 passed`, ruff без замечаний.

- [ ] **Шаг 5: коммит**

```bash
git add src/youtube_insights/server.py tests/test_server.py
git commit -m "feat: start_index и currency в analytics"
```

---

### Задача 3: полные подсказки по метрикам и измерениям, данные эфира

Выполнять строго после задачи 2: тест этой задачи проверяет наличие `start_index` в схеме.

**Файлы:**
- Изменить: `src/youtube_insights/server.py:119-139` (описания `metrics` и `dimensions`)
- Изменить: `src/youtube_insights/constants.py:15` (`VIDEO_PARTS`)
- Изменить: `tests/test_server.py:58-85` (`test_serve_speaks_newline_json`)

**Интерфейсы:**
- Производит: строки описаний в `tools/list`. Никаких изменений сигнатур.

- [ ] **Шаг 1: добавить проверку в тест stdio**

В `test_serve_speaks_newline_json` после строки `assert names == {...}`:

```python
    analytics_schema = next(t for t in replies[1]["result"]["tools"] if t["name"] == "analytics")
    hints = analytics_schema["inputSchema"]["properties"]
    assert "estimatedRevenue" in hints["metrics"]["description"]
    assert "insightTrafficSourceDetail" in hints["dimensions"]["description"]
    assert "start_index" in hints
```

- [ ] **Шаг 2: убедиться, что тест падает**

```bash
uv run pytest tests/test_server.py::test_serve_speaks_newline_json -q
```

Ожидание: FAIL на `"estimatedRevenue" in ...`.

- [ ] **Шаг 3: переписать описания**

`src/youtube_insights/server.py`, в схеме `analytics` заменить `"metrics"` и `"dimensions"`:

```python
                "metrics": {
                    "type": "string",
                    "description": (
                        "Через запятую. Просмотры: views, engagedViews, redViews, "
                        "estimatedMinutesWatched, averageViewDuration, averageViewPercentage. "
                        "Вовлечённость: likes, dislikes, comments, shares, subscribersGained, "
                        "subscribersLost, videosAddedToPlaylists, videosRemovedFromPlaylists. "
                        "Доход (нужен scope monetary, канал в партнёрке): estimatedRevenue, "
                        "estimatedAdRevenue, estimatedRedPartnerRevenue, grossRevenue, cpm, "
                        "playbackBasedCpm, adImpressions, monetizedPlaybacks. "
                        "Подсказки: cardImpressions, cardClicks, cardClickRate, "
                        "cardTeaserImpressions, cardTeaserClicks, cardTeaserClickRate. "
                        "Эфиры: averageConcurrentViewers, peakConcurrentViewers. "
                        "Плейлисты (с dimensions=playlist или filters=playlist==ID): "
                        "playlistStarts, playlistViews, viewsPerPlaylistStart, "
                        "averageTimeInPlaylist, playlistSaves. "
                        "Удержание (только с dimensions=elapsedVideoTimeRatio и "
                        "filters=video==ID): "
                        "audienceWatchRatio, relativeRetentionPerformance, startedWatching, "
                        "stoppedWatching. Демография: viewerPercentage (с dimensions ageGroup "
                        "и/или gender). Показов обложек и CTR в этом API нет."
                    ),
                },
                "dimensions": {
                    "type": "string",
                    "description": (
                        "Через запятую. Время: day, month (даты строго первое число месяца). "
                        "Контент: video (нужен sort, max_results не больше 200), playlist, "
                        "creatorContentType (VIDEO_ON_DEMAND, SHORTS, LIVE_STREAM, STORY), "
                        "liveOrOnDemand, youtubeProduct. "
                        "Аудитория: subscribedStatus, ageGroup, gender, country, province (только "
                        "с filters=country==US), city. "
                        "Трафик: insightTrafficSourceType; insightTrafficSourceDetail (поисковые "
                        "запросы, внешние сайты, видео-источники) только с "
                        "filters=insightTrafficSourceType==YT_SEARCH|EXT_URL|RELATED_VIDEO|"
                        "SUBSCRIBER|YT_CHANNEL|ADVERTISING и max_results не больше 25. "
                        "Где смотрят: insightPlaybackLocationType, insightPlaybackLocationDetail "
                        "(только с filters=insightPlaybackLocationType==EMBEDDED). "
                        "Устройства: deviceType, operatingSystem. Шеринг: sharingService. "
                        "Удержание: elapsedVideoTimeRatio (100 точек, требует filters=video==ID). "
                        "Эфир по минутам: livestreamPosition. Реклама: adType."
                    ),
                },
```

`src/youtube_insights/constants.py`:

```python
VIDEO_PARTS = "snippet,statistics,contentDetails,status,liveStreamingDetails"
```

Тест на константу не нужен: одна строка, Google вернёт поле `liveStreamingDetails` только для эфиров, для обычных видео его просто не будет.

- [ ] **Шаг 4: убедиться, что тесты проходят**

```bash
uv run pytest -q && uv run ruff check .
```

Ожидание: `8 passed`, ruff без замечаний (строки описаний ≤ 100 символов).

- [ ] **Шаг 5: коммит**

```bash
git add src/youtube_insights/server.py src/youtube_insights/constants.py tests/test_server.py
git commit -m "feat: полные подсказки метрик и измерений, liveStreamingDetails"
```

---

### Задача 4: README — примеры, ограничения, ручная проверка

**Файлы:**
- Изменить: `README.md`, разделы «Примеры запросов к `analytics`» и «Ограничения»

**Интерфейсы:** нет.

- [ ] **Шаг 1: дополнить таблицу примеров**

Добавить строки после «Демография»:

```markdown
| Доход по дням | `metrics=estimatedRevenue,monetizedPlaybacks,playbackBasedCpm`, `dimensions=day`, `currency=EUR` |
| Поисковые запросы | `metrics=views`, `dimensions=insightTrafficSourceDetail`, `filters=insightTrafficSourceType==YT_SEARCH`, `sort=-views`, `max_results=25` |
| Подписчики против остальных | `metrics=views,averageViewPercentage`, `dimensions=subscribedStatus` |
| Весь архив видео | `metrics=views`, `dimensions=video`, `sort=-views`, `max_results=200`, затем `start_index=201` |
```

- [ ] **Шаг 2: переписать раздел «Ограничения»**

```markdown
## Ограничения

- **Показы и CTR обложек.** В YouTube Analytics API их нет. Они есть в YouTube Reporting API (отчёты `channel_reach_basic_a1`, `channel_reach_combined_a1`), но тот требует один POST для создания задания и отдаёт CSV раз в сутки. Сюда не включены, цифры пока из Studio.
- **Доход.** Данные приходят только каналам в партнёрской программе; остальным Google вернёт ошибку или пустой отчёт. Нужен scope `yt-analytics-monetary.readonly` (только чтение) и повторный `auth` после обновления.
- **Субтитры.** `captions.list` требует `youtube.force-ssl`, а этот scope даёт право на изменение и удаление, поэтому субтитры не включены.
- **Комментарии.** Не включены. Документация методов не указывает нужный scope, работа с `youtube.readonly` не проверялась.
- **Режим Testing.** Пока проект Google в этом режиме, вход приходится повторять раз в 7 дней. Перевод в Production снимает ограничение, Google покажет предупреждение о непроверенном приложении.
```

- [ ] **Шаг 3: ручной прогон (делает владелец канала, не агент)**

1. `YOUTUBE_SECRETS_DIR=~/.config/youtube-insights uv run youtube-insights auth` — на экране согласия три разрешения, все «view». Сверить текст третьего с README, поправить при расхождении.
2. Перезапустить Claude Desktop. Вызвать `analytics` с `metrics=estimatedRevenue`, `dimensions=day` за последние 28 дней. Ожидание: строки с числами (канал в партнёрке) или ошибка Google с понятным текстом (нет партнёрки). Ошибка `insufficientPermissions` означает старый токен — повторить п. 1.
3. Вызвать `analytics` с `dimensions=insightTrafficSourceDetail`, `filters=insightTrafficSourceType==YT_SEARCH`. Ожидание: список поисковых запросов.
4. Вызвать `analytics` с `dimensions=video`, `max_results=2`, затем то же с `start_index=3`. Ожидание: разные видео.

- [ ] **Шаг 4: коммит**

```bash
git add README.md
git commit -m "docs: примеры дохода и трафика, уточнение про показы и CTR"
```

---

## Самопроверка плана

**Покрытие пробелов:** доход → задача 1; пагинация и валюта → задача 2; подсказки, `viewerPercentage`, `liveStreamingDetails` → задача 3; README про показы/CTR → задача 4. Reporting API вынесен явно.

**Вызовы изменённых функций:** `analytics` вызывается только из `tools/call` через `tool(**arguments)` (`server.py:166`) и из теста. Новые параметры необязательные, старые вызовы без них проходят, `google.get` отбрасывает `None` (проверено `test_get_drops_none_and_sends_bearer`).

**Все упоминания старого поведения:** «два read-only scope» (`README.md:3`), «два разрешения» (`README.md:34`) — задача 1. Докстринги `server.py:1`, `google.py:1` говорят «read-only»/«только чтение» без числа scope — остаются. `docs/plans/2026-11-03-*.md` фиксирует «scope ровно два» — исторический план, не редактируем.

**Путь доставки:** Claude Desktop запускает `uv run --directory <repo> youtube-insights` из рабочей копии; после правок нужен перезапуск Claude Desktop, новый токен — после `auth`. Оба шага в задаче 4.

**Подтверждения из документации:** `currency` влияет только на денежные метрики — `reference/reports/query`; `insightTrafficSourceDetail` ограничен списком типов и `maxResults` ≤ 25, отчёт по `video` требует `sort` и `maxResults` ≤ 200 — `channel_reports`; `province` только с `country==US` — `analytics/dimensions`; `jobs.create` это POST — `reporting/v1/reference/rest/v1/jobs/create`.

**Аудит:** `docs/plans/2026-11-08-full-analytics-metrics-audit.md`. Открытый замер: работает ли `startIndex` с `dimensions=video`; если нет, строку «Весь архив видео» из README (задача 4) убрать.

**Известные дефекты на затронутом пути:** `max_results` в схеме ограничен 200, у Google документированного максимума нет. Оставлено: с `start_index` это теперь не блокер.

**Коммиты:** по одному на задачу, файлы названы.
