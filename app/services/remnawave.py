from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.services.errors import RemnawaveAPIError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RemnawaveUser:
    uuid: str
    short_uuid: str | None
    username: str
    subscription_url: str
    expire_at: datetime


@dataclass(slots=True)
class RemnawaveDevice:
    hwid: str
    platform: str | None
    os_version: str | None
    device_model: str | None
    user_agent: str | None
    created_at: datetime


def _to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


class RemnawaveClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_sec: float,
        api_token: str | None,
        admin_username: str | None,
        admin_password: str | None,
        username_prefix: str,
        username_min_digits: int,
        username_max_digits: int,
        internal_squad_uuid: str,
        device_limit: int,
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_sec)
        self._api_token = api_token
        self._admin_username = admin_username
        self._admin_password = admin_password
        self._token_lock = asyncio.Lock()

        self._username_prefix = username_prefix
        self._username_min_digits = username_min_digits
        self._username_max_digits = username_max_digits
        self._internal_squad_uuid = internal_squad_uuid
        self._device_limit = device_limit

    async def close(self) -> None:
        await self._client.aclose()

    async def ensure_ready(self) -> None:
        await self._ensure_token(force=False)
        squads = await self._request("GET", "/api/internal-squads")
        internal = squads.get("internalSquads", []) if isinstance(squads, dict) else []
        if not any(item.get("uuid") == self._internal_squad_uuid for item in internal):
            raise RemnawaveAPIError(
                500,
                f"Внутренний сквад {self._internal_squad_uuid} не найден в Remnawave",
            )

    async def _ensure_token(self, *, force: bool) -> str:
        if self._api_token and not force:
            return self._api_token

        if not self._admin_username or not self._admin_password:
            if self._api_token:
                return self._api_token
            raise RemnawaveAPIError(
                401,
                "Не задан API-токен Remnawave и нет логина/пароля администратора",
            )

        async with self._token_lock:
            if self._api_token and not force:
                return self._api_token

            response = await self._client.post(
                "/api/auth/login",
                json={
                    "username": self._admin_username,
                    "password": self._admin_password,
                },
            )
            if response.status_code >= 400:
                raise RemnawaveAPIError(response.status_code, self._extract_error(response))

            payload = response.json()
            token = payload.get("response", {}).get("accessToken")
            if not token:
                raise RemnawaveAPIError(500, "Remnawave не вернул accessToken")

            self._api_token = token
            logger.info("Получен JWT токен Remnawave")
            return token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> Any:
        token = await self._ensure_token(force=False)
        headers = {"Authorization": f"Bearer {token}"}

        response = await self._client.request(
            method,
            path,
            json=json_data,
            params=params,
            headers=headers,
        )

        if response.status_code == 401 and retry_auth and self._admin_username and self._admin_password:
            await self._ensure_token(force=True)
            return await self._request(
                method,
                path,
                json_data=json_data,
                params=params,
                retry_auth=False,
            )

        if response.status_code >= 400:
            raise RemnawaveAPIError(response.status_code, self._extract_error(response))

        payload = response.json()
        return payload.get("response", payload)

    @staticmethod
    def _extract_error(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except Exception:
            text = response.text.strip()
            return text[:300] if text else f"HTTP {response.status_code}"

        if isinstance(payload, dict):
            for key in ("message", "error", "detail"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            if "response" in payload and isinstance(payload["response"], str):
                return payload["response"]
        return str(payload)[:300]

    def _generate_username(self) -> str:
        digits_len = random.randint(self._username_min_digits, self._username_max_digits)
        lower = 10 ** (digits_len - 1)
        upper = (10**digits_len) - 1
        return f"{self._username_prefix}{random.randint(lower, upper)}"

    @staticmethod
    def _is_duplicate_username(error: RemnawaveAPIError) -> bool:
        text = error.message.lower()
        return error.status_code in {400, 409} and "username" in text and (
            "exist" in text or "taken" in text or "already" in text
        )

    @staticmethod
    def _map_user(data: dict[str, Any]) -> RemnawaveUser:
        return RemnawaveUser(
            uuid=data["uuid"],
            short_uuid=data.get("shortUuid"),
            username=data["username"],
            subscription_url=data["subscriptionUrl"],
            expire_at=_parse_dt(data["expireAt"]),
        )

    async def create_user(self, *, expire_at: datetime, telegram_id: int | None = None) -> RemnawaveUser:
        last_error: RemnawaveAPIError | None = None

        for _ in range(20):
            username = self._generate_username()
            payload: dict[str, Any] = {
                "username": username,
                "expireAt": _to_utc_iso(expire_at),
                "hwidDeviceLimit": self._device_limit,
                "activeInternalSquads": [self._internal_squad_uuid],
            }
            if telegram_id is not None:
                payload["telegramId"] = telegram_id

            try:
                response = await self._request("POST", "/api/users", json_data=payload)
                return self._map_user(response)
            except RemnawaveAPIError as exc:
                if self._is_duplicate_username(exc):
                    last_error = exc
                    continue
                raise

        if last_error:
            raise last_error
        raise RemnawaveAPIError(500, "Не удалось сгенерировать уникальный username в Remnawave")

    async def extend_user(self, *, user_uuid: str, new_expire_at: datetime) -> RemnawaveUser:
        payload = {
            "uuid": user_uuid,
            "expireAt": _to_utc_iso(new_expire_at),
            "hwidDeviceLimit": self._device_limit,
            "activeInternalSquads": [self._internal_squad_uuid],
        }
        response = await self._request("PATCH", "/api/users", json_data=payload)
        return self._map_user(response)

    async def get_user(self, *, user_uuid: str) -> RemnawaveUser:
        response = await self._request("GET", f"/api/users/by-uuid/{user_uuid}")
        return self._map_user(response)

    async def get_user_devices(self, *, user_uuid: str) -> tuple[int, list[RemnawaveDevice]]:
        response = await self._request("GET", f"/api/hwid/devices/{user_uuid}")
        total = int(response.get("total", 0))
        devices_raw = response.get("devices", [])

        devices: list[RemnawaveDevice] = []
        for item in devices_raw:
            created = item.get("createdAt")
            created_at = _parse_dt(created) if isinstance(created, str) else datetime.now(tz=timezone.utc)
            devices.append(
                RemnawaveDevice(
                    hwid=item.get("hwid", "unknown"),
                    platform=item.get("platform"),
                    os_version=item.get("osVersion"),
                    device_model=item.get("deviceModel"),
                    user_agent=item.get("userAgent"),
                    created_at=created_at,
                )
            )
        return total, devices
