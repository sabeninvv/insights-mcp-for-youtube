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

from .constants import (
    AUTH_URL,
    CLIENT_SECRET_FILE,
    LOGIN_TIMEOUT,
    REQUEST_TIMEOUT,
    SCOPES,
    SECRETS_DIR_ENV,
    TOKEN_FILE,
    TOKEN_URL,
)


def secrets_dir() -> Path:
    return Path(os.environ[SECRETS_DIR_ENV])


def client() -> dict:
    """client_secret.json из Google Cloud (OAuth-клиент типа Desktop)."""
    return json.loads((secrets_dir() / CLIENT_SECRET_FILE).read_text())["installed"]


def call(request: Request) -> dict:
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Google API {error.code}: {error.read().decode()}") from None


def post(url: str, form: dict) -> dict:
    return call(Request(url, data=urlencode(form).encode(), method="POST"))


def save_token(token: dict) -> None:
    path = secrets_dir() / TOKEN_FILE
    token["expires_at"] = time.time() + token["expires_in"]
    path.touch(mode=0o600)
    path.chmod(0o600)  # touch не меняет права существующего файла
    path.write_text(json.dumps(token))


def access_token() -> str:
    path = secrets_dir() / TOKEN_FILE
    if not path.exists():
        raise RuntimeError(f"Нет {TOKEN_FILE}. Выполни: uv run youtube-insights auth")
    token = json.loads(path.read_text())
    if token["expires_at"] < time.time() + 60:
        secret = client()
        token |= post(
            TOKEN_URL,
            {
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
                "client_id": secret["client_id"],
                "client_secret": secret["client_secret"],
            },
        )
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

    query: dict = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            query.update(parse_qs(urlparse(self.path).query))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Вернитесь в терминал.".encode())

        def log_message(self, *args: object) -> None:
            pass

    with HTTPServer(("127.0.0.1", 0), Callback) as server:
        redirect = f"http://127.0.0.1:{server.server_port}"
        params = {
            "client_id": secret["client_id"],
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        url = f"{AUTH_URL}?{urlencode(params)}"
        print(f"Если браузер не открылся, открой вручную:\n{url}", file=sys.stderr)
        webbrowser.open(url)
        server.timeout = LOGIN_TIMEOUT
        server.handle_request()

    if query.get("state") != [state] or "code" not in query:
        raise SystemExit(
            f"OAuth не удался: {query.get('error', ['нет кода или неверный state'])[0]}"
        )
    save_token(
        post(
            TOKEN_URL,
            {
                "code": query["code"][0],
                "client_id": secret["client_id"],
                "client_secret": secret["client_secret"],
                "redirect_uri": redirect,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
        )
    )
    print(f"Токен сохранён: {secrets_dir() / TOKEN_FILE}", file=sys.stderr)
