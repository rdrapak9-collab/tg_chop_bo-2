"""
Усі клавіатури (кнопки) бота зібрані в одному місці для зручності.
"""
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛍 Каталог"), KeyboardButton(text="🛒 Кошик")],
            [KeyboardButton(text="📦 Мої замовлення"), KeyboardButton(text="ℹ️ Про магазин")],
        ],
        resize_keyboard=True,
    )
    return kb


def categories_kb(categories):
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat["name"], callback_data=f"cat:{cat['id']}")
    builder.button(text="🔎 Всі товари", callback_data="cat:all")
    builder.adjust(2)
    return builder.as_markup()


def products_list_kb(products, category_id):
    builder = InlineKeyboardBuilder()
    for p in products:
        builder.button(
            text=f"{p['name']} — {p['price']:.0f} грн",
            callback_data=f"product:{p['id']}",
        )
    builder.button(text="⬅️ До категорій", callback_data="back_to_categories")
    builder.adjust(1)
    return builder.as_markup()


def product_card_kb(product_id, category_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Додати в кошик", callback_data=f"add_to_cart:{product_id}")
    builder.button(text="⬅️ Назад", callback_data=f"cat:{category_id}")
    builder.adjust(1)
    return builder.as_markup()


def cart_kb(cart_items):
    builder = InlineKeyboardBuilder()
    for item in cart_items:
        builder.button(
            text=f"➖ {item['name']} ({item['qty']})",
            callback_data=f"cart_dec:{item['id']}",
        )
        builder.button(
            text="🗑",
            callback_data=f"cart_del:{item['id']}",
        )
        builder.button(
            text=f"➕",
            callback_data=f"cart_inc:{item['id']}",
        )
    builder.adjust(3)
    if cart_items:
        builder.row(InlineKeyboardButton(text="✅ Оформити замовлення", callback_data="checkout"))
    return builder.as_markup()


def delivery_method_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🚚 Нова Пошта", callback_data="delivery:np")
    builder.button(text="🏠 Самовивіз", callback_data="delivery:pickup")
    builder.adjust(1)
    return builder.as_markup()


def payment_method_kb(show_pl: bool, show_card: bool):
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Картка ПУМБ (грн)", callback_data="pay_method:pumb")
    if show_pl:
        builder.button(text="🇵🇱 Польський переказ/BLIK (zł)", callback_data="pay_method:pl")
    if show_card:
        builder.button(text="🍏 Apple Pay / Картка онлайн", callback_data="pay_method:card")
    builder.adjust(1)
    return builder.as_markup()


def confirm_order_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Підтвердити замовлення", callback_data="confirm_order")
    builder.button(text="❌ Скасувати", callback_data="cancel_order")
    builder.adjust(1)
    return builder.as_markup()


def admin_order_kb(order_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Підтвердити оплату", callback_data=f"admin_confirm:{order_id}")
    builder.button(text="❌ Відхилити", callback_data=f"admin_reject:{order_id}")
    builder.adjust(1)
    return builder.as_markup()
