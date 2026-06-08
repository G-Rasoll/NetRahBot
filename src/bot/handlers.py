import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from src.services.user_service import UserService
from src.services.package_service import PackageService
from src.services.order_service import OrderService
from src.bot.keyboards import get_packages_keyboard, get_payment_keyboard
from config import INVOICE_EXPIRY_MINUTES

logger = logging.getLogger(__name__)
user_service = UserService()
package_service = PackageService()
order_service = OrderService()


async def start_handler(update: Update,
                        context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    if not tg_user:
        return
    try:
        internal_id = await user_service.register_or_update_user(
            telegram_id=tg_user.id, username=tg_user.username,
            first_name=tg_user.first_name
        )
        if internal_id == -1:
            await update.message.reply_text(
                "❌ حساب کاربری شما در این ربات مسدود شده است.")
            return

        context.user_data['internal_db_id'] = internal_id

        reply_keyboard = [
            ["🛍️ خرید اشتراک جدید"],
            ["🎁 دریافت کانفیگ تست (رایگان)", "👤 سرویس‌های من"],
            ["📊 پشتیبانی و راهنما"]
        ]
        markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
        welcome_text = f"سلام {tg_user.first_name} عزیز! 🚀\nبه ربات فروش کانفیگ **نت‌راه** خوش آمدید."
        await update.message.reply_text(welcome_text, reply_markup=markup,
                                        parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in start_handler: {e}")
        await update.message.reply_text("⚠️ خطا در ارتباط با سرور.")


async def menu_handler(update: Update,
                       context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    مدیریت کلیک روی منوهای اصلی ربات
    """
    text = update.message.text
    user_tg_id = update.effective_user.id

    # اطمینان از وجود آیدی داخلی در وضعیت جاری Session
    internal_id = context.user_data.get('internal_db_id')
    if not internal_id:
        internal_id = await user_service.register_or_update_user(
            telegram_id=user_tg_id, username=update.effective_user.username,
            first_name=update.effective_user.first_name
        )
        context.user_data['internal_db_id'] = internal_id

    if text == "🛍️ خرید اشتراک جدید":
        try:
            # واکشی پکیج‌ها از دیتابیس
            packages = await package_service.get_active_commercial_packages()
            if not packages:
                await update.message.reply_text(
                    "😔 در حال حاضر پکیجی برای فروش تعریف نشده است.")
                return

            kb = get_packages_keyboard(packages)
            await update.message.reply_text(
                "👇 لطفاً یکی از پکیج‌های زیر را جهت خرید انتخاب کنید:",
                reply_markup=kb)
        except Exception as e:
            logger.error(f"Error showing packages to user: {e}")
            await update.message.reply_text("⚠️ خطا در لود کردن لیست پکیج‌ها.")

    elif text == "📊 پشتیبانی و راهنما":
        await  update.message.reply_text("👤 ایدی پشتیبانی جهت ارتباط:\n@NetRah_Support")

    elif text == "👤 سرویس‌های من":
        await  update.message.reply_text("صبر کن دارم می نویسمش")
    elif text == "🎁 دریافت کانفیگ تست (رایگان)":

        try:

            # فراخوانی سرویس اختصاص پکیج تست رایگان

            result = await order_service.claim_free_test_package(internal_id,
                                                                 user_tg_id)

            if result["status"] == "SUCCESS":

                success_test_text = (

                    f"🎁 **کانفیگ تست رایگان شما با موفقیت صادر شد!**\n\n"

                    f"🔗 **لینک اتصال شما:**\n"

                    f"`{result['link']}`\n\n"

                    f"⚠️ توجه داشته باشید که هر کاربر تنها یک‌بار مجاز به استفاده از تست رایگان سیستم می‌باشد."

                )

                await update.message.reply_text(success_test_text,
                                                parse_mode="Markdown")


            elif result["status"] == "ALREADY_USED":

                await update.message.reply_text(
                    "❌ شما قبلاً یک‌بار پکیج تست رایگان خود را دریافت کرده‌اید و مجاز به دریافت مجدد نیستید.")


            elif result["status"] == "OUT_OF_STOCK":

                await update.message.reply_text(
                    "😔 متاسفانه در حال حاضر کانفیگ تست در انبار پشتیبان موجود نیست. لطفا بعداً تلاش کنید یا به پشتیبانی پیام دهید.")


            elif result["status"] == "NO_TEST_PACKAGE_DEFINED":

                await update.message.reply_text(
                    "⚙️ پکیج تست توسط مدیریت تعریف نشده است.")


        except Exception as e:

            logger.error(
                f"Error handling free test package for user {user_tg_id}: {e}")

            await update.message.reply_text(
                "⚠️ خطایی در پردازش درخواست شما رخ داد.")
    else:
        await update.message.reply_text(
            "💡 لطفاً از گزینه‌های منو استفاده کنید.")


async def package_selection_callback(update: Update,
                                     context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    هندلر کلیک روی دکمه شیشه‌ای پکیج و صدور آنی فاکتور مجهز به ممو
    """
    query = update.callback_query
    await query.answer()  # حذف حالت Loading دکمه شیشه‌ای در کلاینت تلگرام

    data = query.data
    if not data or not data.startswith("buy_pkg:"):
        return

    package_id = int(data.split(":")[1])
    user_internal_id = context.user_data.get('internal_db_id')

    if not user_internal_id:
        await query.message.reply_text(
            "⚠️ جلسه کاری شما منقضی شده است. لطفا ربات را مجدداً /start کنید.")
        return

    try:
        # صدور فاکتور
        invoice_data = await order_service.create_invoice(user_internal_id,
                                                          package_id)
        if not invoice_data:
            await query.message.reply_text(
                "❌ متاسفانه این پکیج دیگر فعال نیست.")
            return

        # تولید متن رسمی و شیک فاکتور برای خریدار
        invoice_text = (
            f"🧾 **فاکتور پرداخت آنلاین صادر شد**\n\n"
            f"📦 **سرویس انتخابی:** {invoice_data['package_title']}\n"
            f"💎 **مبلغ نهایی:** `{invoice_data['expected_amount']:.6f}` TON\n"
            f"🔑 **تگ مَمو (Memo / Comment):** `{invoice_data['memo']}`\n"
            f"⏳ **مهلت پرداخت:** {INVOICE_EXPIRY_MINUTES} دقیقه\n\n"
            f"⚠️ **⚠️ هشدار امنیتی بسیار مهم:** سیستم پرداخت ربات کاملاً خودکار است. حتماً در ولت خود (مانند Tonkeeper)، در بخش **Comment** یا **Description**، عبارت مموی بالا یعنی `{invoice_data['memo']}` را دقیقاً کپی و وارد کنید. در صورت وارد نکردن ممو، واریزی شما شناسایی نخواهد شد!"
        )

        pay_kb = get_payment_keyboard(invoice_data['payment_link'])
        await query.message.reply_text(invoice_text, reply_markup=pay_kb,
                                       parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error processing invoice generation call: {e}")
        await query.message.reply_text(
            "⚠️ مشکلی در سیستم صدور فاکتور رخ داد. مجدداً تلاش فرمایید.")