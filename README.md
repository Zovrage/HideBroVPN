# HideBroVPN Telegram Bot

Production-oriented async Telegram bot for selling VPN subscriptions with Remnawave integration.

## Features

- Async bot on `aiogram 3`
- PostgreSQL for persistent business data
- Redis for FSM/session state
- Remnawave user creation/extension
  - Username format: `HideBro_<6-7 digits>`
  - Device limit: `3`
  - Internal squad is assigned at create time
- Tariffs:
  - `3 days` free trial (once)
  - `1 month` - `100 ₽`
  - `3 months` - `300 ₽`
  - `6 months` - `600 ₽`
  - `12 months` - `1000 ₽`
- Payment flow (`Pay` + `Check payment`) via YooKassa (or `mock` mode)
- Referral program:
  - Personal invite link
  - +5 days for inviter after invited user's first paid purchase
  - If inviter has multiple keys, inviter chooses the key to extend
- Admin panel `/admin`
  - Available only for admin IDs from env
  - Stats
  - Free key issuance by Telegram ID / username

## Quick Start (Docker)

1. Copy env template:

```bash
cp .env.example .env
```

2. Fill required values in `.env`:
- `BOT_TOKEN`
- `ADMIN_IDS`
- `REMNAWAVE_*`
- `YOOKASSA_*` (if `PAYMENTS_PROVIDER=yookassa`)

3. Run:

```bash
docker compose up -d --build
```

Bot container runs migrations automatically (`alembic upgrade head`) on start.

## Local Run

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python -m app.main
```

## Main Flows

- `/start` -> main menu
- `Подключиться` -> tariffs
  - Paid tariffs: `Оплатить`, `Проверить оплату`, `Назад`
- `Мои подписки` -> list with actions
  - `Подключиться`
  - `Продлить`
  - `Устройства`
- `Пригласить друга` -> personal referral link
- `Тех поддержка` -> opens `@HideBroSupport`
- `/admin` -> admin panel (admins only)

## Notes

- Remnawave auth supports:
  - `REMNAWAVE_API_TOKEN`, or
  - `REMNAWAVE_ADMIN_USERNAME` + `REMNAWAVE_ADMIN_PASSWORD`
- Ensure `REMNAWAVE_INTERNAL_SQUAD_UUID` is valid in your panel.
