import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from src.services.user_service import UserService
from src.services.package_service import PackageService
from src.services.order_service import OrderService
from src.bot.keyboards import get_packages_keyboard, get_payment_keyboard
from config import INVOICE_EXPIRY_MINUTES
from config import INVOICE_EXPIRY_MINUTES, REQUIRED_CHANNEL, CHANNEL_LINK
from src.bot.keyboards import get_packages_keyboard, get_payment_keyboard, \
    get_join_keyboard, get_main_menu_keyboard, get_referral_keyboard
from src.services.referral_service import ReferralService

logger = logging.getLogger(__name__)
user_service = UserService()
package_service = PackageService()
order_service = OrderService()
referral_service = ReferralService()


async def start_handler(update: Update,
                        context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    if not tg_user:
        return

    # --- بخش جدید: پردازش پارامتر لینک دعوت (Deep Linking) ---
    if context.args and context.args[0].startswith("ref_"):
        raw_token = context.args[0].replace("ref_", "")
        try:
            inviter_id_str = await user_service.get_user_id_by_token(raw_token)
            inviter_internal_id = int(inviter_id_str)
            # ثبت دعوت اولیه با بررسی لایه‌های ضد تقلب دیتابیس
            await referral_service.record_pending_referral(
                inviter_internal_id, tg_user.id)
        except Exception as ex:
            logger.error(f"Error decoding referral arg: {ex}")

    if not await is_user_member(context.bot, tg_user.id):
        kb = get_join_keyboard(CHANNEL_LINK)
        await update.message.reply_text(
            "⚠️ برای استفاده از خدمات ربات نت‌راه، ابتدا باید عضو کانال ما شوید.\n"
            "پس از عضویت، روی دکمه **تایید عضویت** کلیک کنید:",
            reply_markup=kb,
            parse_mode="Markdown"
        )
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

        markup = get_main_menu_keyboard()
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

    # Force Join
    if not await is_user_member(context.bot, user_tg_id):
        kb = get_join_keyboard(CHANNEL_LINK)
        await update.message.reply_text(
            "❌ شما عضو کانال نیستید یا از آن خارج شده‌اید!\n"
            "برای دسترسی دوباره به منوی ربات، حتماً باید عضو کانال زیر باشید:",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return

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

    elif text == "👥 زیرمجموعه‌گیری و دعوت":

        try:
            stats = await referral_service.get_user_referral_stats(internal_id)
            user_token = await user_service.get_user_referral_token(internal_id)
            invite_link = f"https://t.me/NetRahBot?start=ref_{user_token}"
            msg = (
                f"👥 **سیستم زیرمجموعه‌گیری و دریافت هدیه نت‌راه**\n\n"
                f"با دعوت از دوستان خود به ربات و **اولین خرید آنها**، کانفیگ رایگان بگیرید! 🎁\n\n"
                f"🔗 **لینک دعوت اختصاصی شما:**\n"
                f"`{invite_link}`\n\n"
                f"📊 **آمار دعوت‌های شما:**\n"
                f"▫️ تعداد کل دعوت‌ها (عضو شده): `{stats['total_invites']}` نفر\n"
                f"▫️ امتیازهای فعال فعلی (خریدهای موفق): `{stats['current_points']}` امتیاز\n\n"
                f"💡 **راهنما:** به ازای **اولین خرید** هر نفری که با لینک شما وارد ربات شده، ۱ امتیاز می‌گیرید. شما می‌توانید هر زمان که مایل بودید، با کلیک روی دکمه زیر، امتیازهای خود را به کانفیگ هدیه تبدیل کنید (هر ۱ امتیاز = ۱ گیگابایت)."
            )
            await update.message.reply_text(msg, reply_markup=get_referral_keyboard(),
                                            parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error displaying referral menu: {e}")
            await update.message.reply_text("⚠️ خطایی در بارگذاری منوی دعوت رخ داد.")

    elif text == "📊 پشتیبانی و راهنما":
        await  update.message.reply_text(
            "👤 ایدی پشتیبانی جهت ارتباط:\n@NetRah_Support")

    elif text == "👤 سرویس‌های من":

        try:

            subscriptions = await user_service.get_user_subscriptions(
                internal_id)
            if not subscriptions:
                empty_text = (

                    "🤷‍♂️ **شما در حال حاضر هیچ سرویس فعالی ندارید!**\n\n"

                    "💡 برای شروع می‌توانید از منوی زیر یکی از گزینه‌های **خرید اشتراک جدید** "

                    "یا **دریافت کانفیگ تست (رایگان)** را انتخاب کنید."

                )

                await update.message.reply_text(empty_text,
                                                parse_mode="Markdown")

                return

            message_text = f"👤 **لیست سرویس‌های فعال شما ({len(subscriptions)} سرویس):**\n"
            message_text += "───────────────────\n"

            for idx, sub in enumerate(subscriptions, 1):
                pkg_type = "🎁 تست رایگان" if sub[
                    'is_test_package'] else "🛍️ اشتراک تجاری"

                date_str = sub['assigned_at'].strftime(
                    '%Y-%m-%d %H:%M') if hasattr(
                    sub['assigned_at'], 'strftime') else str(sub['assigned_at'])

                message_text += (
                    f"{idx}. 📦 **نام سرویس:** {sub['title']}\n"
                    f"نوع: {pkg_type} | حجم: {sub['volume_mb']} مگابایت\n"
                    f"📅 تاریخ دریافت: `{date_str}`\n"
                    f"🔗 **لینک اتصال اختصاصی شما:**\n"
                    f"`{sub['subscription_link']}`\n"
                    f"───────────────────\n"
                )

            await update.message.reply_text(message_text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error in menu_handler for My Services: {e}")
            await update.message.reply_text(
                "⚠️ مشکلی در واکشی سرویس‌های شما پیش آمد. لطفاً مجدداً تلاش کنید.")

    elif text == "🎁 دریافت کانفیگ تست (رایگان)":

        try:

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
    await query.answer()

    user_tg_id = update.effective_user.id
    if not await is_user_member(context.bot, user_tg_id):
        kb = get_join_keyboard(CHANNEL_LINK)
        await query.message.reply_text(
            "❌ برای خرید یا انتخاب پکیج، باید عضو کانال باشید:",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return
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
        logger.warning(
            f"[INVOICE DEBUG] "
            f"TG_ID={update.effective_user.id} "
            f"DB_ID={user_internal_id} "
            f"USERNAME={update.effective_user.username}"
        )
        invoice_data = await order_service.create_invoice(user_internal_id,
                                                          package_id)
        if not invoice_data:
            await query.message.reply_text(
                "❌ متاسفانه این پکیج دیگر فعال نیست.")
            return

        invoice_text = (
            f"🧾 **فاکتور پرداخت آنلاین صادر شد**\n\n"
            f"📦 **سرویس انتخابی:** {invoice_data['package_title']}\n"
            f"💎 **مبلغ نهایی:** `{invoice_data['expected_amount']:.6f}` TON\n"
            f"🔑 **تگ ممو (Memo / Comment):** `{invoice_data['memo']}`\n"
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


async def is_user_member(bot, telegram_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL,
                                           user_id=telegram_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(
            f"Error checking channel membership for {telegram_id}: {e}")
        return False

async def verify_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    tg_user = update.effective_user
    if not tg_user:
        await query.answer()
        return

    if await is_user_member(context.bot, tg_user.id):
        await query.answer("✅ عضویت شما با موفقیت تایید شد!", show_alert=True)

        try:
            internal_id = await user_service.register_or_update_user(
                telegram_id=tg_user.id, username=tg_user.username, first_name=tg_user.first_name
            )
            if internal_id == -1:
                await query.message.reply_text("❌ حساب کاربری شما در این ربات مسدود شده است.")
                return

            context.user_data['internal_db_id'] = internal_id

            # بررسی سیستم دعوت و ارسال پیام اطلاع‌رسانی به دعوت‌کننده (بدون تخصیص امتیاز)
            inviter_chat_id = await referral_service.verify_user_joined(tg_user.id)
            if inviter_chat_id:
                try:
                    await context.bot.send_message(
                        chat_id=inviter_chat_id,
                        text=f"👤 **یک کاربر با لینک دعوت شما عضو ربات شد!**\n\n"
                             f"⏳ به محض اینکه این کاربر **اولین خرید موفق** خود را انجام دهد، ۱ امتیاز هدیه به صورت خودکار به حساب شما منظور خواهد شد.",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify inviter about join: {e}")

            markup = get_main_menu_keyboard()
            welcome_text = f"خوش آمدید! 🚀\nمنوی ربات **نت‌راه** برای شما فعال شد."
            await query.message.reply_text(welcome_text, reply_markup=markup, parse_mode="Markdown")
            await query.message.delete()

        except Exception as e:
            logger.error(f"Error in verify_join_callback onboarding: {e}")
            await query.message.reply_text("⚠️ خطا در ارتباط با سرور.")
    else:
        await query.answer("❌ شما هنوز عضو کانال نشده‌اید. لطفاً ابتدا عضو شوید!", show_alert=True)


async def claim_reward_callback(update: Update,
                                context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_tg_id = update.effective_user.id
    if not await is_user_member(context.bot, user_tg_id):
        from src.bot.keyboards import get_join_keyboard
        kb = get_join_keyboard(CHANNEL_LINK)
        await query.message.reply_text(
            "❌ برای دریافت هدیه، باید عضو کانال باشید:",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return

    internal_id = context.user_data.get('internal_db_id')
    if not internal_id:
        await query.message.reply_text(
            "⚠️ جلسه کاری شما منقضی شده است. لطفا ربات را مجدداً /start کنید.")
        return

    loading_msg = await query.message.reply_text(
        "⏳ در حال بررسی امتیازات و ساخت کانفیگ هدیه اختصاصی شما در پنل...")

    try:
        result = await referral_service.claim_reward(internal_id, user_tg_id)

        if result["status"] == "NO_POINTS":
            await loading_msg.edit_text(
                "❌ شما در حال حاضر هیچ امتیاز فعالی برای دریافت هدیه ندارید.")

        elif result["status"] == "SUCCESS":
            success_text = (
                f"🎉 **هدیه شما با موفقیت صادر شد!**\n\n"
                f"📦 **حجم سرویس:** `{result['gb']}` گیگابایت\n"
                f"🔗 **لینک اتصال اختصاصی شما:**\n"
                f"`{result['link']}`\n\n"
                f"💡 امتیازهای شما صفر شد. این سرویس به منوی «👤 سرویس‌های من» نیز اضافه گردید. با دعوت و خرید دوستان جدید می‌توانید دوباره هدیه بگیرید."
            )
            await loading_msg.edit_text(success_text, parse_mode="Markdown")

        else:
            await loading_msg.edit_text(
                "⚠️ خطایی در ارتباط با سرور پنل یا دیتابیس رخ داد. لطفا به پشتیبانی اطلاع دهید.")

    except Exception as e:
        logger.error(f"Error in claim_reward_callback: {e}")
        await loading_msg.edit_text("⚠️ خطای سیستمی در پردازش هدیه رخ داد.")