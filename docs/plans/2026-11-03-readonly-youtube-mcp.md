# Read-only MCP для аналитики YouTube: план реализации

> **Для агентов:** выполнять через `executing-plans` или `subagent-driven-development`, задача за задачей. Шаги помечены чекбоксами.

**Цель:** локальный MCP-сервер, который читает статистику своего YouTube-канала через официальные API и физически не может ничего изменить.

**Архитектура:** два модуля на stdlib (OAuth PKCE + GET к Google; stdio JSON-RPC + 4 инструмента). Никаких зависимостей, никаких схем «на вырост». Готовые запросы для отчётов живут в навыке `youtube-analitika` (промпт), не в коде.

**Стек:** Python ≥ 3.12, uv, stdlib (`urllib`, `http.server`, `json`). Dev: pytest, ruff.

**Исходник идеи:** `~/Downloads/MCP_для_аналитики_YouTube_ресерч_и_рекомендация.md` (ресерч hygef-v4/youtube-studio-mcp).

## Почему переписать, а не урезать hygef-v4

Апстрим: 1996 строк Python, 32 инструмента, 7 файлов схем, слой `http.py`, класс-клиент на 751 строку. После удаления записи осталось бы ~900 строк и три слоя ради 4 GET-запросов. Плюс найденные дефекты:

- `server.py:224-245` фреймит сообщения заголовком `Content-Length`. Спецификация MCP stdio: «Messages are delimited by newlines». Клиенты Claude такой сервер не поймут.
- Scope `youtube`, `youtube.force-ssl`, `youtube.upload` — полный доступ к каналу.
- `youtube_bulk_get_transcripts` пишет файлы на диск по пути из аргумента инструмента.
- Токен сохраняется с правами по умолчанию (0644).

Переписать с нуля ≈ 200 строк, из них ~60 — описания инструментов.

## Глобальные ограничения

- Scope ровно два: `https://www.googleapis.com/auth/youtube.readonly` и `https://www.googleapis.com/auth/yt-analytics.readonly`.
- Только HTTP GET к `googleapis.com`; единственный POST — обмен кода/refresh на `oauth2.googleapis.com/token`.
- `dependencies = []`. Никаких `mcp`, `httpx`, `google-auth`.
- Обязательный ENV `YOUTUBE_SECRETS_DIR` без дефолта; в нём `client_secret.json` и `token.json` (0600).
- Сервер не пишет на диск ничего, кроме `token.json`.
- Код и комментарии короткие, по-русски. Имена: `channel`, `videos`, `video`, `analytics`.
- Коммиты только по явной просьбе (см. `rules/no-commit-without-approval.md`).

## Что сознательно не делаем

| Инструмент апстрима | Почему нет |
| --- | --- |
| Комментарии (list) | Методы comments в Data API требуют `youtube.force-ssl`; для аналитики не нужны |
| Субтитры, транскрипты | `captions.list/download` требуют `youtube.force-ssl` (проверено по докам) |
| Поиск по YouTube | Не про свой канал; добавить одной функцией, если понадобится |
| Плейлисты | YAGNI |
| 5 отдельных analytics-инструментов | Один `analytics(metrics, dimensions, filters, …)` покрывает все пять и ещё удержание по `elapsedVideoTimeRatio` и срез Shorts по `creatorContentType==SHORTS` |
| `youtube_auth_status`, `youtube_start_auth` | Авторизация — CLI-команда `auth`, не инструмент модели |

**Ограничение API, фиксируем сразу:** YouTube Analytics API не отдаёт показы обложек и CTR (есть только `cardImpressions`, `annotation*`). Эти цифры по-прежнему из Studio вручную.

## Структура файлов

```
pyproject.toml
README.md
src/youtube_insights/__init__.py   # пустой
src/youtube_insights/google.py     # OAuth PKCE, токен, GET      ~90 строк
src/youtube_insights/server.py     # инструменты + stdio-цикл    ~110 строк
tests/test_server.py               # 4 теста                     ~60 строк
```

---

### Задача 1: каркас проекта

**Файлы:** создать `pyproject.toml`, `.gitignore`, `src/youtube_insights/__init__.py`.

- [ ] **Шаг 1: pyproject.toml**

```toml
[project]
name = "youtube-insights"
version = "0.1.0"
description = "Read-only MCP-сервер для аналитики своего YouTube-канала"
requires-python = ">=3.12"
dependencies = []

[project.scripts]
youtube-insights = "youtube_insights.server:main"

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.8"]

[build-system]
requires = ["uv_build>=0.8,<0.14"]
build-backend = "uv_build"

[tool.ruff]
line-length = 100
```

