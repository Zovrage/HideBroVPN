from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.services.errors import PaymentGatewayError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PaymentCreateResult:
    gateway_payment_id: str
    status: str
    payment_url: str | None


@dataclass(slots=True)
class PaymentCheckResult:
    status: str
    paid_at: datetime | None


class BasePaymentGateway:
    provider_name: str = "base"

    async def create_payment(
        self,
        *,
        local_order_id: int,
        amount_rub: int,
        description: str,
        metadata: dict[str, str],
    ) -> PaymentCreateResult:
        raise NotImplementedError

    async def check_payment(self, *, gateway_payment_id: str) -> PaymentCheckResult:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class YooKassaGateway(BasePaymentGateway):
    provider_name = "yookassa"

    def __init__(
        self,
        *,
        shop_id: str,
        secret_key: str,
        return_url: str,
        timeout_sec: float = 20.0,
    ) -> None:
        self._return_url = return_url

        timeout = httpx.Timeout(
            connect=min(timeout_sec, 10),
            read=timeout_sec,
            write=timeout_sec,
            pool=timeout_sec,
        )

        self._client = httpx.AsyncClient(
            base_url="https://api.yookassa.ru",
            timeout=timeout,
            auth=httpx.BasicAuth(shop_id, secret_key),
        )

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        retries = 3 if method == "GET" else 2
        base_delay = 1

        for attempt in range(1, retries + 1):
            try:
                logger.debug(f"[YooKassa] {method} {url}")

                response = await self._client.request(method, url, **kwargs)

                # retry на 5xx
                if response.status_code >= 500:
                    logger.warning(
                        f"[YooKassa] Server error {response.status_code}, attempt {attempt}"
                    )
                    if attempt == retries:
                        return response
                    await asyncio.sleep(base_delay * attempt)
                    continue

                return response

            except httpx.TimeoutException as exc:
                logger.warning(
                    f"[YooKassa] Timeout (attempt {attempt}/{retries})"
                )
                if attempt == retries:
                    raise PaymentGatewayError(
                        "Время ожидания платежной системы истекло. Попробуйте еще раз."
                    ) from exc

            except httpx.RequestError as exc:
                logger.warning(
                    f"[YooKassa] Network error (attempt {attempt}/{retries}): {exc}"
                )
                if attempt == retries:
                    raise PaymentGatewayError(
                        "Платежная система временно недоступна. Попробуйте позже."
                    ) from exc

            await asyncio.sleep(base_delay * attempt)

        raise PaymentGatewayError("Не удалось выполнить запрос к платежной системе")

    async def close(self) -> None:
        await self._client.aclose()

    async def create_payment(
        self,
        *,
        local_order_id: int,
        amount_rub: int,
        description: str,
        metadata: dict[str, str],
    ) -> PaymentCreateResult:
        payload = {
            "amount": {"value": f"{amount_rub:.2f}", "currency": "RUB"},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": self._return_url,
            },
            "description": description,
            "metadata": {**metadata, "local_order_id": str(local_order_id)},
        }

        headers = {"Idempotence-Key": str(uuid.uuid4())}
        response = await self._request("POST", "/v3/payments", json=payload, headers=headers)

        if response.status_code >= 400:
            raise PaymentGatewayError(self._extract_error(response))

        body = response.json()
        confirmation = body.get("confirmation", {}) if isinstance(body, dict) else {}
        return PaymentCreateResult(
            gateway_payment_id=body["id"],
            status=body.get("status", "pending"),
            payment_url=confirmation.get("confirmation_url"),
        )

    async def check_payment(self, *, gateway_payment_id: str) -> PaymentCheckResult:
        response = await self._request("GET", f"/v3/payments/{gateway_payment_id}")
        if response.status_code >= 400:
            raise PaymentGatewayError(self._extract_error(response))

        body = response.json()
        status = body.get("status", "pending")
        paid_at_raw = body.get("paid_at") or body.get("captured_at")
        paid_at = self._parse_datetime(paid_at_raw) if isinstance(paid_at_raw, str) else None
        return PaymentCheckResult(status=status, paid_at=paid_at)

    @staticmethod
    def _extract_error(response: httpx.Response) -> str:
        try:
            body = response.json()
        except Exception:
            text = response.text.strip()
            return text[:300] if text else f"HTTP {response.status_code}"

        if isinstance(body, dict):
            description = body.get("description")
            if isinstance(description, str) and description:
                return description
            code = body.get("code")
            if isinstance(code, str) and code:
                return code
        return str(body)[:300]

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)


class MockGateway(BasePaymentGateway):
    provider_name = "mock"

    async def create_payment(
        self,
        *,
        local_order_id: int,
        amount_rub: int,
        description: str,
        metadata: dict[str, str],
    ) -> PaymentCreateResult:
        logger.warning("Используется Mock платежный провайдер. Заказ не будет оплачен автоматически.")
        return PaymentCreateResult(
            gateway_payment_id=f"mock_{local_order_id}",
            status="pending",
            payment_url=None,
        )

    async def check_payment(self, *, gateway_payment_id: str) -> PaymentCheckResult:
        return PaymentCheckResult(status="pending", paid_at=None)


def map_gateway_status(status: str) -> str:
    normalized = status.lower()
    if normalized in {"succeeded"}:
        return "succeeded"
    if normalized in {"canceled", "cancelled"}:
        return "canceled"
    if normalized in {"pending", "waiting_for_capture", "waiting_for_confirmation"}:
        return "pending"
    return "pending"
