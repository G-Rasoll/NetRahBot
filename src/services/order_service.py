import logging
import secrets
from datetime import datetime, timedelta
from src.infrastructure.database import db
from src.infrastructure.payments.ton_payment import TonPayment
from src.services.package_service import PackageService
from config import MY_TON_WALLET, INVOICE_EXPIRY_MINUTES
from typing import Optional, Dict, Any
import  aiohttp
logger = logging.getLogger(__name__)


class OrderService:
    def __init__(self):
        self.package_service = PackageService()
        self.ton_gateway = TonPayment(wallet_address=MY_TON_WALLET)



    async def _get_current_ton_rate(self) -> float:

        async with aiohttp.ClientSession() as session:
            # قیمت تتر به تومان
            async with session.get(
                    "https://api.tetherland.com/currencies"
            ) as response:
                usdt_data = await response.json()

            usdt_price = float(
                usdt_data["data"]["currencies"]["USDT"]["price"]
            )

            async with session.get(
                    "https://api.binance.com/api/v3/ticker/24hr?symbol=TONUSDT"
            ) as response:
                ton_data = await response.json()

            ton_price_usdt = float(ton_data["lastPrice"])
            ton_price_toman = ton_price_usdt * usdt_price

            return ton_price_toman

    def _generate_unique_memo(self) -> str:

        random_num = secrets.randbelow(900000) + 100000
        return f"NR-{random_num}"

    async def create_invoice(self, user_internal_id: int, package_id: int) -> \
    Optional[Dict[str, Any]]:

        try:
            package = await self.package_service.get_package_by_id(package_id)
            if not package or not package['is_active']:
                logger.warning(
                    f"Package ID {package_id} is not available for purchase.")
                return None

            memo = self._generate_unique_memo()

            ton_rate = await self._get_current_ton_rate()
            if ton_rate <= 0:
                raise ValueError(
                    "Calculated TON exchange rate must be greater than zero.")

            expected_amount = float(package['price_rial']) / ton_rate

            expires_at = datetime.now() + timedelta(
                minutes=INVOICE_EXPIRY_MINUTES)

            query = """
                INSERT INTO invoices (
                    user_id, package_id, memo, status_id, 
                    package_title_snapshot, package_price_snapshot_rial, package_volume_snapshot_mb, 
                    payment_currency_code, expected_payment_amount, amount_received, expires_at
                ) 
                VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, 0.0, ?)
            """
            params = (
                user_internal_id,
                package['id'],
                memo,
                package['title'],
                package['price_rial'],
                package['volume_mb'],
                "TON",
                expected_amount,
                expires_at
            )

            invoice_id = await db.execute_non_query(query, params)

            payment_url = self.ton_gateway.create_invoice_link(
                amount=expected_amount,
                memo=memo,
                expires_in_minutes=INVOICE_EXPIRY_MINUTES
            )

            return {
                "invoice_id": invoice_id,
                "memo": memo,
                "expected_amount": expected_amount,
                "payment_link": payment_url,
                "expires_at": expires_at,
                "package_title": package['title']
            }

        except Exception as e:
            logger.error(
                f"Error in creating invoice for user {user_internal_id}: {e}")
            raise e

    async def process_successful_payment(self, invoice_id: int, package_id: int,
                                         user_id: int, tx_hash: str,
                                         amount_received: float) -> Dict[
        str, Any]:
        """
        پردازش اتمیک و فوق سریع فاکتورهای پرداخت شده همراه با ساختار ضد نشت تراکنش (Anti-Leak)
        """
        # ابتدا وضعیت فاکتور را به PAID تغییر می‌دهیم
        query_update_invoice = """
            UPDATE invoices 
            SET status_id = 2, tx_hash = ?, amount_received = ? 
            WHERE id = ? AND status_id = 1
        """
        await db.execute_non_query(query_update_invoice,
                                   (tx_hash, amount_received, invoice_id))

        # ساختار اتمیک با سرعت بالا و لاک بهینه
        transaction_query = """
        BEGIN TRY
            BEGIN TRANSACTION;

            -- تعریف یک جدول متغیر موقت برای صید آنی رکورد انبار
            DECLARE @UpdatedInventory TABLE (id INT, subscription_link NVARCHAR(MAX));

            -- آپدیت اتمیک: انتخاب، قفل و خروج داده در یک دستور واحد
            UPDATE TOP (1) subscription_inventory
            SET is_assigned = 1
            OUTPUT INSERTED.id, INSERTED.subscription_link INTO @UpdatedInventory
            WHERE package_id = ? AND is_assigned = 0;

            -- بررسی اینکه آیا کانفیگی صید شد یا خیر
            IF EXISTS (SELECT 1 FROM @UpdatedInventory)
            BEGIN
                DECLARE @SelectedInventoryId INT;
                DECLARE @SubLink NVARCHAR(MAX);

                SELECT @SelectedInventoryId = id, @SubLink = subscription_link FROM @UpdatedInventory;

                -- ثبت در جدول اشتراک‌های کاربر
                INSERT INTO user_subscriptions (user_id, inventory_id, invoice_id, assigned_at)
                VALUES (?, @SelectedInventoryId, ?, GETDATE());

                -- تکمیل نهایی فاکتور به وضعیت COMPLETED (آیدی 3)
                UPDATE invoices SET status_id = 3 WHERE id = ?;

                COMMIT TRANSACTION;
                SELECT 1 AS success, @SubLink AS link;
            END
            ELSE
            BEGIN
                -- انبار خالی است؛ رول‌بک ملایم برای حفظ وضعیت فاکتور در حالت PAID جهت بررسی ادمین
                ROLLBACK TRANSACTION;
                SELECT 0 AS success, NULL AS link;
            END
        END TRY
        BEGIN CATCH
            IF @@TRANCOUNT > 0
                ROLLBACK TRANSACTION;
            THROW; -- پرتاب خطا به سمت پایتون جهت آگاهی لاگر
        END CATCH
        """

        result = await db.execute_query_single(transaction_query, (
        package_id, user_id, invoice_id, invoice_id))

        if result and result['success'] == 1:
            return {"status": "SUCCESS", "link": result['link']}
        else:
            logger.critical(
                f"⚠️ OUT OF STOCK ALERT: Invoice {invoice_id} is paid but subscription inventory is empty!")
            return {"status": "OUT_OF_STOCK", "link": None}

    async def claim_free_test_package(self, user_internal_id: int,
                                      telegram_id: int) -> Dict[str, Any]:
        """
        منطق دریافت اتمیک پکیج تست رایگان با امنیت ۱۰۰٪ در برابر مسابقه همزمانی کاربران
        """
        try:
            # ۱. بررسی وضعیت استفاده قبلی کاربر
            check_user_query = "SELECT has_used_test_package FROM users WHERE id = ?"
            user_status = await db.execute_query_single(check_user_query,
                                                        (user_internal_id,))

            if not user_status or user_status['has_used_test_package']:
                return {"status": "ALREADY_USED", "link": None}

            # ۲. پیدا کردن آیدی پکیج تست فعال
            pkg_query = "SELECT id FROM packages WHERE is_test_package = 1 AND is_active = 1"
            test_pkg = await db.execute_query_single(pkg_query)
            if not test_pkg:
                return {"status": "NO_TEST_PACKAGE_DEFINED", "link": None}

            # ۳. کوئری ترنزاکشنال اتمیک بدون ریسک قفل‌شدگی دیتابیس
            test_transaction = """
            BEGIN TRY
                BEGIN TRANSACTION;

                DECLARE @UpdatedInventory TABLE (id INT, subscription_link NVARCHAR(MAX));

                -- صید اتمیک کانفیگ تست بدون ایجاد صف مسدودکننده (Blocking)
                UPDATE TOP (1) subscription_inventory
                SET is_assigned = 1
                OUTPUT INSERTED.id, INSERTED.subscription_link INTO @UpdatedInventory
                WHERE package_id = ? AND is_assigned = 0;

                IF EXISTS (SELECT 1 FROM @UpdatedInventory)
                BEGIN
                    DECLARE @InventoryId INT;
                    DECLARE @Link NVARCHAR(MAX);

                    SELECT @InventoryId = id, @Link = subscription_link FROM @UpdatedInventory;

                    -- ثبت اشتراک تست
                    INSERT INTO user_subscriptions (user_id, inventory_id, invoice_id, assigned_at)
                    VALUES (?, @InventoryId, NULL, GETDATE());

                    -- مسدودسازی درخواست‌های تست بعدی این کاربر
                    UPDATE users SET has_used_test_package = 1 WHERE id = ?;

                    COMMIT TRANSACTION;
                    SELECT 1 AS success, @Link AS link;
                END
                ELSE
                BEGIN
                    ROLLBACK TRANSACTION;
                    SELECT 0 AS success, NULL AS link;
                END
            END TRY
            BEGIN CATCH
                IF @@TRANCOUNT > 0
                    ROLLBACK TRANSACTION;
                THROW;
            END CATCH
            """

            res = await db.execute_query_single(test_transaction, (
            test_pkg['id'], user_internal_id, user_internal_id))

            if res and res['success'] == 1:
                return {"status": "SUCCESS", "link": res['link']}
            else:
                return {"status": "OUT_OF_STOCK", "link": None}

        except Exception as e:
            logger.error(
                f"Error claiming free test package for user {user_internal_id}: {e}")
            return {"status": "ERROR", "link": None}

    async def handle_expired_invoices(self) -> int:
        """
        تغییر وضعیت فاکتورهایی که زمان قانونی پرداخت آن‌ها به سر رسیده است به وضعیت EXPIRED (آیدی 4)
        """
        query = "UPDATE invoices SET status_id = 4 WHERE status_id = 1 AND expires_at < GETDATE()"
        # این متد تعداد فاکتورهای منقضی شده را به دیتابیس برمی‌گرداند
        # پکیج pyodbc مقدار تعداد ردیف‌های تاثیر‌پذیرفته را ثبت می‌کند اما در متد غیراستعلامی ما True/False برمی‌گرداند.
        await db.execute_non_query(query)