- [ ] **Шаг 2: .gitignore**

```
.venv/
__pycache__/
*.json
!client_secret.example.json
```

Секреты в репозитории не лежат вообще (они в `YOUTUBE_SECRETS_DIR`), `*.json` — страховка.

- [ ] **Шаг 3: пустой `src/youtube_insights/__init__.py`, затем `uv sync`**

Ожидается: `.venv` создан, `uv run python -c "import youtube_insights"` молчит.

---

### Задача 2: `google.py` — OAuth PKCE и GET

**Файлы:** создать `src/youtube_insights/google.py`, `tests/test_server.py`.

**Интерфейс для задачи 3:** `google.get(url: str, **params) -> dict`, `google.login() -> None`, `google.client() -> dict`.

- [ ] **Шаг 1: падающие тесты**

```python
"""Тесты youtube_insights: токен, GET, инструменты, stdio-цикл."""

import io
import json
import sys

import pytest

from youtube_insights import google, server


@pytest.fixture
def secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUTUBE_SECRETS_DIR", str(tmp_path))
    client = {"installed": {"client_id": "id", "client_secret": "s"}}
    (tmp_path / "client_secret.json").write_text(json.dumps(client))
    return tmp_path


def test_refresh_when_expired(secrets, monkeypatch):
    google.save_token({"access_token": "old", "refresh_token": "r", "expires_in": 0})
    forms = []
    monkeypatch.setattr(
        google, "post", lambda url, form: forms.append(form) or {"access_token": "new", "expires_in": 3600}
    )
    assert google.access_token() == "new"
    assert forms[0]["grant_type"] == "refresh_token"
    saved = json.loads((secrets / "token.json").read_text())
    assert (saved["access_token"], saved["refresh_token"]) == ("new", "r")
    assert oct((secrets / "token.json").stat().st_mode)[-3:] == "600"


def test_get_drops_none_and_sends_bearer(monkeypatch):
    seen = {}
    monkeypatch.setattr(google, "access_token", lambda: "tok")
    monkeypatch.setattr(
        google, "call", lambda req: seen.update(url=req.full_url, auth=req.get_header("Authorization")) or {}
    )
    google.get("https://x/y", a=1, b=None)
    assert seen == {"url": "https://x/y?a=1", "auth": "Bearer tok"}
```

- [ ] **Шаг 2: убедиться, что падают**

Запуск: `uv run pytest -q`
Ожидается: `ImportError` на `from youtube_insights import google, server`.

- [ ] **Шаг 3: реализация `google.py`**

```python
"""OAuth 2.0 (PKCE) и GET-запросы к Google API. Только чтение."""

import base64
import hashlib
import json
import os
import secrets
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = (
    "https://www.googleapis.com/auth/youtube.readonly "
    "https://www.googleapis.com/auth/yt-analytics.readonly"
)


def secrets_dir() -> Path:
    return Path(os.environ["YOUTUBE_SECRETS_DIR"])


def client() -> dict:
    """client_secret.json из Google Cloud (OAuth-клиент типа Desktop)."""
    return json.loads((secrets_dir() / "client_secret.json").read_text())["installed"]


def call(request: Request) -> dict:
    try:
        with urlopen(request, timeout=60) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Google API {error.code}: {error.read().decode()}") from None


def post(url: str, form: dict) -> dict:
    return call(Request(url, data=urlencode(form).encode(), method="POST"))


def save_token(token: dict) -> None:
    path = secrets_dir() / "token.json"
    token["expires_at"] = time.time() + token["expires_in"]
    path.write_text(json.dumps(token))
    path.chmod(0o600)


def access_token() -> str:
    path = secrets_dir() / "token.json"
    if not path.exists():
        raise RuntimeError("Нет token.json. Выполни: uv run youtube-insights auth")
    token = json.loads(path.read_text())
    if token["expires_at"] < time.time() + 60:
        secret = client()
        token |= post(TOKEN_URL, {
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
            "client_id": secret["client_id"],
            "client_secret": secret["client_secret"],
        })
        save_token(token)
    return token["access_token"]


def get(url: str, **params: object) -> dict:
    """GET с bearer-токеном; параметры со значением None отбрасываются."""
    query = urlencode({key: value for key, value in params.items() if value is not None})
    return call(Request(f"{url}?{query}", headers={"Authorization": f"Bearer {access_token()}"}))


def login() -> None:
    """Открывает браузер, ловит redirect на loopback, сохраняет token.json."""
    secret = client()
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.server.query = parse_qs(urlparse(self.path).query)
            self.send_response(200)
            self.end_headers()
            self.wfile.write("Готово, вкладку можно закрыть.".encode())

        def log_message(self, *args: object) -> None:
            pass

    with HTTPServer(("127.0.0.1", 0), Callback) as server:
        redirect = f"http://127.0.0.1:{server.server_port}"
        url = AUTH_URL + "?" + urlencode({
            "client_id": secret["client_id"],
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        print(f"Если браузер не открылся, открой вручную:\n{url}", file=sys.stderr)
        webbrowser.open(url)
        server.timeout = 300
        server.query = {}
        server.handle_request()

    query = server.query
    if query.get("state") != [state] or "code" not in query:
        raise SystemExit(f"OAuth не удался: {query.get('error', ['нет ответа от Google'])[0]}")
    save_token(post(TOKEN_URL, {
        "code": query["code"][0],
        "client_id": secret["client_id"],
        "client_secret": secret["client_secret"],
        "redirect_uri": redirect,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }))
    print(f"Токен сохранён: {secrets_dir() / 'token.json'}", file=sys.stderr)
```

