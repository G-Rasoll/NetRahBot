import logging
import asyncio
from telegram import Bot
from config import ADMIN_IDS, BOT_TOKEN
from src.infrastructure.panel_api import panel_api
from src.utils.helpers import format_bytes
logger = logging.getLogger(__name__)


async def notify_admins_if_panel_full(bot: Bot = None) -> None:
    """
    بررسی میزان حجم اختصاص‌یافته پنل و ارسال هشدار به ادمین‌ها در صورت تکمیل ظرفیت.
    استفاده از تابع موجود format_bytes بدون دوباره‌نویسی کد.
    """
    try:
        # ۱. دریافت آمار کلی پنل با استفاده از تابع موجود در panel_api
        stats = await panel_api.get_panel_stats()

        total_assigned = stats.get("total_assigned", 0)
        total_panel_traffic = stats.get("total_panel_traffic")

        # ۲. بررسی شرط: حجم اختصاص‌یافته مساوی یا بیشتر از حجم کل پنل شده باشد
        if total_panel_traffic is not None and total_panel_traffic > 0 and total_assigned >= total_panel_traffic:
            assigned_str = format_bytes(total_assigned)
            total_str = format_bytes(total_panel_traffic)

            message = (
                f"⚠️ **هشدار تکمیل ظرفیت پنل!**\n\n"
                f"حجم اختصاص داده‌شده به کاربران به سقف حجم کل پنل رسیده است.\n\n"
                f"▫️ **حجم کل پنل:** `{total_str}`\n"
                f"▫️ **مجموع حجم اختصاص‌یافته:** `{assigned_str}`\n\n"
                f"🚨 **لطفاً جهت جلوگیری از اختلال در صدور کانفیگ جدید، حجم کل پنل را آپدیت کنید.**"
            )

            # استفاده از نمونه بوت پاس داده شده یا ایجاد نمونه موقت برای ورکر
            telegram_bot = bot if bot else Bot(token=BOT_TOKEN)

            for admin_id in ADMIN_IDS:
                try:
                    await telegram_bot.send_message(
                        chat_id=admin_id,
                        text=message,
                        parse_mode="Markdown"
                    )
                except Exception as send_err:
                    logger.error(f"Failed to send panel capacity warning to admin {admin_id}: {send_err}")

    except Exception as e:
        logger.error(f"Error in notify_admins_if_panel_full: {e}")


def trigger_panel_capacity_check(bot: Bot = None) -> None:
    """
    فراخوانی غیرهمزمان (Background Task) جهت رعایت همزمانی.
    این تابع روند اصلی ورکر یا ثبت دیتابیس را متوقف نمی‌کند.
    """
    asyncio.create_task(notify_admins_if_panel_full(bot=bot))