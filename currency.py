"""
Курс валют: гривня → злотий.
Курс автоматично підтягується з офіційного API Національного банку
України (НБУ) — це безкоштовне джерело, що не вимагає реєстрації чи
ключа доступу, і саме той курс, який фактично використовують банки
в Україні. Якщо API тимчасово недоступне (немає інтернету, збій
сервісу тощо), бот використовує запасний курс з .env, аби не
зупиняти показ цін.
"""
import asyncio
import logging
import ssl

import aiohttp
import certifi

from config import FALLBACK_RATE_PLN_PER_UAH

logger = logging.getLogger(__name__)

# НБУ віддає курс у форматі "скільки гривень коштує 1 злотий"
NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=PLN&json"
REFRESH_INTERVAL_SECONDS = 6 * 60 * 60  # оновлювати курс раз на 6 годин

_current_rate = FALLBACK_RATE_PLN_PER_UAH  # скільки злотих коштує 1 гривня

# На деяких системах Windows Python не знаходить актуальний набір
# кореневих сертифікатів, через що HTTPS-запити падають з
# SSLCertVerificationError. Явно вказуємо перевірений набір
# сертифікатів з пакету certifi, щоб це не залежало від системи.
_ssl_context = ssl.create_default_context(cafile=certifi.where())


async def refresh_rate():
    """Питає в НБУ актуальний курс злотого і оновлює кеш.
    Якщо щось пішло не так — просто лишає попереднє значення."""
    global _current_rate
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(NBU_URL, ssl=_ssl_context) as response:
                data = await response.json()
                # НБУ повертає, скільки ГРИВЕНЬ коштує 1 ЗЛОТИЙ —
                # нам потрібне обернене значення (скільки злотих
                # коштує 1 гривня), тому ділимо 1 на цей курс.
                uah_per_pln = float(data[0]["rate"])
                _current_rate = 1 / uah_per_pln
                logger.info(
                    f"Курс валют оновлено (НБУ): 1 PLN = {uah_per_pln:.4f} UAH "
                    f"→ 1 UAH = {_current_rate:.4f} PLN"
                )
    except Exception as e:
        logger.warning(
            f"Не вдалося оновити курс валют, використовую попередній "
            f"({_current_rate:.4f}): {e}"
        )


async def refresh_rate_periodically():
    """Фонове завдання: оновлює курс раз на кілька годин, поки бот працює."""
    while True:
        await refresh_rate()
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)


def to_pln(uah_amount: float) -> float:
    return uah_amount * _current_rate


def to_uah(pln_amount: float) -> float:
    """Скільки гривень коштує вказана сума в злотих (за поточним курсом)."""
    if _current_rate == 0:
        return 0.0
    return pln_amount / _current_rate


def format_price(uah_amount: float) -> str:
    """Повертає рядок виду '14.25 zł (≈150 грн)' — спочатку злоті,
    потім гривня, перерахована за поточним курсом."""
    pln_amount = to_pln(uah_amount)
    return f"{pln_amount:.2f} zł (≈{uah_amount:.0f} грн)"
