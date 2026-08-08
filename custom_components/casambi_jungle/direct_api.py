from __future__ import annotations
import json
from typing import Any
from urllib.parse import urlencode
from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

def direct_available(entry) -> bool:
    transport = entry.data.get("transport", "mqtt")
    url = str(entry.data.get("web_url", "") or "").rstrip("/")
    return bool(url) and transport in {"direct", "hybrid"}

def web_url(entry) -> str:
    return str(entry.data.get("web_url", "") or "").rstrip("/")

async def direct_get_json(hass: HomeAssistant, entry, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    base = web_url(entry)
    if not base:
        return {"ok": False, "error": "no web_url"}
    url = f"{base}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    session = async_get_clientsession(hass)
    try:
        async with session.get(url, timeout=8) as resp:
            text = await resp.text()
            if resp.status >= 400:
                return {"ok": False, "status": resp.status, "error": text}
            try:
                return json.loads(text)
            except Exception:
                return {"ok": True, "text": text}
    except (ClientError, TimeoutError) as err:
        return {"ok": False, "error": str(err)}
    except Exception as err:
        return {"ok": False, "error": str(err)}
