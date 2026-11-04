"""Official SIWC public-client OAuth for locally running personal apps.

Protocol: https://developers.openai.com/siwc/token-sharing-open-source/sign-in
No browser cookies, Codex token imports, or private backend endpoints are used.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Event, RLock
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import httpx
import jwt

from jarvis.security.credential_vault import CredentialVault

ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = f"openid profile email offline_access resource.invoke {PLAN_SCOPE}"
USAGE_URL = "https://chatgpt.com/#settings/Usage"


class ChatGPTAccount:
    def __init__(self, vault: CredentialVault, transport: httpx.BaseTransport | None = None) -> None:
        self.vault = vault
        self.transport = transport
        self._refresh_lock = RLock()

    @contextmanager
    def _session_lock(self) -> Iterator[None]:
        # Serialize rotating refresh tokens across threads and desktop instances.
        with self._refresh_lock:
            if self.vault.path is None:
                yield
                return
            import msvcrt
            self.vault.path.parent.mkdir(parents=True, exist_ok=True)
            with self.vault.path.with_suffix(".refresh.lock").open("a+b") as handle:
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

    def profiles(self) -> list[dict[str, Any]]:
        return [
            {"id": key, "email": value.get("email", "ChatGPT account"),
             "connected": bool(value.get("access_token")),
             "sharing": bool(value.get("access_token") and PLAN_SCOPE in value.get("scopes", []))}
            for key, value in self.vault.get("chatgpt").get("profiles", {}).items()
        ]

    def session(self) -> dict[str, Any]:
        saved = self.vault.get("chatgpt")
        return next((p for p in self.profiles() if p["id"] == saved.get("active")),
                    {"connected": False, "sharing": False, "email": "Not connected"})

    def select(self, profile_id: str) -> None:
        saved = self.vault.get("chatgpt")
        if profile_id not in saved.get("profiles", {}):
            raise ValueError("Unknown ChatGPT connection.")
        saved["active"] = profile_id
        self.vault.set("chatgpt", saved)

    def begin(self, redirect_uri: str, *, new_profile: bool = False) -> dict[str, Any]:
        saved = self.vault.get("chatgpt")
        if not saved.get("host_id"):
            saved["host_id"] = uuid4().urn
            self.vault.set("chatgpt", saved)
        previous = {} if new_profile else saved.get("profiles", {}).get(saved.get("active"), {})
        client_id = previous.get("client_id") or (None if new_profile else saved.get("pending_client_id"))
        client_id = client_id or "dynamic_agent_client"
        verifier = secrets.token_urlsafe(48)
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        params = {
            "client_id": client_id, "ext_agent_host_id": saved["host_id"],
            "response_type": "code", "redirect_uri": redirect_uri, "scope": SCOPES,
            "resource": RESOURCE, "state": state, "nonce": nonce,
            "code_challenge_method": "S256",
            "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("="),
        }
        if client_id == "dynamic_agent_client":
            params["agent_name_hint"] = "JARVIS"
        elif previous.get("id_token"):
            params["id_token_hint"] = previous["id_token"]
        return {"state": state, "nonce": nonce, "verifier": verifier, "client_id": client_id,
                "redirect_uri": redirect_uri, "created": time.monotonic(), "previous": previous,
                "url": ISSUER + "/api/accounts/authorize?" + urlencode(params), "used": False}

    def complete(self, attempt: dict[str, Any], query: dict[str, list[str]]) -> None:
        if attempt["used"] or time.monotonic() - attempt["created"] > 180:
            raise ValueError("Sign-in expired. Start a new sign-in.")
        attempt["used"] = True
        if not hmac.compare_digest(query.get("state", [""])[0], attempt["state"]):
            raise ValueError("Sign-in state did not match. Please try again.")
        if query.get("error"):
            raise ValueError("Sign-in or plan sharing was declined. Your existing connection is unchanged.")
        issued = query.get("client_id", [attempt["client_id"]])[0]
        if issued == "dynamic_agent_client" or not issued or not query.get("code"):
            raise ValueError("Sign-in did not return a registered client and code.")
        if attempt["client_id"] != "dynamic_agent_client" and issued != attempt["client_id"]:
            raise ValueError("Sign-in returned a different registration. Start a new connection instead.")
        saved = self.vault.get("chatgpt")
        saved["pending_client_id"] = issued
        self.vault.set("chatgpt", saved)
        with httpx.Client(timeout=20, transport=self.transport) as client:
            response = client.post(ISSUER + "/api/accounts/oauth/token", data={
                "grant_type": "authorization_code", "client_id": issued, "code": query["code"][0],
                "code_verifier": attempt["verifier"], "redirect_uri": attempt["redirect_uri"], "resource": RESOURCE,
            })
            if response.status_code != 200:
                raise ValueError("ChatGPT sign-in could not finish. Start a fresh sign-in; no API key is needed.")
            tokens = response.json()
            identity = self._verify_identity(client, tokens.get("id_token", ""), issued, attempt["nonce"])
        previous = attempt["previous"]
        if previous.get("subject") and previous["subject"] != identity["sub"]:
            raise ValueError("A different account signed in. Add it as a new connection instead.")
        profile = self._token_record(tokens, issued)
        profile.update(subject=identity["sub"], email=identity.get("email", "ChatGPT account"))
        saved = self.vault.get("chatgpt")
        saved.setdefault("profiles", {})[issued] = profile
        saved["active"] = issued
        saved.pop("pending_client_id", None)
        self.vault.set("chatgpt", saved)

    @staticmethod
    def _verify_identity(client: httpx.Client, token: str, client_id: str, nonce: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256":
                raise ValueError("Unsupported identity signature")
            keys_response = client.get(ISSUER + "/.well-known/jwks.json")
            keys_response.raise_for_status()
            key = next(k for k in keys_response.json()["keys"] if k.get("kid") == header.get("kid"))
            identity = jwt.decode(token, jwt.PyJWK.from_dict(key, algorithm="RS256").key,
                                  algorithms=["RS256"], issuer=ISSUER, audience=client_id,
                                  options={"require": ["exp", "iat", "sub", "iss", "aud", "nonce"]})
            if not hmac.compare_digest(str(identity["nonce"]), nonce):
                raise ValueError("Identity nonce did not match")
            return identity
        except (jwt.PyJWTError, ValueError, KeyError, StopIteration) as exc:
            raise ValueError("ChatGPT identity verification failed. Please sign in again.") from exc

    @staticmethod
    def _token_record(tokens: dict[str, Any], client_id: str) -> dict[str, Any]:
        if not isinstance(tokens.get("access_token"), str) or not tokens["access_token"]:
            raise ValueError("ChatGPT did not return a usable access token.")
        return {"client_id": client_id, "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token"), "id_token": tokens.get("id_token"),
                "expires_at": time.time() + float(tokens.get("expires_in", 3600)),
                "scopes": str(tokens.get("scope", "")).split()}

    def sign_in(self, *, new_profile: bool = False, cancel: Event | None = None) -> None:
        callback: dict[str, list[str]] = {}
        finished = Event()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if urlsplit(self.path).path != "/auth/callback":
                    self.send_error(404)
                    return
                callback.update(parse_qs(urlsplit(self.path).query))
                finished.set()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(b"Return to JARVIS to see whether sign-in completed.")

            def log_message(self, format: str, *args: Any) -> None:
                pass  # Never log callback URLs containing authorization codes.

        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            server.timeout = 0.2
            uri = f"http://127.0.0.1:{server.server_port}/auth/callback"
            attempt = self.begin(uri, new_profile=new_profile)
            if not webbrowser.open(attempt["url"]):
                raise ValueError("Could not open your browser. Check the default browser and try again.")
            while not finished.is_set():
                if cancel and cancel.is_set():
                    raise ValueError("Sign-in cancelled.")
                if time.monotonic() - attempt["created"] > 180:
                    raise ValueError("Sign-in timed out. Please try again.")
                server.handle_request()
        self.complete(attempt, callback)

    def access_token(self) -> str:
        with self._session_lock():
            saved = self.vault.get("chatgpt")
            profile = saved.get("profiles", {}).get(saved.get("active"), {})
            if not profile.get("access_token") or PLAN_SCOPE not in profile.get("scopes", []):
                raise ValueError("Connect ChatGPT and allow plan usage in Settings first.")
            if profile["expires_at"] > time.time() + 60:
                return profile["access_token"]
            if not profile.get("refresh_token"):
                raise ValueError("ChatGPT connection expired. Reconnect in Settings.")
            with httpx.Client(timeout=20, transport=self.transport) as client:
                response = client.post(ISSUER + "/api/accounts/oauth/token", data={
                    "grant_type": "refresh_token", "client_id": profile["client_id"],
                    "refresh_token": profile["refresh_token"], "resource": RESOURCE,
                })
            if response.status_code != 200:
                raise ValueError("ChatGPT session could not refresh. Reconnect in Settings.")
            tokens = response.json()
            updated = self._token_record(tokens, profile["client_id"])
            updated["refresh_token"] = updated["refresh_token"] or profile.get("refresh_token")
            updated["id_token"] = updated["id_token"] or profile.get("id_token")
            if "scope" not in tokens:
                updated["scopes"] = profile["scopes"]
            profile.update(updated)
            self.vault.set("chatgpt", saved)
            if PLAN_SCOPE not in profile["scopes"]:
                raise ValueError("ChatGPT plan sharing is no longer enabled. Reconnect in Settings.")
            return profile["access_token"]

    def list_models(self) -> list[dict[str, str]]:
        with httpx.Client(timeout=20, transport=self.transport) as client:
            response = client.get(RESOURCE + "/models", headers={"Authorization": "Bearer " + self.access_token()})
        if response.status_code != 200:
            raise ValueError("Could not load this ChatGPT account's models. Reconnect or check your plan access.")
        return [{"id": m["slug"], "name": m.get("display_name", m["slug"])}
                for m in response.json().get("models", []) if m.get("visibility") == "list" and m.get("slug")]

    def sign_out(self) -> bool:
        with self._session_lock():
            saved = self.vault.get("chatgpt")
            profile = saved.get("profiles", {}).get(saved.get("active"), {})
            revoked = not bool(profile.get("refresh_token"))
            try:
                if profile.get("refresh_token"):
                    with httpx.Client(timeout=10, transport=self.transport) as client:
                        response = client.post(ISSUER + "/api/accounts/oauth/revoke", data={
                            "token": profile["refresh_token"], "token_type_hint": "refresh_token",
                            "client_id": profile["client_id"],
                        })
                    revoked = response.status_code == 200
            except httpx.HTTPError:
                revoked = False
            for key in ("access_token", "refresh_token", "id_token", "expires_at", "scopes"):
                profile.pop(key, None)
            self.vault.set("chatgpt", saved)
            return revoked