Заметки для исполнителя:
- Порт `0` — ОС выбирает свободный; Google разрешает любой loopback-порт для Desktop-клиентов, поэтому `redirect_uri` строится после `bind`.
- `handle_request()` обрабатывает ровно один запрос и блокирует до него или до `timeout`; потоки и опрос не нужны.
- `client_secret` для Desktop-клиента Google считает не секретом (так в их документации), но файл всё равно держим в `YOUTUBE_SECRETS_DIR`.
- `token |= post(...)` сохраняет `refresh_token`, которого в ответе refresh нет.

- [ ] **Шаг 4: тесты зелёные (пока только два — `server` ещё не существует, поэтому временно создать пустой `server.py`)**

Запуск: `uv run pytest -q`
Ожидается: `2 passed`.

---

### Задача 3: `server.py` — инструменты

**Файлы:** создать `src/youtube_insights/server.py` (верхняя половина), дополнить `tests/test_server.py`.

**Интерфейс для задачи 4:** `TOOLS: list[tuple[Callable, dict]]` — пары (функция, JSON-schema аргументов); имя инструмента = `f.__name__`, описание = `f.__doc__`.

- [ ] **Шаг 1: падающий тест**

```python
def test_analytics_rows_as_dicts(monkeypatch):
    report = {"columnHeaders": [{"name": "day"}, {"name": "views"}], "rows": [["2026-11-01", 5]]}
    monkeypatch.setattr(google, "get", lambda url, **params: report)
    rows = server.analytics("2026-11-01", "2026-11-02", "views", dimensions="day")
    assert rows == [{"day": "2026-11-01", "views": 5}]
```

- [ ] **Шаг 2: убедиться, что падает** — `AttributeError: module has no attribute 'analytics'`.

- [ ] **Шаг 3: реализация инструментов**

