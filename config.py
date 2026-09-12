"""
Конфігурація бота.
Всі секретні дані беруться зі змінних середовища (.env файл),
щоб не зберігати токен та інші дані прямо в коді.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота, отриманий від @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Telegram ID адміністратора (власника магазину) - саме сюди прийдуть сповіщення
# Дізнатись свій ID можна написавши боту @userinfobot
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Реквізити для оплати
CARD_NUMBER = os.getenv("CARD_NUMBER", "0000 0000 0000 0000")
CARD_HOLDER = os.getenv("CARD_HOLDER", "Ім'я Прізвище")
BANK_NAME = os.getenv("BANK_NAME", "ПУМБ")

# Польські реквізити (для клієнтів, яким зручніше платити в злотих)
PL_ACCOUNT_NUMBER = os.getenv("PL_ACCOUNT_NUMBER", "")
PL_ACCOUNT_HOLDER = os.getenv("PL_ACCOUNT_HOLDER", "")
PL_BLIK_PHONE = os.getenv("PL_BLIK_PHONE", "")

# Токен платіжного провайдера для оплати карткою/Apple Pay/Google Pay
# прямо в Telegram (наприклад, Stripe). Без нього ця кнопка просто не
# показуватиметься клієнтам. Отримати можна через @BotFather:
# /mybots → ваш бот → Payments → підключити провайдера.
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")

# Назва магазину, яка буде показуватись у боті
SHOP_NAME = os.getenv("SHOP_NAME", "Мій Магазин")

# Запасний курс гривня→злотий (скільки злотих коштує 1 грн), якщо
# API Нацбанку України раптом недоступне. Бот сам підтягує актуальний
# курс автоматично, це значення використовується лише як резерв.
# Наприклад, якщо 1 zł ≈ 12.04 грн, то тут: 1 / 12.04 ≈ 0.083
FALLBACK_RATE_PLN_PER_UAH = float(os.getenv("FALLBACK_RATE_PLN_PER_UAH", "0.083"))

# Шлях до бази даних
DB_PATH = os.getenv("DB_PATH", "shop.db")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не знайдено! Створіть файл .env на основі .env.example "
        "і вкажіть токен, отриманий від @BotFather."
    )

if not ADMIN_IDS:
    raise RuntimeError(
        "ADMIN_IDS не знайдено! Вкажіть свій Telegram ID у файлі .env "
        "(дізнатись його можна написавши боту @userinfobot)."
    )
