import logging
import re
import string
import secrets
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from src.services.user_service import UserService
from src.services.package_service import PackageService
from src.services.order_service import OrderService
from config import INVOICE_EXPIRY_MINUTES, ADMIN_IDS
from config import INVOICE_EXPIRY_MINUTES, REQUIRED_CHANNEL, CHANNEL_LINK

from src.bot.keyboards import get_packages_keyboard, get_payment_keyboard, \
    get_join_keyboard, get_main_menu_keyboard, get_referral_keyboard, \
    get_admin_config_name_keyboard, get_my_services_keyboard, \
    get_service_detail_keyboard

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

    internal_id = context.user_data.get('internal_db_id')
    if not internal_id:
        internal_id = await user_service.register_or_update_user(
            telegram_id=user_tg_id, username=update.effective_user.username,
            first_name=update.effective_user.first_name
        )
        context.user_data['internal_db_id'] = internal_id

    # --- بخش مدیریت یکپارچه نام‌گذاری (برای خرید کاربر و کانفیگ دستی ادمین) ---
    if 'pending_config_name' in context.user_data:
        pending_data = context.user_data['pending_config_name']
        action_type = pending_data.get('type')

        if text == "❌ لغو عملیات":
            del context.user_data['pending_config_name']
            await update.message.reply_text("عملیات لغو شد.",
                                            reply_markup=get_main_menu_keyboard())
            return

        custom_name = None
        if text != "🎲 ایجاد نام تصادفی (Random)":
            safe_name = re.sub(r'[^a-zA-Z0-9_]', '', text.replace(" ", "_"))
            if not safe_name:
                await update.message.reply_text(
                    "⚠️ لطفاً نام را فقط با حروف انگلیسی تایپ کنید، یا دکمه تصادفی را بزنید:")
                return
            custom_name = safe_name[:20]  # محدود کردن طول نام جهت امنیت پنل
        else:
            prefix = "Rnd_" if action_type == 'admin_manual' else "Sub_"
            custom_name = prefix + ''.join(
                secrets.choice(string.ascii_letters + string.digits) for _ in
                range(5))

        # الف) پردازش نام برای کانفیگ دستی ادمین
        if action_type == 'admin_manual':
            volume_gb = pending_data['gb']
            brand_name = pending_data['brand']

            loading_msg = await update.message.reply_text(
                f"⏳ در حال ساخت کانفیگ تحت برند `{brand_name}`...")

            try:
                res = await order_service.create_manual_admin_config(
                    internal_id, user_tg_id, volume_gb, brand_name, custom_name
                )
                if res["status"] == "SUCCESS":
                    success_text = (
                        f"✅ **کانفیگ دستی با موفقیت ساخته شد!**\n\n"
                        f"🏷 **نام:** `{custom_name}`\n"
                        f"📊 **حجم:** `{volume_gb}` گیگابایت\n"
                        f"🏢 **برند:** `{brand_name}`\n"
                        f"🔑 **کد رهگیری:** `{res['memo']}`\n\n"
                        f"🔗 **لینک اتصال اختصاصی:**\n`{res['link']}`"
                    )
                    await loading_msg.edit_text(success_text,
                                                parse_mode="Markdown")
                else:
                    await loading_msg.edit_text(
                        "❌ خطایی در پنل یا دیتابیس رخ داد.")
            except Exception as e:
                logger.error(f"Error generating manual config in handler: {e}")
                await loading_msg.edit_text("⚠️ خطای غیرمنتظره در ساخت کانفیگ.")
            finally:
                if 'pending_config_name' in context.user_data:
                    del context.user_data['pending_config_name']
                await update.message.reply_text("منوی اصلی:",
                                                reply_markup=get_main_menu_keyboard())
            return

        # ب) پردازش نام برای صدور فاکتور خرید کاربر
        elif action_type == 'user_buy':
            package_id = pending_data['package_id']
            loading_msg = await update.message.reply_text(
                "⏳ در حال صدور فاکتور اختصاصی...")

            try:
                invoice_data = await order_service.create_invoice(internal_id,
                                                                  package_id,
                                                                  custom_name)
                if not invoice_data:
                    await loading_msg.edit_text(
                        "❌ متاسفانه این پکیج دیگر فعال نیست.")
                    await update.message.reply_text("عملیات لغو شد.",
                                                    reply_markup=get_main_menu_keyboard())
                    return

                from config import MY_TON_WALLET

                # طراحی پیام ضد تقلب و هشدار عدم رند کردن
                invoice_text = (
                    f"🧾 **فاکتور پرداخت آنلاین صادر شد**\n\n"
                    f"🏷 **نام سرویس:** `{custom_name}`\n"
                    f"📦 **سرویس انتخابی:** {invoice_data['package_title']}\n"
                    f"💎 **مبلغ نهایی پرداخت:** `{invoice_data['expected_amount']:.6f}`\n\n"
                    f"⚠️ **هشدار بسیار مهم (بدون ممو):**\n"
                    f"سیستم ما مبالغ را به صورت رندوم یکتا تولید می‌کند. لطفاً **به هیچ عنوان مبلغ را رند نکنید!** دقیقاً همین مبلغ بالا را پرداخت کنید، در غیر این صورت ربات تراکنش شما را شناسایی نمی‌کند و کانفیگ تحویل داده نمی‌شود.\n\n"
                    f"💼 **آدرس کیف پول ما (جهت کپی کلیک کنید):**\n"
                    f"`{MY_TON_WALLET}`\n\n"
                    f"⏳ **مهلت پرداخت:** {INVOICE_EXPIRY_MINUTES} دقیقه (پس از این زمان، این پیام حذف و فاکتور باطل می‌شود)."
                )

                pay_kb = get_payment_keyboard(invoice_data['payment_link'],
                                              invoice_data['expected_amount'],
                                              MY_TON_WALLET)

                await loading_msg.delete()
                await update.message.reply_text(
                    "✅ فاکتور شما آماده است. منوی اصلی فعال شد:",
                    reply_markup=get_main_menu_keyboard())

                # ارسال فاکتور اصلی و گرفتن message_id
                sent_msg = await update.message.reply_text(invoice_text,
                                                           reply_markup=pay_kb,
                                                           parse_mode="Markdown")

                # ذخیره chat_id و message_id در دیتابیس برای Worker
                await order_service.update_invoice_message_data(
                    invoice_id=invoice_data['invoice_id'],
                    chat_id=sent_msg.chat_id,
                    message_id=sent_msg.message_id
                )

            except Exception as e:
                logger.error(f"Error processing invoice generation call: {e}")
                await loading_msg.delete()
                await update.message.reply_text(
                    "⚠️ مشکلی در سیستم صدور فاکتور رخ داد. مجدداً تلاش فرمایید.",
                    reply_markup=get_main_menu_keyboard())
            finally:
                if 'pending_config_name' in context.user_data:
                    del context.user_data['pending_config_name']
            return
    # ------------------------------------------------
    # --- بررسی درخواست جدید ساخت کانفیگ توسط ادمین ---
    is_numeric = False
    volume_gb = 0.0
    try:
        volume_gb = float(text)
        if volume_gb > 0:
            is_numeric = True
    except ValueError:
        pass

    if is_numeric:
        admin_info = await user_service.get_admin_info(internal_id)
        if admin_info:
            brand_name = admin_info['brand_name']

            # ثبت وضعیت یکپارچه نام‌گذاری برای ادمین
            context.user_data['pending_config_name'] = {'type': 'admin_manual',
                                                        'gb': volume_gb,
                                                        'brand': brand_name}

            await update.message.reply_text(
                f"🛠️ شما درخواست ساخت کانفیگ `{volume_gb}` گیگابایتی برای برند **{brand_name}** را داده‌اید.\n\n"
                f"لطفاً یک نام دلخواه (حتماً به زبان انگلیسی) برای این کانفیگ تایپ کنید تا در نام کانفیگ قرار بگیرد، یا دکمه تصادفی را بزنید:",
                reply_markup=get_admin_config_name_keyboard(),
                parse_mode="Markdown"
            )
            return
    # ------------------------------------------------

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
            await update.message.reply_text(msg,
                                            reply_markup=get_referral_keyboard(),
                                            parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error displaying referral menu: {e}")
            await update.message.reply_text(
                "⚠️ خطایی در بارگذاری منوی دعوت رخ داد.")

    elif text == "📊 پشتیبانی و راهنما":
        await  update.message.reply_text(
            "👤 ایدی پشتیبانی جهت ارتباط:\n@NetRah_Support")

    elif text == "👤 سرویس‌های من":

        try:
            total_count = await user_service.get_user_subscriptions_count(
                internal_id)
            if total_count == 0:
                empty_text = (

                    "🤷‍♂️ **شما در حال حاضر هیچ سرویس فعالی ندارید!**\n\n"

                    "💡 برای شروع می‌توانید از منوی زیر یکی از گزینه‌های **خرید اشتراک جدید** "

                    "یا **دریافت کانفیگ تست (رایگان)** را انتخاب کنید."

                )
                await update.message.reply_text(empty_text,
                                                parse_mode="Markdown")
                return
            page = 0
            limit = 5
            services = await user_service.get_user_subscriptions_paginated(
                internal_id,
                limit=limit,
                offset=0)
            msg_text = (
                f"👤 **لیست سرویس‌های فعال شما**\n"
                f"📊 تعداد کل سرویس‌ها: `{total_count}` عدد\n\n"
                f"👇 برای مشاهده مشخصات دقیق، روی سرویس مورد نظر کلیک کنید:"
            )
            kb = get_my_services_keyboard(services, page, total_count, limit)
            await update.message.reply_text(msg_text, reply_markup=kb,
                                            parse_mode="Markdown")
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
    هندلر کلیک روی دکمه شیشه‌ای پکیج و ثبت State برای دریافت نام
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

    # به جای صدور آنی فاکتور، وضعیت کاربر را به حالت "دریافت نام کانفیگ" تغییر می‌دهیم
    context.user_data['pending_config_name'] = {'type': 'user_buy',
                                                'package_id': package_id}

    await query.message.reply_text(
        "📝 **انتخاب نام برای سرویس**\n\n"
        "لطفاً یک نام دلخواه (فقط با حروف انگلیسی) برای این سرویس تایپ کنید تا در لیست سرویس‌های شما با این نام متمایز شود.\n"
        "یا دکمه تصادفی را بزنید:",
        reply_markup=get_admin_config_name_keyboard(),
        parse_mode="Markdown"
    )


async def is_user_member(bot, telegram_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL,
                                           user_id=telegram_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(
            f"Error checking channel membership for {telegram_id}: {e}")
        return False


async def verify_join_callback(update: Update,
                               context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    tg_user = update.effective_user
    if not tg_user:
        await query.answer()
        return

    if await is_user_member(context.bot, tg_user.id):
        await query.answer("✅ عضویت شما با موفقیت تایید شد!", show_alert=True)

        try:
            internal_id = await user_service.register_or_update_user(
                telegram_id=tg_user.id, username=tg_user.username,
                first_name=tg_user.first_name
            )
            if internal_id == -1:
                await query.message.reply_text(
                    "❌ حساب کاربری شما در این ربات مسدود شده است.")
                return

            context.user_data['internal_db_id'] = internal_id

            # بررسی سیستم دعوت و ارسال پیام اطلاع‌رسانی به دعوت‌کننده (بدون تخصیص امتیاز)
            inviter_chat_id = await referral_service.verify_user_joined(
                tg_user.id)
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
            await query.message.reply_text(welcome_text, reply_markup=markup,
                                           parse_mode="Markdown")
            await query.message.delete()

        except Exception as e:
            logger.error(f"Error in verify_join_callback onboarding: {e}")
            await query.message.reply_text("⚠️ خطا در ارتباط با سرور.")
    else:
        await query.answer(
            "❌ شما هنوز عضو کانال نشده‌اید. لطفاً ابتدا عضو شوید!",
            show_alert=True)


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


async def my_services_callback_handler(update: Update,
                                       context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    هندلر مدیریت کلیک‌ها در بخش سرویس‌های من (صفحه‌بندی، نمایش جزئیات و بازگشت)
    """
    query = update.callback_query
    internal_id = context.user_data.get('internal_db_id')

    if not internal_id:
        await query.answer(
            "⚠️ نشست کاری شما منقضی شده است. لطفا ربات را /start کنید.",
            show_alert=True)
        return

    data = query.data

    if data == "ignore":
        await query.answer()
        return

    limit = 5

    try:
        # مدیریت کلیک روی تغییر صفحه یا بازگشت به لیست
        if data.startswith("srv_page:"):
            page = int(data.split(":")[1])
            total_count = await user_service.get_user_subscriptions_count(
                internal_id)
            offset = page * limit
            services = await user_service.get_user_subscriptions_paginated(
                internal_id, limit, offset)

            msg_text = (
                f"👤 **لیست سرویس‌های فعال شما**\n"
                f"📊 تعداد کل سرویس‌ها: `{total_count}` عدد\n\n"
                f"👇 برای مشاهده مشخصات دقیق، روی سرویس مورد نظر کلیک کنید:"
            )
            kb = get_my_services_keyboard(services, page, total_count, limit)

            await query.edit_message_text(msg_text, reply_markup=kb,
                                          parse_mode="Markdown")
            await query.answer()

        # مدیریت کلیک روی نمایش جزئیات یک سرویس
        elif data.startswith("srv_det:"):
            parts = data.split(":")
            sub_id = int(parts[1])
            current_page = int(parts[2])

            sub = await user_service.get_user_subscription_detail(internal_id,
                                                                  sub_id)
            if not sub:
                await query.answer("❌ این سرویس یافت نشد یا حذف شده است.",
                                   show_alert=True)
                return

            # --- تغییر: بررسی تست یا هدیه بودن پکیج ---
            is_free_service = sub.get('is_test_package') or sub.get(
                'is_gift_package')
            pkg_type = "🎁 تست رایگان/هدیه" if is_free_service else "🛍️ اشتراک تجاری"

            date_str = sub['assigned_at'].strftime('%Y-%m-%d %H:%M') if hasattr(
                sub['assigned_at'], 'strftime') else str(sub['assigned_at'])

            config_name = sub.get('config_name') or "بدون نام"

            vol_gb = float(sub.get('volume_gb') or 0)
            vol_mb = int(sub.get('volume_mb') or 0)

            if vol_mb > 0:
                if vol_mb >= 1024 and vol_mb % 1024 == 0:
                    volume_display = f"{vol_mb // 1024} گیگابایت"
                elif vol_mb > 1024:
                    volume_display = f"{vol_mb / 1024:g} گیگابایت"
                else:
                    volume_display = f"{vol_mb} مگابایت"
            elif vol_gb > 0:
                volume_display = f"{vol_gb:g} گیگابایت"
            else:
                volume_display = "نامحدود / نامشخص"

            message_text = (
                f"📦 **جزئیات سرویس شما**\n"
                f"───────────────────\n"
                f"🏷 **نام سرویس:** `{config_name}`\n"
                f"🔹 **پکیج اصلی:** {sub['title']}\n"
                f"🔹 **نوع سرویس:** {pkg_type}\n"
                f"🔹 **حجم اختصاصی:** `{volume_display}`\n"
                f"📅 **تاریخ دریافت:** `{date_str}`\n\n"
                f"🔗 **لینک اتصال شما (جهت کپی کلیک کنید):**\n"
                f"`{sub['subscription_link']}`\n"
                f"───────────────────"
            )

            # --- ارسال flag به تابع کیبورد ---
            kb = get_service_detail_keyboard(sub_id, current_page,
                                             is_free_package=is_free_service)

            await query.edit_message_text(message_text, reply_markup=kb,
                                          parse_mode="Markdown")
            await query.answer()

        # دکمه تمدید سرویس
        elif data.startswith("srv_renew:"):
            sub_id = int(data.split(":")[1])
            await query.answer("⏳ بخش تمدید سرویس‌ها به زودی فعال می‌شود!",
                               show_alert=True)

    except Exception as e:
        logger.error(f"Error in my_services callback logic: {e}")
        await query.answer("⚠️ خطای سیستمی رخ داد. لطفا مجدداً تلاش کنید.",
                           show_alert=True)