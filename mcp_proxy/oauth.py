from __future__ import annotations

import json
import sys
import time
import webbrowser
from asyncio import Event, get_event_loop
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlparse

from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken


CALLBACK_PORT = 18732
CALLBACK_PATH = "/oauth/callback"


class FileTokenStorage:
    """Persists OAuth tokens and client info to a JSON file on disk.

    Works around a bug in the MCP SDK where loading cached tokens doesn't
    restore the expiry clock. The SDK stores expires_in (a relative TTL) but
    never converts it to an absolute time on reload, so it treats expired
    tokens as valid, sends them, gets a 401, and triggers a full browser
    re-auth instead of silently refreshing. We persist expires_at (absolute
    timestamp) alongside the token and recompute expires_in on load so the
    SDK's expiry check works correctly across restarts.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def _read(self) -> dict[str, Any]:
        if self._path.exists():
            return json.loads(self._path.read_text())
        return {}

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._path.write_text(json.dumps(data, indent=2))
        self._path.chmod(0o600)

    async def get_tokens(self) -> OAuthToken | None:
        data = self._read()
        raw = data.get("tokens")
        if not raw:
            return None
        token = OAuthToken.model_validate(raw)
        expires_at = data.get("expires_at")
        if expires_at is not None and token.expires_in is not None:
            remaining = int(expires_at - time.time())
            token = token.model_copy(update={"expires_in": max(0, remaining)})
        return token

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = self._read()
        data["tokens"] = tokens.model_dump(mode="json")
        if tokens.expires_in is not None:
            data["expires_at"] = time.time() + tokens.expires_in
        self._write(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        data = self._read()
        raw = data.get("client_info")
        if raw:
            return OAuthClientInformationFull.model_validate(raw)
        return None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        data = self._read()
        data["client_info"] = client_info.model_dump(mode="json")
        self._write(data)


_captured_code: str | None = None
_captured_state: str | None = None
_callback_received: Event | None = None


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        global _captured_code, _captured_state
        parsed = urlparse(self.path)
        if parsed.path != CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return

        params = parse_qs(parsed.query)
        _captured_code = params.get("code", [None])[0]
        _captured_state = params.get("state", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h2>Authentication successful.</h2>"
            b"<p>You can close this tab and return to the terminal.</p>"
            b"</body></html>"
        )

        if _callback_received is not None:
            _callback_received._loop.call_soon_threadsafe(_callback_received.set)

    def log_message(self, format: str, *args: Any) -> None:
        pass


async def _redirect_handler(authorization_url: str) -> None:
    print(f"Opening browser for OAuth login...", file=sys.stderr)
    print(f"If the browser doesn't open, visit: {authorization_url}", file=sys.stderr)
    webbrowser.open(authorization_url)


async def _callback_handler() -> tuple[str, str | None]:
    global _callback_received, _captured_code, _captured_state
    _captured_code = None
    _captured_state = None

    loop = get_event_loop()
    _callback_received = Event()
    _callback_received._loop = loop  # type: ignore[attr-defined]

    server = HTTPServer(("127.0.0.1", CALLBACK_PORT), _OAuthCallbackHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        await _callback_received.wait()
    finally:
        server.shutdown()
        thread.join(timeout=2)

    if _captured_code is None:
        raise RuntimeError("OAuth callback did not receive an authorization code")

    return _captured_code, _captured_state


def create_oauth_provider(server_url: str, token_file: Path) -> OAuthClientProvider:
    storage = FileTokenStorage(token_file)
    redirect_uri = f"http://127.0.0.1:{CALLBACK_PORT}{CALLBACK_PATH}"

    client_metadata = OAuthClientMetadata(
        redirect_uris=[redirect_uri],
        client_name="mcp-proxy-filter",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )

    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=client_metadata,
        storage=storage,
        redirect_handler=_redirect_handler,
        callback_handler=_callback_handler,
    )
