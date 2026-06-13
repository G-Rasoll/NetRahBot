from telegram import InlineKeyboardButton, InlineKeyboardMarkup,\
    ReplyKeyboardMarkup
from typing import List, Dict, Any


def get_packages_keyboard(
        packages: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """
        Create InlineKeyboard with pakage list
    """
    keyboard = []
    for pkg in packages:
        # frmat price
        formatted_price = f"{pkg['price_rial']:,}"
        button_text = f"🛍️ {pkg['title']} | {formatted_price} تومان"

        callback_data = f"buy_pkg:{pkg['id']}"
        keyboard.append(
            [InlineKeyboardButton(button_text, callback_data=callback_data)])

    return InlineKeyboardMarkup(keyboard)


def get_payment_keyboard(pay_url: str) -> InlineKeyboardMarkup:
    """
      create payment key for payment bt ton
    """
    keyboard = [
        [InlineKeyboardButton("💎 پرداخت مستقیم از ولت (TON)", url=pay_url)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_join_keyboard(channel_url: str) -> InlineKeyboardMarkup:

    keyboard = [
        [InlineKeyboardButton("📢 عضویت در کانال نت‌راه", url=channel_url)],
        [InlineKeyboardButton("✅ تایید عضویت", callback_data="verify_join")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_main_menu_keyboard() -> ReplyKeyboardMarkup:

    reply_keyboard = [
        ["🛍️ خرید اشتراک جدید"],
        ["🎁 دریافت کانفیگ تست (رایگان)", "👤 سرویس‌های من"],
        ["📊 پشتیبانی و راهنما"],
        ["👥 زیرمجموعه‌گیری و دعوت"]
    ]
    return ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)