from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TariffPlan:
    code: str
    title: str
    days: int
    price_rub: int
    emoji: str = ""
    is_trial: bool = False


PLANS: dict[str, TariffPlan] = {
    "trial3": TariffPlan(
        code="trial3",
        title="3 дня бесплатно",
        days=3,
        price_rub=0,
        is_trial=True,
    ),
    "m1": TariffPlan(code="m1", title="1 месяц", days=30, price_rub=1),
    "m3": TariffPlan(code="m3", title="3 месяца", days=90, price_rub=1),
    "m6": TariffPlan(code="m6", title="6 месяцев", days=180, price_rub=1),
    "m12": TariffPlan(code="m12", title="12 месяцев", days=365, price_rub=1),
}

PAID_PLAN_CODES: tuple[str, ...] = tuple(code for code, plan in PLANS.items() if not plan.is_trial)
DEVICE_LIMIT_PRICE_OVERRIDES: dict[int, dict[str, int]] = {
    3: {
        "m1": 1,
        "m3": 1,
        "m6": 1,
        "m12": 1,
    }
}


def get_plan(plan_code: str) -> TariffPlan:
    try:
        return PLANS[plan_code]
    except KeyError as exc:
        raise ValueError(f"Неизвестный тариф: {plan_code}") from exc


def get_plan_price(plan_code: str, device_limit: int) -> int:
    plan = get_plan(plan_code)
    if plan.is_trial:
        if device_limit != 1:
            raise ValueError("Пробный тариф доступен только для 1 устройства")
        return 0

    override = DEVICE_LIMIT_PRICE_OVERRIDES.get(device_limit, {})
    if plan_code in override:
        return override[plan_code]
    return plan.price_rub
