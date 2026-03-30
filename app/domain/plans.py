from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TariffPlan:
    code: str
    title: str
    days: int
    price_rub: int
    emoji: str
    is_trial: bool = False


PLANS: dict[str, TariffPlan] = {
    "trial3": TariffPlan(
        code="trial3",
        title="3 дня бесплатно",
        days=3,
        price_rub=0,
        emoji="\U0001F193",
        is_trial=True,
    ),
    "m1": TariffPlan(code="m1", title="1 месяц", days=30, price_rub=100, emoji="\U0001F4C5"),
    "m3": TariffPlan(code="m3", title="3 месяца", days=90, price_rub=300, emoji="\U0001F525"),
    "m6": TariffPlan(code="m6", title="6 месяцев", days=180, price_rub=600, emoji="\U0001F680"),
    "m12": TariffPlan(code="m12", title="12 месяцев", days=365, price_rub=1000, emoji="\U0001F3C6"),
}

PAID_PLAN_CODES: tuple[str, ...] = tuple(code for code, plan in PLANS.items() if not plan.is_trial)


def get_plan(plan_code: str) -> TariffPlan:
    try:
        return PLANS[plan_code]
    except KeyError as exc:
        raise ValueError(f"Неизвестный тариф: {plan_code}") from exc
