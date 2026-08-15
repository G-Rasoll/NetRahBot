import asyncio
import logging
from telegram import Bot
from src.infrastructure.database import db
from src.infrastructure.payments.ton_payment import TonPayment
from src.services.order_service import OrderService
from src.bot.notifier import send_config_with_qr
from config import BOT_TOKEN, MY_TON_WALLET

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
ton_gateway = TonPayment(wallet_address=MY_TON_WALLET)
order_service = OrderService()


async def check_payments_and_expire():
    while True:
        try:
            # ۱. ابطال فاکتورهای منقضی شده و حذف پیام تلگرام
            query_expired = "SELECT id, chat_id, message_id FROM invoices WHERE status_id = 1 AND expires_at < GETDATE()"
            expired_invoices = await db.execute_query_all(query_expired)

            for inv in expired_invoices:
                # حذف پیام از تلگرام
                if inv['chat_id'] and inv['message_id']:
                    try:
                        await bot.delete_message(chat_id=inv['chat_id'],
                                                 message_id=inv['message_id'])
                        logger.info(
                            f"Deleted expired invoice message {inv['message_id']} for chat {inv['chat_id']}")
                    except Exception as e:
                        logger.warning(
                            f"Could not delete message (maybe already deleted by user): {e}")

                # تغییر استتوس در دیتابیس
                await db.execute_non_query(
                    "UPDATE invoices SET status_id = 4 WHERE id = ?",
                    (inv['id'],))
                logger.info(f"Invoice {inv['id']} marked as EXPIRED (4).")

            # ۲. بررسی فاکتورهای باز (PENDING)
            query_pending = "SELECT id, user_id, package_id, expected_payment_amount, chat_id FROM invoices WHERE status_id = 1"
            pending_invoices = await db.execute_query_all(query_pending)

            for inv in pending_invoices:
                amount = float(inv['expected_payment_amount'])

                # بررسی تراکنش در شبکه با دقت مبلغ
                tx_data = await ton_gateway.verify_transaction(
                    expected_amount=amount)

                if tx_data["status"] == "PAID":
                    logger.info(
                        f"Payment detected for invoice {inv['id']}. Processing...")
                    result = await order_service.process_successful_payment(
                        invoice_id=inv['id'],
                        package_id=inv['package_id'],
                        user_id=inv['user_id'],
                        tx_hash=tx_data['tx_hash'],
                        amount_received=tx_data['amount_received'],
                        tx_time=tx_data['tx_time']
                    )

                    if result["status"] == "LATE_PAYMENT" and inv['chat_id']:
                        await bot.send_message(
                            chat_id=inv['chat_id'],
                            text="⚠️ شما مبلغ را **پس از گذشت زمان انقضا** پرداخت کردید! تحویل کانفیگ متوقف شد. لطفاً جهت پیگیری وجه به پشتیبانی پیام دهید."
                        )
                    elif result["status"] == "SUCCESS" and inv['chat_id']:
                        success_text = (
                            f"✅ پرداخت شما با موفقیت تایید شد!\n"
                            f"🔗 لینک اتصال شما:\n`{result['link']}`"
                        )
                        # تحویل کانفیگ همراه با QR Code لینک ساب (ساخت لوکال، بدون API ثالث)
                        await send_config_with_qr(
                            bot, inv['chat_id'], result['link'], success_text
                        )
                    elif result["status"] == "OUT_OF_STOCK" and inv['chat_id']:
                        await bot.send_message(
                            chat_id=inv['chat_id'],
                            text="✅ پرداخت تایید شد اما متاسفانه موجودی سرور موقتاً تمام شده است. مدیران به زودی سرویس شما را دستی تحویل می‌دهند."
                        )

        except Exception as e:
            logger.error(f"Error in Worker loop: {e}")

        # استراحت 30 ثانیه‌ای ورکر تا درخواست بعدی به API ها
        await asyncio.sleep(30)


if __name__ == "__main__":
    logger.info("🚀 Starting Background Worker (Payment Monitor & Cleanup)...")
    asyncio.run(check_payments_and_expire())
