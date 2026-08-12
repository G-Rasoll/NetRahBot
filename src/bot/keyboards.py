from telegram import InlineKeyboardButton, InlineKeyboardMarkup,\
    ReplyKeyboardMarkup
from typing import List, Dict, Any
import math

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


def get_payment_keyboard(pay_url: str, amount: float, wallet: str) -> InlineKeyboardMarkup:
    """
      کیبورد شیشه‌ای با ۳ دکمه درخواستی
    """
    keyboard = [
        [InlineKeyboardButton("💎 پرداخت مستقیم ولت (Direct Pay)", url=pay_url)],
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

def get_referral_keyboard() -> InlineKeyboardMarkup:

    keyboard = [
        [InlineKeyboardButton("🎁 دریافت سرویس هدیه", callback_data="claim_referral_reward")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_config_name_keyboard() -> ReplyKeyboardMarkup:

    reply_keyboard = [
        ["🎲 ایجاد نام تصادفی (Random)"],
        ["❌ لغو عملیات"]
    ]
    return ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True, one_time_keyboard=True)


import math
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_my_services_keyboard(services: list, page: int, total_count: int,
                             limit: int = 5) -> InlineKeyboardMarkup:
    """ساخت کیبورد شیشه‌ای برای لیست سرویس‌ها به همراه صفحه‌بندی"""
    keyboard = []

    for s in services:
        # تغییر: بررسی پکیج تست یا هدیه برای تنظیم آیکون
        is_free = s.get('is_test_package') or s.get('is_gift_package')
        icon = "🎁" if is_free else "🛍️"

        display_name = s.get('config_name') or s['title']
        button_text = f"{icon} {display_name}"
        callback_data = f"srv_det:{s['sub_id']}:{page}"
        keyboard.append(
            [InlineKeyboardButton(button_text, callback_data=callback_data)])

    nav_row = []
    total_pages = math.ceil(total_count / limit)

    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ قبلی",
                                            callback_data=f"srv_page:{page - 1}"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}",
                                            callback_data="ignore"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("بعدی ➡️",
                                            callback_data=f"srv_page:{page + 1}"))

    if nav_row:
        keyboard.append(nav_row)

    return InlineKeyboardMarkup(keyboard)

def get_service_detail_keyboard(sub_id: int, current_page: int, is_free_package: bool) -> InlineKeyboardMarkup:
    """
    ساخت دکمه‌های زیر جزئیات یک سرویس خاص.
    دکمه تمدید برای سرویس‌های رایگان (تست و هدیه) نمایش داده نمی‌شود.
    """
    keyboard = []
    # دکمه تمدید فقط در صورتی اضافه می‌شود که پکیج رایگان/هدیه نباشد
    if not is_free_package:
        keyboard.append([InlineKeyboardButton("🔄 تمدید سرویس", callback_data=f"srv_renew:{sub_id}")])

    keyboard.append([InlineKeyboardButton("🔙 بازگشت به لیست", callback_data=f"srv_page:{current_page}")])

    return InlineKeyboardMarkup(keyboard)


def get_invoice_keyboard(payment_url: str, invoice_id: int) -> InlineKeyboardMarkup:
    """کیبورد جدید فاکتور با دکمه اعمال تخفیف"""
    keyboard = [
        [InlineKeyboardButton("💳 پرداخت با TON", url=payment_url)],
        [InlineKeyboardButton("🎁 اعمال کد تخفیف", callback_data=f"ask_discount:{invoice_id}")],
        [InlineKeyboardButton("❌ لغو فاکتور", callback_data=f"cancel_inv:{invoice_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_discount_keyboard(invoice_id: int) -> InlineKeyboardMarkup:
    """برای دکمه انصراف از وارد کردن کد تخفیف"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به فاکتور", callback_data=f"back_to_inv:{invoice_id}")]
    ])