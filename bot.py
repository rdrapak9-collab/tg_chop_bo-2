"""
Головний файл Telegram-бота для магазину.
Запуск: python bot.py
"""
import asyncio
import logging
import json

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, ContentType, LabeledPrice, PreCheckoutQuery

import config
import currency
import database as db
import keyboards as kb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()


# ==================== СТАНИ (FSM) ДЛЯ ОФОРМЛЕННЯ ЗАМОВЛЕННЯ ====================

class OrderStates(StatesGroup):
    waiting_phone = State()
    waiting_delivery_method = State()
    waiting_address = State()
    waiting_payment_proof = State()


class AdminAddProduct(StatesGroup):
    waiting_category = State()
    waiting_name = State()
    waiting_description = State()
    waiting_price = State()
    waiting_photo = State()


# ==================== СТАРТ / ГОЛОВНЕ МЕНЮ ====================

async def send_product_card(message: Message, product):
    """Показує картку товару (фото + опис + кнопка 'Додати в кошик').
    Використовується і з каталогу, і з deep-link кнопки в каналі."""
    text = (
        f"<b>{product['name']}</b>\n\n"
        f"{product['description']}\n\n"
        f"💰 Ціна: <b>{currency.format_price(product['price'])}</b>"
    )
    markup = kb.product_card_kb(product["id"], product["category_id"] or "all")
    if product["photo_file_id"]:
        try:
            await message.answer_photo(product["photo_file_id"], caption=text, reply_markup=markup)
            return
        except TelegramBadRequest as e:
            # Фото зіпсоване/невалідне (наприклад, file_id від іншого бота
            # чи пошкоджений запис у базі) — не валимо весь бот, а просто
            # показуємо товар без фото і лишаємо слід у логах для діагностики.
            logger.warning(f"Не вдалось показати фото товару {product['id']}: {e}")
    await message.answer(text, reply_markup=markup)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject):
    await state.clear()
    await message.answer(
        f"👋 Вітаємо у <b>{config.SHOP_NAME}</b>!\n\n"
        "Тут ви можете переглянути каталог товарів, додати їх у кошик "
        "та оформити замовлення прямо в Telegram — цілодобово.\n\n"
        "Оберіть дію в меню нижче 👇",
        reply_markup=kb.main_menu_kb(),
    )

    # ---- Обробка кнопки з каналу ----
    # Якщо клієнт натиснув кнопку в каналі виду
    # https://t.me/ВАШ_БОТ?start=buy_5 або ?start=product_5 — сюди прийде
    # параметр "buy_5" / "product_5". Приймаємо обидва варіанти назви,
    # аби не залежати від того, як саме названо параметр у кнопці.
    args = command.args
    if args and "_" in args:
        prefix, _, product_id_str = args.partition("_")
        if prefix in ("buy", "product", "order") and product_id_str.isdigit():
            product = db.get_product(int(product_id_str))
            if product:
                await message.answer("🔗 Ось товар, який ви обрали в каналі:")
                await send_product_card(message, product)
            else:
                await message.answer(
                    "На жаль, цей товар вже недоступний. Загляньте в 🛍 Каталог."
                )


@router.message(F.text == "ℹ️ Про магазин")
async def about_shop(message: Message):
    await message.answer(
        f"🏪 <b>{config.SHOP_NAME}</b>\n\n"
        "Замовлення приймаються 24/7 прямо тут, у боті.\n"
        f"Оплата — переказом на картку {config.BANK_NAME}.\n\n"
        "Якщо виникли питання — просто напишіть нам повідомлення в цьому чаті."
    )


# ==================== КАТАЛОГ ====================

async def safe_edit_to_text(callback: CallbackQuery, text: str, markup=None):
    """Показує текст+кнопки замість попереднього повідомлення.
    Telegram не дозволяє editText на повідомленні з фото (там 'caption',
    а не 'text') — тому в такому разі старе повідомлення видаляється,
    а нове надсилається окремо. Це і викликало помилку
    'there is no text in the message'."""
    message = callback.message
    try:
        if message.photo:
            await message.delete()
            await message.answer(text, reply_markup=markup)
        else:
            await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as e:
        logger.warning(f"Не вдалось відредагувати повідомлення, надсилаю нове: {e}")
        await message.answer(text, reply_markup=markup)


