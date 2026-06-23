import asyncio
import logging
from telegram import Bot
from config import BOT_TOKEN
from src.infrastructure.database import db
from src.services.order_service import OrderService
from src.services.referral_service import ReferralService

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("NetRahWorker")


async def run_payment_worker():
    logger.info(
        "⚡ NetRah Blockchain Monitoring Worker Engine has started successfully.")
    order_service = OrderService()
    referral_service = ReferralService()  # نمونه‌سازی سرویس رفرال در ورکر

    # ساخت یک کلاینت تلگرام مستقل برای ورکر جهت ارسال پیام بدون دخالت دادن پولینگ ربات
    bot = Bot(token=BOT_TOKEN)

    while True:
        try:
            # ۱. مدیریت و بستن فاکتورهای منقضی شده زمان‌گذشته
            await order_service.handle_expired_invoices()

            # ۲. واکشی فاکتورهایی که هنوز منتظر پرداخت هستند (status_id = 1)
            query_pending = """
                SELECT i.id, i.user_id, i.package_id, i.memo, i.expected_payment_amount, u.telegram_id 
                FROM invoices i
                JOIN users u ON i.user_id = u.id
                WHERE i.status_id = 1 AND i.expires_at > GETDATE()
            """
            pending_invoices = await db.execute_query_all(query_pending)

            for invoice in pending_invoices:
                memo = invoice['memo']
                invoice_id = invoice['id']
                user_id = invoice['user_id']
                package_id = invoice['package_id']
                tg_id = invoice['telegram_id']
                expected_amount = float(invoice['expected_payment_amount'])

                # استعلام وضعیت تراکنش با استفاده از کلاس پرداخت TON
                tx_status = await order_service.ton_gateway.verify_transaction(
                    memo)

                if tx_status["status"] == "PAID":
                    # بررسی اعتبارسنجی کف مبلغ واریزی (به جهت امنیت بیشتر در پرداخت کاربر)
                    if tx_status["amount_received"] >= (
                            expected_amount - 0.001):

                        # پردازش تخصیص لایسنس به صورت کاملاً امن در دیتابیس
                        delivery = await order_service.process_successful_payment(
                            invoice_id=invoice_id,
                            package_id=package_id,
                            user_id=user_id,
                            tx_hash=tx_status["tx_hash"],
                            amount_received=tx_status["amount_received"]
                        )

                        if delivery["status"] == "SUCCESS":
                            success_msg = (
                                f"🎉 **پرداخت شما تایید شد!**\n\n"
                                f"📦 فاکتور شماره `{invoice_id}` با موفقیت تسویه گردید.\n"
                                f"🔗 **لینک اتصال اختصاصی شما:**\n"
                                f"`{delivery['link']}`\n\n"
                                f"💡 این لینک را کپی کرده و در نرم‌افزار اتصال خود (مانند v2rayNG) وارد نمایید. از همراهی شما سپاسگزاریم!"
                            )
                            await bot.send_message(chat_id=tg_id,
                                                   text=success_msg,
                                                   parse_mode="Markdown")
                            logger.info(
                                f"Successfully delivered subscription to user telegram: {tg_id}")

                            # ----------------------------------------------------
                            # پردازش اهدای امتیاز دعوت در صورت خرید اول زیرمجموعه
                            # ----------------------------------------------------
                            ref_res = await referral_service.process_referral_on_purchase(
                                tg_id)
                            if ref_res and ref_res.get("inviter_telegram_id"):
                                inviter_tg = ref_res["inviter_telegram_id"]
                                try:
                                    await bot.send_message(
                                        chat_id=inviter_tg,
                                        text=f"🎉 **تبریک! یک امتیاز دعوت جدید دریافت کردید.**\n\n"
                                             f"کاربری که با لینک شما عضو شده بود، اولین خرید خود را انجام داد.\n"
                                             f"برای تبدیل امتیاز خود به کانفیگ هدیه، به منوی **👥 زیرمجموعه‌گیری و دعوت** در ربات مراجعه کنید.",
                                        parse_mode="Markdown"
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"Failed to notify inviter {inviter_tg} about reward point: {e}")

                        elif delivery["status"] == "OUT_OF_STOCK":
                            error_msg = (
                                f"⚠️ **توجه! پرداخت شما دریافت شد اما انبار خالی است**\n\n"
                                f"مبلغ واریزی شما برای فاکتور `{invoice_id}` تایید شده است اما متاسفانه موقتاً کانفیگ آماده در انبار ربات موجود نیست.\n"
                                f"مدیریت ربات مطلع شد؛ کانفیگ شما به زودی به صورت دستی ارسال خواهد شد یا وجه شما عودت داده می‌شود."
                            )
                            await bot.send_message(chat_id=tg_id,
                                                   text=error_msg,
                                                   parse_mode="Markdown")
                    else:
                        logger.warning(
                            f"Underpayment detected for invoice {invoice_id}. Expected {expected_amount}, Got {tx_status['amount_received']}")

            # استراحت ۳۰ ثانیه‌ای موتور ورکر برای جلوگیری از اسپم کردن بلاکچین و سرور دیتابیس
            await asyncio.sleep(30)

        except Exception as e:
            logger.error(f"Error in worker main loop event: {e}")
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(run_payment_worker())