```python
"""MCP-сервер (stdio, JSON-RPC по строкам) с read-only инструментами YouTube."""

import json
import sys
from collections.abc import Callable

from youtube_insights import google

DATA = "https://www.googleapis.com/youtube/v3"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
VIDEO_PARTS = "snippet,statistics,contentDetails,status"


def channel() -> dict:
    """Свой канал: профиль, статистика, id плейлиста загрузок."""
    return google.get(f"{DATA}/channels", part="snippet,statistics,contentDetails", mine="true")["items"][0]


def videos(max_results: int = 10, page_token: str | None = None) -> dict:
    """Последние загрузки канала с метаданными и статистикой."""
    uploads = channel()["contentDetails"]["relatedPlaylists"]["uploads"]
    page = google.get(
        f"{DATA}/playlistItems",
        part="contentDetails",
        playlistId=uploads,
        maxResults=max_results,
        pageToken=page_token,
    )
    ids = ",".join(item["contentDetails"]["videoId"] for item in page["items"])
    details = google.get(f"{DATA}/videos", part=VIDEO_PARTS, id=ids)
    return {"items": details["items"], "nextPageToken": page.get("nextPageToken")}


def video(video_id: str) -> dict:
    """Одно видео: метаданные, статистика, статус."""
    items = google.get(f"{DATA}/videos", part=VIDEO_PARTS, id=video_id)["items"]
    if not items:
        raise ValueError(f"Видео {video_id} не найдено")
    return items[0]


def analytics(
    start_date: str,
    end_date: str,
    metrics: str,
    dimensions: str | None = None,
    filters: str | None = None,
    sort: str | None = None,
    max_results: int | None = None,
) -> list[dict]:
    """Отчёт YouTube Analytics по своему каналу; строки возвращаются как словари."""
    report = google.get(
        ANALYTICS,
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        metrics=metrics,
        dimensions=dimensions,
        filters=filters,
        sort=sort,
        maxResults=max_results,
    )
    names = [column["name"] for column in report["columnHeaders"]]
    return [dict(zip(names, row, strict=True)) for row in report.get("rows", [])]


DATE = {"type": "string", "description": "YYYY-MM-DD"}
TOOLS: list[tuple[Callable[..., object], dict]] = [
    (channel, {"type": "object", "properties": {}}),
    (videos, {"type": "object", "properties": {
        "max_results": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
        "page_token": {"type": "string", "description": "nextPageToken из прошлого ответа"},
    }}),
    (video, {"type": "object", "properties": {"video_id": {"type": "string"}}, "required": ["video_id"]}),
    (analytics, {"type": "object", "properties": {
        "start_date": DATE,
        "end_date": DATE,
        "metrics": {"type": "string", "description": (
            "Через запятую: views, engagedViews, estimatedMinutesWatched, averageViewDuration, "
            "averageViewPercentage, likes, comments, shares, subscribersGained, subscribersLost; "
            "audienceWatchRatio только вместе с dimensions=elapsedVideoTimeRatio"
        )},
        "dimensions": {"type": "string", "description": (
            "Через запятую: day, month, video, creatorContentType, insightTrafficSourceType, "
            "deviceType, ageGroup, gender, country, elapsedVideoTimeRatio (кривая удержания, "
            "требует filters=video==ID)"
        )},
        "filters": {"type": "string", "description": "Например video==ID или creatorContentType==SHORTS"},
        "sort": {"type": "string", "description": "Например -views"},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 200},
    }, "required": ["start_date", "end_date", "metrics"]}),
]
```

- [ ] **Шаг 4: `uv run pytest -q`** — ожидается `3 passed`.

---

### Задача 4: stdio-цикл JSON-RPC

**Файлы:** дополнить `src/youtube_insights/server.py` (низ файла), `tests/test_server.py`.

- [ ] **Шаг 1: падающий тест — сквозной прогон через stdin/stdout**

```python
def test_serve_speaks_newline_json(monkeypatch, capsys):
    monkeypatch.setattr(google, "get", lambda url, **params: {"items": [{"id": "UC1"}]})
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "channel"}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "video", "arguments": {}}},
    ]
    monkeypatch.setattr(sys, "stdin", io.StringIO("".join(json.dumps(r) + "\n" for r in requests)))
    server.serve()
    replies = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3, 4]
    assert replies[0]["result"]["protocolVersion"] == "2025-06-18"
    names = {tool["name"] for tool in replies[1]["result"]["tools"]}
    assert names == {"channel", "videos", "video", "analytics"}
    assert json.loads(replies[2]["result"]["content"][0]["text"]) == {"id": "UC1"}
    assert replies[3]["result"]["isError"] is True
```

Тест фиксирует три контракта: одна строка = одно сообщение; уведомления без `id` не получают ответа; ошибка инструмента уходит модели как `isError`, а не ломает соединение.

- [ ] **Шаг 2: убедиться, что падает** — `AttributeError: module has no attribute 'serve'`.

- [ ] **Шаг 3: реализация**

```python
def respond(message: dict) -> dict:
    match message["method"]:
        case "initialize":
            return {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "youtube-insights", "version": "0.1.0"},
            }
        case "ping":
            return {}
        case "tools/list":
            return {"tools": [
                {"name": f.__name__, "description": f.__doc__, "inputSchema": schema} for f, schema in TOOLS
            ]}
        case "tools/call":
            params = message["params"]
            tool = {f.__name__: f for f, _ in TOOLS}[params["name"]]
            try:
                data = tool(**params.get("arguments", {}))
            except Exception as error:  # ошибка инструмента — ответ модели, не сбой протокола
                return {"content": [{"type": "text", "text": str(error)}], "isError": True}
            return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}
        case method:
            raise LookupError(f"Method not found: {method}")


def serve() -> None:
    for line in sys.stdin:
        message = json.loads(line)
        if "id" not in message:  # уведомления ответа не требуют
            continue
        try:
            reply = {"jsonrpc": "2.0", "id": message["id"], "result": respond(message)}
        except Exception as error:
            reply = {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32000, "message": str(error)}}
        print(json.dumps(reply), flush=True)


def main() -> None:
    if sys.argv[1:] == ["auth"]:
        google.login()
        return
    google.client()  # fail-fast: без секретов не стартуем
    serve()
```