@router.message(F.text == "🛍 Каталог")
async def show_catalog(message: Message):
    categories = db.get_categories()
    if not categories:
        products = db.get_all_products()
        if not products:
            await message.answer("Каталог поки що порожній. Загляньте пізніше 🙂")
            return
        await message.answer(
            "Оберіть товар:", reply_markup=kb.products_list_kb(products, "all")
        )
        return
    await message.answer(
        "Оберіть категорію:", reply_markup=kb.categories_kb(categories)
    )


@router.callback_query(F.data.startswith("cat:"))
async def show_category_products(callback: CallbackQuery):
    cat_id = callback.data.split(":")[1]
    if cat_id == "all":
        products = db.get_all_products()
    else:
        products = db.get_products_by_category(int(cat_id))

    if not products:
        await callback.answer("У цій категорії поки немає товарів", show_alert=True)
        return

    await safe_edit_to_text(
        callback, "Оберіть товар:", kb.products_list_kb(products, cat_id)
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery):
    categories = db.get_categories()
    await safe_edit_to_text(
        callback, "Оберіть категорію:", kb.categories_kb(categories)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("product:"))
async def show_product_card(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    product = db.get_product(product_id)
    if not product:
        await callback.answer("Товар не знайдено", show_alert=True)
        return
    await send_product_card(callback.message, product)
    await callback.answer()


@router.callback_query(F.data.startswith("add_to_cart:"))
async def add_to_cart(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    db.add_to_cart(callback.from_user.id, product_id)
    await callback.answer("✅ Додано в кошик!", show_alert=False)


# ==================== КОШИК ====================

async def render_cart(user_id):
    items, total = db.get_cart(user_id)
    if not items:
        return "🛒 Ваш кошик порожній. Загляньте в каталог!", None

    lines = ["🛒 <b>Ваш кошик:</b>\n"]
    for it in items:
        line_total = it["qty"] * it["price"]
        lines.append(
            f"• {it['name']} — {it['qty']} x {currency.format_price(it['price'])} "
            f"= {currency.format_price(line_total)}"
        )
    lines.append(f"\n💰 <b>Разом: {currency.format_price(total)}</b>")

    # для клавіатури зручніше мапити product_id як id
    cart_kb_items = [{"id": it["id"], "name": it["name"], "qty": it["qty"]} for it in items]
    return "\n".join(lines), kb.cart_kb(cart_kb_items)


@router.message(F.text == "🛒 Кошик")
async def show_cart(message: Message):
    text, markup = await render_cart(message.from_user.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("cart_inc:"))
async def cart_increase(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    items, _ = db.get_cart(callback.from_user.id)
    current = next((i for i in items if i["id"] == product_id), None)
    qty = (current["qty"] + 1) if current else 1
    db.update_cart_qty(callback.from_user.id, product_id, qty)
    text, markup = await render_cart(callback.from_user.id)
    await safe_edit_to_text(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data.startswith("cart_dec:"))
async def cart_decrease(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    items, _ = db.get_cart(callback.from_user.id)
    current = next((i for i in items if i["id"] == product_id), None)
    qty = (current["qty"] - 1) if current else 0
    db.update_cart_qty(callback.from_user.id, product_id, qty)
    text, markup = await render_cart(callback.from_user.id)
    await safe_edit_to_text(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data.startswith("cart_del:"))
async def cart_delete(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    db.remove_from_cart(callback.from_user.id, product_id)
    text, markup = await render_cart(callback.from_user.id)
    await safe_edit_to_text(callback, text, markup)
    await callback.answer("Видалено")


# ==================== ОФОРМЛЕННЯ ЗАМОВЛЕННЯ ====================

@router.callback_query(F.data == "checkout")
async def start_checkout(callback: CallbackQuery, state: FSMContext):
    items, total = db.get_cart(callback.from_user.id)
    if not items:
        await callback.answer("Кошик порожній", show_alert=True)
        return
    await state.set_state(OrderStates.waiting_phone)
    await callback.message.answer(
        "📱 Залиште, будь ласка, ваш номер телефону для зв'язку "
        "(можна написати текстом, напр. +380671234567):"
    )
    await callback.answer()


@router.message(OrderStates.waiting_phone)
async def get_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    await state.set_state(OrderStates.waiting_delivery_method)
    await message.answer("🚚 Оберіть спосіб отримання:", reply_markup=kb.delivery_method_kb())


@router.callback_query(OrderStates.waiting_delivery_method, F.data.startswith("delivery:"))
async def get_delivery_method(callback: CallbackQuery, state: FSMContext):
    method = callback.data.split(":")[1]
    method_name = "Нова Пошта" if method == "np" else "Самовивіз"
    await state.update_data(delivery_method=method_name)

    if method == "np":
        await state.set_state(OrderStates.waiting_address)
        await callback.message.answer(
            "📍 Вкажіть, будь ласка, місто та номер відділення Нової Пошти:"
        )
    else:
        await state.update_data(delivery_address="Самовивіз")
        await show_order_summary(callback.message, callback.from_user, state)
    await callback.answer()


@router.message(OrderStates.waiting_address)
async def get_address(message: Message, state: FSMContext):
    await state.update_data(delivery_address=message.text.strip())
    await show_order_summary(message, message.from_user, state)


async def show_order_summary(message: Message, user, state: FSMContext):
    data = await state.get_data()
    items, total = db.get_cart(user.id)

    lines = ["📋 <b>Перевірте ваше замовлення:</b>\n"]
    for it in items:
        lines.append(f"• {it['name']} — {it['qty']} x {currency.format_price(it['price'])}")
    lines.append(f"\n💰 <b>Разом: {currency.format_price(total)}</b>")
    lines.append(f"\n📱 Телефон: {data.get('phone')}")
    lines.append(f"🚚 Доставка: {data.get('delivery_method')}")
    lines.append(f"📍 Адреса: {data.get('delivery_address')}")

    await message.answer("\n".join(lines), reply_markup=kb.confirm_order_kb())


@router.callback_query(F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    items, total = db.get_cart(callback.from_user.id)
    if not items:
        await callback.answer("Кошик порожній", show_alert=True)
        return

    items_payload = [
        {"name": it["name"], "price": it["price"], "qty": it["qty"]} for it in items
    ]

    order_id = db.create_order(
        user_id=callback.from_user.id,
        username=callback.from_user.username or "",
        full_name=callback.from_user.full_name,
        phone=data.get("phone"),
        delivery_method=data.get("delivery_method"),
        delivery_address=data.get("delivery_address"),
        items=items_payload,
        total=total,
    )
    db.clear_cart(callback.from_user.id)
    await state.update_data(order_id=order_id, order_total=total)

    # Показуємо тільки ті способи оплати, які реально налаштовані
    # (порожні реквізити чи відсутній токен провайдера — кнопка ховається)
    show_pl = bool(config.PL_ACCOUNT_NUMBER or config.PL_BLIK_PHONE)
    show_card = bool(config.PAYMENT_PROVIDER_TOKEN)

    await callback.message.answer(
        f"✅ Замовлення <b>№{order_id}</b> створено!\n\n"
        f"💰 До сплати: <b>{currency.format_price(total)}</b>\n\n"
        "Оберіть, будь ласка, зручний спосіб оплати:",
        reply_markup=kb.payment_method_kb(show_pl=show_pl, show_card=show_card),
    )
    await callback.answer()


@router.callback_query(F.data == "pay_method:pumb")
async def pay_method_pumb(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    total = data.get("order_total", 0)
    order_id = data.get("order_id")

    await state.set_state(OrderStates.waiting_payment_proof)
    await callback.message.edit_text(
        f"✅ Замовлення <b>№{order_id}</b>\n\n"
        f"💳 Переказьте <b>{total:.0f} грн</b> "
        f"(≈{currency.to_pln(total):.2f} zł) на картку:\n\n"
        f"<code>{config.CARD_NUMBER}</code>\n"
        f"Отримувач: {config.CARD_HOLDER} ({config.BANK_NAME})\n\n"
        "📸 Після оплати надішліть, будь ласка, скріншот або фото чеку "
        "сюди в чат — і ми одразу підтвердимо замовлення."
    )
    await callback.answer()


@router.callback_query(F.data == "pay_method:pl")
async def pay_method_pl(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    total = data.get("order_total", 0)
    order_id = data.get("order_id")
    pln_amount = currency.to_pln(total)

    lines = [
        f"✅ Замовлення <b>№{order_id}</b>\n",
        f"💳 Переказьте <b>≈{pln_amount:.2f} zł</b> ({total:.0f} грн) на реквізити:\n",
    ]
    if config.PL_ACCOUNT_NUMBER:
        lines.append(f"Номер рахунку: <code>{config.PL_ACCOUNT_NUMBER}</code>")
    if config.PL_ACCOUNT_HOLDER:
        lines.append(f"Отримувач: {config.PL_ACCOUNT_HOLDER}")
    if config.PL_BLIK_PHONE:
        lines.append(f"BLIK на номер: <code>{config.PL_BLIK_PHONE}</code>")
    lines.append(
        "\n📸 Після оплати надішліть, будь ласка, скріншот або фото "
        "підтвердження сюди в чат — і ми одразу підтвердимо замовлення."
    )

    await state.set_state(OrderStates.waiting_payment_proof)
    await callback.message.edit_text("\n".join(lines))
    await callback.answer()


@router.callback_query(F.data == "pay_method:card")
async def pay_method_card(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    total = data.get("order_total", 0)
    order_id = data.get("order_id")
    pln_amount = currency.to_pln(total)
    # Telegram Payments приймає суму в найменших одиницях валюти
    # (для злотого — це гроші, тобто 1 zł = 100 грошів)
    amount_in_groszy = max(int(round(pln_amount * 100)), 1)

    await callback.answer()
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"Замовлення №{order_id}",
        description=f"Оплата замовлення №{order_id} у {config.SHOP_NAME}",
        payload=f"order_{order_id}",
        provider_token=config.PAYMENT_PROVIDER_TOKEN,
        currency="PLN",
        prices=[LabeledPrice(label=f"Замовлення №{order_id}", amount=amount_in_groszy)],
    )
    # Стан НЕ переводимо в waiting_payment_proof — Telegram сам підтвердить
    # оплату через successful_payment, без потреби у скріншоті.


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    # Тут можна було б додатково перевірити наявність товару тощо,
    # але для простоти одразу підтверджуємо готовність прийняти оплату.
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message, state: FSMContext, bot: Bot):
    payload = message.successful_payment.invoice_payload  # напр. "order_5"
    order_id_str = payload.replace("order_", "", 1)
    if not order_id_str.isdigit():
        return
    order_id = int(order_id_str)

    db.set_order_status(order_id, "confirmed")
    order = db.get_order(order_id)
    await state.clear()

    await message.answer(
        f"🎉 Оплату замовлення №{order_id} успішно отримано! "
        "Незабаром зв'яжемось з вами щодо відправки 🚚"
    )

    items = json.loads(order["items_json"])
    items_text = "\n".join(f"• {i['name']} — {i['qty']} x {currency.format_price(i['price'])}" for i in items)
    admin_text = (
        f"🆕 <b>Нове замовлення №{order_id}</b> (оплачено карткою/Apple Pay ✅)\n\n"
        f"{items_text}\n\n"
        f"💰 Сума: <b>{currency.format_price(order['total'])}</b>\n"
        f"👤 Клієнт: {order['full_name']} (@{order['username']})\n"
        f"📱 Телефон: {order['phone']}\n"
        f"🚚 Доставка: {order['delivery_method']} — {order['delivery_address']}"
    )
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text)
        except Exception as e:
            logger.error(f"Не вдалося сповістити адміна {admin_id}: {e}")


@router.message(OrderStates.waiting_payment_proof, F.photo)
async def receive_payment_proof(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order_id = data.get("order_id")
    file_id = message.photo[-1].file_id

    db.attach_payment_proof(order_id, file_id)
    order = db.get_order(order_id)

    await message.answer(
        "🙏 Дякуємо! Скріншот отримано, очікуйте підтвердження оплати "
        "(зазвичай це займає до кількох годин). Ви отримаєте повідомлення, "
        "коли замовлення буде підтверджено."
    )
    await state.clear()

    # Сповіщаємо всіх адмінів
    items = json.loads(order["items_json"])
    items_text = "\n".join(f"• {i['name']} — {i['qty']} x {currency.format_price(i['price'])}" for i in items)
    admin_text = (
        f"🆕 <b>Нове замовлення №{order_id}</b>\n\n"
        f"{items_text}\n\n"
        f"💰 Сума: <b>{currency.format_price(order['total'])}</b>\n"
        f"👤 Клієнт: {order['full_name']} (@{order['username']})\n"
        f"📱 Телефон: {order['phone']}\n"
        f"🚚 Доставка: {order['delivery_method']} — {order['delivery_address']}\n\n"
        "Перевірте скріншот оплати нижче 👇"
    )
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id, file_id, caption=admin_text,
                reply_markup=kb.admin_order_kb(order_id),
            )
        except Exception as e:
            logger.error(f"Не вдалося сповістити адміна {admin_id}: {e}")


@router.message(OrderStates.waiting_payment_proof)
async def waiting_for_photo_reminder(message: Message):
    await message.answer("Будь ласка, надішліть саме фото/скріншот підтвердження оплати 📸")


@router.callback_query(F.data == "cancel_order")
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("❌ Оформлення замовлення скасовано.")
    await callback.answer()


# ==================== МОЇ ЗАМОВЛЕННЯ ====================

STATUS_LABELS = {
    "waiting_payment": "⏳ Очікує оплати",
    "pending_review": "🔍 Оплата на перевірці",
    "confirmed": "✅ Підтверджено, готуємо до відправки",
    "rejected": "❌ Оплату не підтверджено",
    "completed": "📦 Виконано",
}


@router.message(F.text == "📦 Мої замовлення")
async def my_orders(message: Message):
    orders = db.get_user_orders(message.from_user.id)
    if not orders:
        await message.answer("У вас ще немає замовлень.")
        return

    for order in orders[:10]:
        items = json.loads(order["items_json"])
        items_text = ", ".join(f"{i['name']} x{i['qty']}" for i in items)
        status = STATUS_LABELS.get(order["status"], order["status"])
        await message.answer(
            f"<b>Замовлення №{order['id']}</b>\n"
            f"{items_text}\n"
            f"Сума: {currency.format_price(order['total'])}\n"
            f"Статус: {status}"
        )


# ==================== АДМІН: ПІДТВЕРДЖЕННЯ ОПЛАТИ ====================

async def append_status_note(message: Message, note: str):
    """Дописує позначку статусу до повідомлення з замовленням.
    Повідомлення може бути як фото зі скріншотом оплати (тоді редагуємо
    caption), так і звичайним текстом зі списку /orders (тоді редагуємо
    text) — тому перевіряємо тип, інакше Telegram видає помилку."""
    try:
        if message.photo:
            await message.edit_caption(caption=(message.caption or "") + note)
        else:
            await message.edit_text((message.text or "") + note)
    except TelegramBadRequest as e:
        logger.warning(f"Не вдалось оновити повідомлення про замовлення: {e}")


@router.callback_query(F.data.startswith("admin_confirm:"))
async def admin_confirm_payment(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Недостатньо прав", show_alert=True)
        return

    order_id = int(callback.data.split(":")[1])
    db.set_order_status(order_id, "confirmed")
    order = db.get_order(order_id)

    await append_status_note(callback.message, "\n\n✅ <b>ОПЛАТУ ПІДТВЕРДЖЕНО</b>")
    await callback.answer("Підтверджено!")

    try:
        await bot.send_message(
            order["user_id"],
            f"✅ Оплату замовлення №{order_id} підтверджено! "
            "Незабаром зв'яжемось з вами щодо відправки 🚚"
        )
    except Exception as e:
        logger.error(f"Не вдалося сповістити клієнта: {e}")


@router.callback_query(F.data.startswith("admin_reject:"))
async def admin_reject_payment(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Недостатньо прав", show_alert=True)
        return

    order_id = int(callback.data.split(":")[1])
    db.set_order_status(order_id, "rejected")
    order = db.get_order(order_id)

    await append_status_note(callback.message, "\n\n❌ <b>ОПЛАТУ ВІДХИЛЕНО</b>")
    await callback.answer("Відхилено")

    try:
        await bot.send_message(
            order["user_id"],
            f"❌ На жаль, ми не змогли підтвердити оплату замовлення №{order_id}. "
            "Будь ласка, напишіть нам у цей чат для уточнення деталей."
        )
    except Exception as e:
        logger.error(f"Не вдалося сповістити клієнта: {e}")


# ==================== АДМІН: ДОДАВАННЯ ТОВАРІВ ====================

@router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    await message.answer(
        "🛠 <b>Адмін-панель</b>\n\n"
        "/add_product — додати новий товар\n"
        "/list_products — список товарів з ID\n"
        "/remove_product ID — прибрати товар з продажу\n"
        "/orders — переглянути замовлення, що очікують перевірки"
    )


@router.message(Command("add_product"))
async def add_product_start(message: Message, state: FSMContext):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    await state.set_state(AdminAddProduct.waiting_category)
    categories = db.get_categories()
    cat_list = ", ".join(c["name"] for c in categories) if categories else "поки немає категорій"
    await message.answer(
        f"Наявні категорії: {cat_list}\n\n"
        "Введіть назву категорії для нового товару (якщо категорії ще немає — "
        "просто введіть нову назву, вона створиться автоматично):"
    )


@router.message(AdminAddProduct.waiting_category)
async def add_product_category(message: Message, state: FSMContext):
    category_id = db.add_category(message.text.strip())
    await state.update_data(category_id=category_id)
    await state.set_state(AdminAddProduct.waiting_name)
    await message.answer("Введіть назву товару:")


@router.message(AdminAddProduct.waiting_name)
async def add_product_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminAddProduct.waiting_description)
    await message.answer("Введіть опис товару:")


@router.message(AdminAddProduct.waiting_description)
async def add_product_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(AdminAddProduct.waiting_price)
    await message.answer("Введіть ціну товару в злотих (тільки число, напр. 25.50):")


@router.message(AdminAddProduct.waiting_price)
async def add_product_price(message: Message, state: FSMContext):
    try:
        price_pln = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("Будь ласка, введіть число, напр. 25.50")
        return

    # Товар вводиться в злотих, але в базі зберігається в гривнях
    # (щоб решта логіки бота — оплата ПУМБ, кошик тощо — лишалась
    # без змін). Перерахунок відбувається за поточним курсом.
    price_uah = currency.to_uah(price_pln)
    await state.update_data(price=price_uah)
    await state.set_state(AdminAddProduct.waiting_photo)
    await message.answer(
        f"Прийнято: {price_pln:.2f} zł ≈ {price_uah:.0f} грн за поточним курсом.\n\n"
        "Надішліть фото товару (або /skip щоб пропустити):"
    )


@router.message(AdminAddProduct.waiting_photo, F.photo)
async def add_product_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photo_file_id = message.photo[-1].file_id
    product_id = db.add_product(
        name=data["name"], description=data["description"], price=data["price"],
        category_id=data["category_id"], photo_file_id=photo_file_id,
    )
    await state.clear()
    await message.answer(f"✅ Товар додано! ID: {product_id}")


@router.message(AdminAddProduct.waiting_photo, Command("skip"))
async def add_product_skip_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = db.add_product(
        name=data["name"], description=data["description"], price=data["price"],
        category_id=data["category_id"], photo_file_id=None,
    )
    await state.clear()
    await message.answer(f"✅ Товар додано (без фото)! ID: {product_id}")


@router.message(Command("list_products"))
async def list_products(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    products = db.get_all_products()
    if not products:
        await message.answer("Товарів поки немає.")
        return
    lines = [f"ID {p['id']}: {p['name']} — {currency.format_price(p['price'])}" for p in products]
    await message.answer("\n".join(lines))


@router.message(Command("remove_product"))
async def remove_product_cmd(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Використання: /remove_product ID")
        return
    db.delete_product(int(parts[1]))
    await message.answer("✅ Товар прибрано з продажу.")


@router.message(Command("orders"))
async def list_pending_orders(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    orders = db.get_orders_by_status("pending_review")
    if not orders:
        await message.answer("Немає замовлень, що очікують перевірки. ✅")
        return
    for order in orders:
        items = json.loads(order["items_json"])
        items_text = ", ".join(f"{i['name']} x{i['qty']}" for i in items)
        await message.answer(
            f"№{order['id']} | {order['full_name']} | {currency.format_price(order['total'])}\n{items_text}",
            reply_markup=kb.admin_order_kb(order["id"]),
        )


# ==================== ЗАПУСК БОТА ====================

async def main():
    db.init_db()
    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logger.info("Бот запускається...")
    await currency.refresh_rate()  # отримуємо курс гривня→злотий одразу при старті
    asyncio.create_task(currency.refresh_rate_periodically())  # і далі оновлюємо у фоні

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
