"""Async HTTP client for tiger-sms.com API."""
from __future__ import annotations

import httpx
from typing import Optional


TIGER_BASE = "https://api.tiger-sms.com/stubs/handler_api.php"


class TigerSMSError(Exception):
    """Raised when the tiger-sms API returns an error code."""


class TigerSMSClient:
    def __init__(self, api_key: str, timeout: float = 20.0) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def _call(self, params: dict) -> str:
        params = {"api_key": self._api_key, **params}
        resp = await self._client.get(TIGER_BASE, params=params)
        resp.raise_for_status()
        return resp.text.strip()

    async def get_balance(self) -> float:
        txt = await self._call({"action": "getBalance"})
        if not txt.startswith("ACCESS_BALANCE"):
            raise TigerSMSError(txt)
        # format: ACCESS_BALANCE:12.34
        return float(txt.split(":", 1)[1])

    async def get_number(self, service: str, country: str) -> tuple[str, str]:
        """Returns (activation_id, phone_number)."""
        txt = await self._call({
            "action": "getNumber",
            "service": service,
            "country": country,
        })
        if not txt.startswith("ACCESS_NUMBER"):
            raise TigerSMSError(txt)
        parts = txt.split(":")
        # ACCESS_NUMBER:<id>:<phone>
        if len(parts) < 3:
            raise TigerSMSError(txt)
        return parts[1], parts[2]

    async def get_status(self, activation_id: str) -> tuple[str, Optional[str]]:
        """Returns (status, code_if_any).

        Possible statuses:
            STATUS_WAIT_CODE, STATUS_WAIT_RETRY, ACCESS_CANCEL, STATUS_OK
        """
        txt = await self._call({"action": "getStatus", "id": activation_id})
        if txt.startswith("STATUS_OK"):
            # STATUS_OK:<code>
            _, code = txt.split(":", 1)
            return "STATUS_OK", code
        if txt in ("STATUS_WAIT_CODE", "STATUS_WAIT_RETRY", "ACCESS_CANCEL"):
            return txt, None
        # unknown — treat as error
        raise TigerSMSError(txt)

    async def set_status(self, activation_id: str, status: int) -> str:
        """status: 1=ready, 3=request another, 6=complete, 8=cancel."""
        txt = await self._call({
            "action": "setStatus",
            "status": str(status),
            "id": activation_id,
        })
        return txt
