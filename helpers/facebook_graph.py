# helpers/facebook_graph.py
from __future__ import annotations

import os
import aiohttp
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from dotenv import load_dotenv

def _get_env(name: str, default: Optional[str] = None, required: bool = False) -> str:
    val = os.getenv(name, default)
    if required and not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val or ""

def _graph_base(version: Optional[str]) -> str:
    v = (version or _get_env("META_GRAPH_VERSION", "v19.0")).strip()
    if not v.startswith("v"):
        v = f"v{v}"
    return f"https://graph.facebook.com/{v}"

class FacebookGraph:
    """
    Lightweight async client for Meta Graph API (Lead Ads).

    Usage:
        graph = FacebookGraph.from_env()  # reads META_APP_ID, META_APP_SECRET, META_GRAPH_VERSION
        # ...then call graph.get_user_pages(token) etc.
    """

    def __init__(self, app_id: str, app_secret: str, version: Optional[str] = None):
        if not app_id or not app_secret:
            raise RuntimeError("FacebookGraph requires app_id and app_secret")
        self.app_id = app_id
        self.app_secret = app_secret
        self.version = version or _get_env("META_GRAPH_VERSION", "v19.0")
        self.GRAPH = _graph_base(self.version)

    @classmethod
    def from_env(cls) -> "FacebookGraph":
        """
        Create client using env vars:
          - META_APP_ID (required)
          - META_APP_SECRET (required)
          - META_GRAPH_VERSION (optional; defaults to v19.0)
        """
        app_id = _get_env("META_APP_ID", required=True)
        app_secret = _get_env("META_APP_SECRET", required=True)
        version = _get_env("META_GRAPH_VERSION", "v19.0")
        return cls(app_id=app_id, app_secret=app_secret, version=version)

    # ---------- SECURITY ----------
    def verify_signature(self, raw_body: bytes, signature_header: Optional[str]) -> bool:
        """
        Validate X-Hub-Signature-256 header for Webhooks.
        """
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        provided = signature_header.split("=", 1)[1]
        expected = hmac.new(
            key=self.app_secret.encode("utf-8"),
            msg=raw_body,
            digestmod=hashlib.sha256
        ).hexdigest()
        try:
            return hmac.compare_digest(provided, expected)
        except Exception:
            return False

    # ---------- OAUTH ----------
    async def exchange_code_for_user_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """
        Exchange OAuth 'code' -> short-lived user token.
        """
        url = f"{self.GRAPH}/oauth/access_token"
        params = {
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "redirect_uri": redirect_uri,
            "code": code
        }
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params) as r:
                return await r.json()

    async def extend_user_token(self, short_lived_token: str) -> Dict[str, Any]:
        """
        Convert short-lived token -> long-lived (~60 days).
        """
        url = f"{self.GRAPH}/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "fb_exchange_token": short_lived_token
        }
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params) as r:
                return await r.json()

    async def get_me(self, user_token: str) -> Dict[str, Any]:
        url = f"{self.GRAPH}/me"
        params = {"access_token": user_token}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params) as r:
                return await r.json()

    async def get_user_pages(self, user_token: str) -> Dict[str, Any]:
        """
        Returns pages (and page access tokens) the user manages.
        """
        url = f"{self.GRAPH}/me/accounts"
        params = {"access_token": user_token}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params) as r:
                return await r.json()

    # ---------- PAGE OPS ----------
    async def subscribe_app_to_page(self, page_id: str, page_token: str) -> Dict[str, Any]:
        """
        Subscribe your app to specific page events (here: leadgen).
        Requires Webhooks (Page) product enabled for your App.
        """
        url = f"{self.GRAPH}/{page_id}/subscribed_apps"
        data = {
            "subscribed_fields": "leadgen",
            "access_token": page_token
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(url, data=data) as r:
                return await r.json()

    # ---------- LEADS ----------
    async def fetch_lead(self, leadgen_id: str, page_token: str) -> Dict[str, Any]:
        """
        Pull lead details by leadgen_id after webhook.
        """
        url = f"{self.GRAPH}/{leadgen_id}"
        params = {
            "access_token": page_token,
            "fields": "created_time,field_data,ad_id,form_id,platform,retailer_item_id"
        }
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params) as r:
                return await r.json()
