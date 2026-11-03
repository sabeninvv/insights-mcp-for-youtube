"""Тесты youtube_insights: токен, GET, инструменты, stdio-цикл."""

import io
import json
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

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
        google,
        "post",
        lambda url, form: forms.append(form) or {"access_token": "new", "expires_in": 3600},
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
        google,
        "call",
        lambda req: seen.update(url=req.full_url, auth=req.get_header("Authorization")) or {},
    )
    google.get("https://x/y", a=1, b=None)
    assert seen == {"url": "https://x/y?a=1", "auth": "Bearer tok"}


def test_analytics_rows_as_dicts(monkeypatch):
    report = {"columnHeaders": [{"name": "day"}, {"name": "views"}], "rows": [["2026-11-01", 5]]}
    monkeypatch.setattr(google, "get", lambda url, **params: report)
    rows = server.analytics("2026-11-01", "2026-11-02", "views", dimensions="day")
    assert rows == [{"day": "2026-11-01", "views": 5}]


def test_serve_speaks_newline_json(monkeypatch, capsys):
    monkeypatch.setattr(google, "get", lambda url, **params: {"items": [{"id": "UC1"}]})
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "v"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "channel"}},
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "video", "arguments": {}},
        },
    ]
    monkeypatch.setattr(sys, "stdin", io.StringIO("".join(json.dumps(r) + "\n" for r in requests)))
    server.serve()
    replies = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3, 4]
    assert replies[0]["result"]["protocolVersion"] == "v"
    names = {tool["name"] for tool in replies[1]["result"]["tools"]}
    assert names == {"channel", "videos", "video", "analytics"}
    assert json.loads(replies[2]["result"]["content"][0]["text"]) == {"id": "UC1"}
    assert replies[3]["result"]["isError"] is True


def test_serve_error_codes_and_survives_bad_input(monkeypatch, capsys):
    lines = [
        "{oops",
        "5",
        '{"id": 1, "method": "resources/list"}',
        '{"id": 2, "method": "tools/call", "params": {"name": "nope"}}',
        '{"id": 3, "method": "ping"}',
    ]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(lines) + "\n"))
    server.serve()
    replies = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    codes = [reply["error"]["code"] for reply in replies[:4]]
    assert codes == [-32700, -32600, -32601, -32602]
    assert replies[4] == {"jsonrpc": "2.0", "id": 3, "result": {}}


def test_channel_without_items_has_clear_error(monkeypatch):
    monkeypatch.setattr(google, "get", lambda url, **params: {})
    with pytest.raises(ValueError, match="нет канала"):
        server.channel()


def test_token_is_private_before_secret_is_written(secrets, monkeypatch):
    modes = []
    write_text = Path.write_text

    def spy(path, text):
        modes.append(path.stat().st_mode & 0o777)
        return write_text(path, text)

    monkeypatch.setattr(Path, "write_text", spy)
    google.save_token({"access_token": "a", "refresh_token": "r", "expires_in": 1})
    assert modes == [0o600]


def test_login_asks_only_readonly_and_rejects_wrong_state(secrets, monkeypatch):
    opened = {}

    def browser(url):
        opened.update(parse_qs(urlparse(url).query))
        target = f"{opened['redirect_uri'][0]}?code=c&state=evil"
        threading.Thread(target=lambda: urlopen(target).read()).start()

    monkeypatch.setattr(google.webbrowser, "open", browser)
    monkeypatch.setattr(google, "post", lambda url, form: pytest.fail("обмен кода при чужом state"))
    with pytest.raises(SystemExit):
        google.login()
    assert opened["scope"][0].split() == [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
    ]
    assert not (secrets / "token.json").exists()