Заметки:
- `protocolVersion` эхом: сервер использует только `initialize`/`tools/*`, которые есть во всех версиях протокола.
- Внешний `json.dumps` с `ensure_ascii=True` — это провод, клиент раскодирует `\u`-последовательности; внутренний текст для модели — без экранирования, иначе кириллица в заголовках стоит в разы больше токенов.
- В stdout только JSON; всё человеческое — в stderr.

- [ ] **Шаг 4: `uv run pytest -q`** — ожидается `4 passed`. Затем `uv run ruff check . && uv run ruff format --check .`.

---

### Задача 5: README и подключение к Claude

**Файлы:** заменить `README.md`.

- [ ] **Шаг 1: README.md** (структура, текст по-русски, без воды):

1. Что это: read-only MCP для своего канала, 4 инструмента, два scope, ноль зависимостей.
2. Google Cloud (один раз, ~20 мин): проект → включить *YouTube Data API v3* и *YouTube Analytics API* → OAuth consent screen (External, себя в Test users) → Credentials → OAuth client ID, тип **Desktop app** → скачать JSON.
3. Секреты: `mkdir -m 700 ~/.config/youtube-insights`, положить файл как `client_secret.json`. Папка вне iCloud/Dropbox.
4. Вход: `YOUTUBE_SECRETS_DIR=~/.config/youtube-insights uv run youtube-insights auth`. На экране Google должны быть только «Просмотр аккаунта YouTube» и «Просмотр отчётов YouTube Analytics». Если есть слово «управлять» — остановиться.
5. Конфиг Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "youtube": {
      "command": "uv",
      "args": ["run", "--directory", "/Users/<user>/Projects/insights-mcp-for-youtube", "youtube-insights"],
      "env": {"YOUTUBE_SECRETS_DIR": "/Users/<user>/.config/youtube-insights"}
    }
  }
}
```

6. Примеры запросов к `analytics`: по дням за 28 дней; топ видео (`dimensions=video, sort=-views, max_results=10`); только Shorts (`filters=creatorContentType==SHORTS`); удержание одного видео (`metrics=audienceWatchRatio, dimensions=elapsedVideoTimeRatio, filters=video==ID`); источники трафика; демография.
7. Ограничения: показов и CTR в API нет (из Studio вручную); комментарии и субтитры требуют write-scope и не включены; в режиме Testing вход повторять раз в 7 дней, лечится переводом проекта в Production без верификации.
8. Отзыв доступа: myaccount.google.com → Безопасность → Сторонние приложения.

---

### Задача 6: проверка перед «готово»

- [ ] `uv run pytest -q` → `4 passed`; `uv run ruff check .` чисто.
- [ ] `/code-lenses` на диффе, затем `/code-review-diff` (ветка против `main`). Замечания закрыть или объяснить.
- [ ] Ручной прогон: `auth` → на экране согласия только два «просмотр»-scope → в Claude Desktop вызвать `channel`, затем `analytics` по одному видео за известный период и сравнить `views` с последней CSV-выгрузкой из Studio.
- [ ] Проверить права: `ls -l $YOUTUBE_SECRETS_DIR/token.json` → `-rw-------`.
- [ ] Удалить клон апстрима из scratchpad (он только для анализа).

---

## Самопроверка плана

**Покрытие рекомендации из ресерча:** read-only scope — задача 2; свой Google-проект — README п.2; код зафиксирован локально, без `uvx --from git+` — конфиг в README п.5; секреты вне iCloud, 0600 — задачи 2 и 5; первый вход с проверкой экрана — задача 6; сравнение с CSV — задача 6. Пункт 6 ресерча (связка с навыком `youtube-analitika`) — отдельная задача после этой.

**Согласованность имён:** `google.get/post/call/save_token/access_token/login/client`, `server.channel/videos/video/analytics/TOOLS/respond/serve/main` — одинаковы во всех задачах и тестах.

**Корнеры, помеченные `ponytail`:** нет. Единственная сознательная простота — `videos` делает 3 запроса (channel → playlistItems → videos) вместо кэширования id плейлиста; квота 3 единицы, кэш не нужен.
