from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MainMenuCb(CallbackData, prefix="mm"):
    action: str


class TariffCb(CallbackData, prefix="tf"):
    plan: str
    mode: str
    sub: int = 0


class PlanActionCb(CallbackData, prefix="pa"):
    action: str
    plan: str
    mode: str
    sub: int = 0


class SubscriptionCb(CallbackData, prefix="sb"):
    action: str
    sub: int


class ReferralCb(CallbackData, prefix="rf"):
    action: str


class RewardChoiceCb(CallbackData, prefix="rw"):
    referral_id: int
    sub: int


class AdminMenuCb(CallbackData, prefix="am"):
    action: str


class AdminIssueCb(CallbackData, prefix="ai"):
    action: str
    value: str = "0"
