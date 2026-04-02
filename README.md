# HideBroVPN Telegram Bot

Продакшен-ориентированный асинхронный Telegram-бот для продажи VPN-подписок с интеграцией Remnawave.

## Возможности

- Асинхронный бот на `aiogram 3`
- PostgreSQL для бизнес-данных
- Redis для FSM и сессий
- Remnawave:
  - создание и продление пользователей
  - формат имени: `HideBro_<6-7 цифр>`
  - лимит устройств: `1`
  - внутренний сквад назначается при создании
- Тарифы:
  - `3 дня` бесплатно (один раз)
  - `1 месяц` — `100 ₽`
  - `3 месяца` — `300 ₽`
  - `6 месяцев` — `600 ₽`
  - `12 месяцев` — `1000 ₽`
- Оплата через YooKassa (или `mock` режим)
- Реферальная программа:
  - персональная ссылка
  - +5 дней пригласившему за первую покупку приглашенного
  - при наличии нескольких ключей пригласивший выбирает, какой продлить
- Админ-панель `/admin`:
  - доступ только для `ADMIN_IDS`
  - статистика
  - выдача бесплатных ключей по Telegram ID или username
  - рассылка сообщения (текст, фото, видео или медиа с подписью)

## Быстрый старт (Docker)

1. Скопируйте шаблон окружения:

```bash
cp .env.example .env
```

2. Заполните `.env`:
- `BOT_TOKEN`
- `ADMIN_IDS`
- `REMNAWAVE_*`
- `YOOKASSA_*` (если `PAYMENTS_PROVIDER=yookassa`)

3. Запустите:

```bash
docker compose up -d --build
```

При старте контейнера выполняются миграции:
`alembic upgrade head`.

## Локальный запуск

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python -m app.main
```

## Основные сценарии

- `/start` — главное меню
- `Подключиться` — выбор тарифа
  - для платных тарифов доступны: `Оплатить`, `Проверить оплату`, `Назад`
- `Мои подписки` — список подписок
  - `Подключиться`
  - `Продлить`
  - `Устройства`
- `Пригласить друга` — персональная реферальная ссылка
- `Тех поддержка` — открывает `@HideBroSupport`
- `/admin` — админ-панель (только для админов)

## Настройки Remnawave

Варианты авторизации:
- `REMNAWAVE_API_TOKEN`, или
- `REMNAWAVE_ADMIN_USERNAME` + `REMNAWAVE_ADMIN_PASSWORD`

Обязательно укажите корректный `REMNAWAVE_INTERNAL_SQUAD_UUID` из панели.

## Переменные окружения

Минимально необходимые:

- `BOT_TOKEN`
- `ADMIN_IDS`
- `POSTGRES_DSN`
- `REDIS_DSN`
- `REMNAWAVE_BASE_URL`
- `REMNAWAVE_INTERNAL_SQUAD_UUID`
- `PAYMENTS_PROVIDER`

Для YooKassa:

- `YOOKASSA_SHOP_ID`
- `YOOKASSA_SECRET_KEY`
- `YOOKASSA_RETURN_URL`

## Примечания

- Лимит устройств задается через `DEVICE_LIMIT` в `.env`.
- Если изменили `.env` на сервере, перезапустите контейнер:
  `docker compose up -d --build`
