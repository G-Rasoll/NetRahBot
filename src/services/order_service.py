import logging
import math
import secrets
from datetime import datetime, timedelta
from src.infrastructure.database import db
from src.infrastructure.payments.ton_payment import TonPayment
from src.infrastructure.panel_api import panel_api
from src.services.package_service import PackageService
from src.services.user_service import UserService
from config import MY_TON_WALLET, INVOICE_EXPIRY_MINUTES,PANEL_ALLOCATION_MODE
from typing import Optional, Dict, Any
import aiohttp
import random
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class OrderService:
    def __init__(self):
        self.package_service = PackageService()
        self.ton_gateway = TonPayment(wallet_address=MY_TON_WALLET)
        self.User_service = UserService()

    async def _get_current_gram_rate(self) -> float:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                    "https://api.tetherland.com/currencies") as response:
                response.raise_for_status()
                usdt_data = await response.json()
            usdt_price = float(
                usdt_data["data"]["currencies"]["USDT"]["price"]
            )
            async with session.get(
                    "https://api.binance.com/api/v3/ticker/price",
                    params={"symbol": "GRAMUSDT"}
            ) as response:
                response.raise_for_status()
                gram_data = await response.json()
            gram_price_usdt = float(gram_data["price"])
            return gram_price_usdt * usdt_price

    async def _generate_unique_amount(self, base_amount) -> Decimal:
        max_retries = 15
        try:
            base_amount = Decimal(str(base_amount)).quantize(
                Decimal("0.000000001"),
                rounding=ROUND_HALF_UP
            )
            if base_amount <= Decimal("0.001"):
                raise ValueError(
                    f"Base amount is too small to apply the random deduction safely: {base_amount}"
                )

            for attempt in range(max_retries):
                random_deduction_int = random.randint(1, 1000000)
                deduction = Decimal(random_deduction_int) / Decimal(
                    "1000000000")
                new_amount = base_amount - deduction
                if new_amount >= base_amount:
                    continue
                new_amount = new_amount.quantize(
                    Decimal("0.000000001"),
                    rounding=ROUND_DOWN
                )
                query = """
                    SELECT id
                    FROM invoices
                    WHERE expected_payment_amount = ?
                      AND status_id = 1
                """
                exists = await db.execute_query_single(query, (new_amount,))
                if not exists:
                    logger.info(
                        f"Unique payment amount generated: "
                        f"{new_amount} "
                        f"(base={base_amount}, attempt={attempt + 1})"
                    )
                    return new_amount
            logger.critical(
                f"Failed to generate unique amount after "
                f"{max_retries} attempts for base {base_amount}"
            )
            raise RuntimeError(
                "سیستم در حال حاضر قادر به تولید فاکتور یکتا نیست. "
                "لطفاً دقایقی دیگر تلاش کنید."
            )
        except Exception as e:
            logger.error(
                f"Error generating unique amount for base "
                f"{base_amount}: {e}",
                exc_info=True
            )
            raise

    async def create_invoice(
            self,
            user_internal_id: int,
            package_id: int,
            custom_name: str = None
    ) -> Optional[Dict[str, Any]]:

        try:
            package = await self.package_service.get_package_by_id(package_id)
            if not package or not package['is_active']:
                return None

            gram_rate = await self._get_current_gram_rate()
            if gram_rate <= 0:
                raise ValueError(
                    "Calculated GRAM exchange rate must be greater than zero."
                )
            package_price = Decimal(str(package['price_rial']))
            gram_rate_decimal = Decimal(str(gram_rate))
            raw_base_amount = package_price / gram_rate_decimal
            base_expected_amount = raw_base_amount.quantize(
                Decimal("0.000000001"),
                rounding=ROUND_HALF_UP
            )
            expected_amount = await self._generate_unique_amount(
                base_expected_amount)
            expires_at = datetime.now() + timedelta(
                minutes=INVOICE_EXPIRY_MINUTES)
            query = """
                INSERT INTO invoices (
                    user_id,
                    package_id,
                    status_id,
                    package_title_snapshot,
                    package_price_snapshot_rial,
                    package_volume_snapshot_mb,
                    payment_currency_code,
                    expected_payment_amount,
                    amount_received,
                    expires_at,
                    custom_config_name
                )
                OUTPUT INSERTED.id
                VALUES (?, ?, 1, ?, ?, ?, ?, ?, 0.0, ?, ?)
            """
            params = (
                user_internal_id,
                package['id'],
                package['title'],
                package['price_rial'],
                package['volume_mb'],
                "GRAM",
                expected_amount,
                expires_at,
                custom_name
            )
            invoice_id = await db.execute_insert_return_id(query, params)
            payment_url = self.ton_gateway.create_invoice_link(
                amount=expected_amount)
            logger.info(
                f"Invoice created: "
                f"id={invoice_id}, "
                f"base_amount={base_expected_amount}, "
                f"expected_amount={expected_amount}, "
                f"currency=GRAM"
            )
            return {
                "invoice_id": invoice_id,
                "expected_amount": expected_amount,
                "payment_link": payment_url,
                "expires_at": expires_at,
                "package_title": package['title']
            }
        except Exception as e:
            logger.error(
                f"Error in creating invoice for user {user_internal_id}: {e}",
                exc_info=True
            )
            raise

    async def update_invoice_message_data(self, invoice_id: int, chat_id: int,
                                          message_id: int):
        """ثبت آیدی پیام تلگرام در دیتابیس برای حذف در صورت انقضا"""
        try:
            query = "UPDATE invoices SET chat_id = ?, message_id = ? WHERE id = ?"
            await db.execute_non_query(query, (chat_id, message_id, invoice_id))
            logger.info(
                f"Successfully updated message data for invoice {invoice_id} | Chat: {chat_id}, Msg: {message_id}")
        except Exception as e:
            logger.error(
                f"Failed to update chat_id/message_id for invoice {invoice_id}. DB Error: {e}",
                exc_info=True)
            raise e

    async def process_successful_payment(self, invoice_id: int, package_id: int,
                                         user_id: int, tx_hash: str,
                                         amount_received: float,
                                         tx_time: int) -> Dict[str, Any]:

        # بررسی تقلب زمانی (پرداخت دیرهنگام)
        invoice = await db.execute_query_single(
            "SELECT expires_at FROM invoices WHERE id = ?", (invoice_id,))
        if invoice:
            tx_datetime = datetime.fromtimestamp(tx_time)
            # اگر زمان تراکنش روی بلاکچین از زمان انقضای ما بیشتر باشد
            if tx_datetime > invoice['expires_at']:
                logger.warning(
                    f"Late payment detected for invoice {invoice_id}. Updating status to 6 (LATE_PAYMENT).")
                query_late = "UPDATE invoices SET status_id = 6, tx_hash = ?, amount_received = ? WHERE id = ?"
                await db.execute_non_query(query_late, (
                tx_hash, amount_received, invoice_id))
                return {"status": "LATE_PAYMENT", "link": None}

        # آپدیت فاکتور به PAID
        query_update_invoice = """
                    UPDATE invoices 
                    SET status_id = 2, tx_hash = ?, amount_received = ? 
                    WHERE id = ? AND status_id = 1
                """
        await db.execute_non_query(query_update_invoice,
                                   (tx_hash, amount_received, invoice_id))

        if PANEL_ALLOCATION_MODE == "AUTO":
            try:
                user_info = await self.User_service.get_user_by_id(user_id)
                pkg = await self.package_service.get_package_by_id(package_id)
                vol_gb = float(pkg['volume_gb'])

                generated_link = await panel_api.create_user_config(
                    sub_type="buyed",
                    telegram_id=user_info["telegram_id"],
                    limit_gb=vol_gb)
                auto_transaction = """
                        BEGIN TRY
                                BEGIN TRANSACTION;
                                DECLARE @ConfName NVARCHAR(100);
                                SELECT @ConfName = custom_config_name FROM invoices WHERE id = ?;

                                INSERT INTO subscription_inventory (package_id, subscription_link, is_assigned, created_at)
                                VALUES (?, ?, 1, GETDATE());

                                DECLARE @NewInventoryId INT = SCOPE_IDENTITY();

                                INSERT INTO user_subscriptions (user_id, inventory_id, invoice_id, assigned_at, config_name)
                                VALUES (?, @NewInventoryId, ?, GETDATE(), ISNULL(@ConfName, N'اشتراک تجاری'));

                                UPDATE invoices SET status_id = 3 WHERE id = ?;
                                COMMIT TRANSACTION;
                                SELECT 1 AS success;
                            END TRY
                            BEGIN CATCH
                                IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
                                THROW;
                            END CATCH
                            """
                await db.execute_query_single(auto_transaction, (
                invoice_id, package_id, generated_link, user_id, invoice_id,
                invoice_id))
                return {"status": "SUCCESS", "link": generated_link}

            except Exception as ex:
                logger.error(
                    f"Error in AUTO allocation for invoice {invoice_id}: {ex}")
                return {"status": "OUT_OF_STOCK", "link": None}
        else:
            transaction_query = """
                    BEGIN TRY
                        BEGIN TRANSACTION;
                        DECLARE @ConfName NVARCHAR(100);
                        SELECT @ConfName = custom_config_name FROM invoices WHERE id = ?;

                        DECLARE @UpdatedInventory TABLE (id INT, subscription_link NVARCHAR(MAX));

                        UPDATE TOP (1) subscription_inventory
                        SET is_assigned = 1
                        OUTPUT INSERTED.id, INSERTED.subscription_link INTO @UpdatedInventory
                        WHERE package_id = ? AND is_assigned = 0;

                        IF EXISTS (SELECT 1 FROM @UpdatedInventory)
                        BEGIN
                            DECLARE @SelectedInventoryId INT;
                            DECLARE @SubLink NVARCHAR(MAX);
                            SELECT @SelectedInventoryId = id, @SubLink = subscription_link FROM @UpdatedInventory;

                            INSERT INTO user_subscriptions (user_id, inventory_id, invoice_id, assigned_at, config_name)
                            VALUES (?, @SelectedInventoryId, ?, GETDATE(), ISNULL(@ConfName, N'اشتراک تجاری'));

                            UPDATE invoices SET status_id = 3 WHERE id = ?;
                            COMMIT TRANSACTION;
                            SELECT 1 AS success, @SubLink AS link;
                        END
                        ELSE
                        BEGIN
                            ROLLBACK TRANSACTION;
                            SELECT 0 AS success, NULL AS link;
                        END
                    END TRY
                    BEGIN CATCH
                        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
                        THROW;
                    END CATCH
                    """
            result = await db.execute_query_single(transaction_query, (
            invoice_id, package_id, user_id, invoice_id, invoice_id))
            if result and result['success'] == 1:
                return {"status": "SUCCESS", "link": result['link']}
            else:
                return {"status": "OUT_OF_STOCK", "link": None}
    async def claim_free_test_package(self, user_internal_id: int,
                                      telegram_id: int) -> Dict[str, Any]:

        try:
            check_user_query = "SELECT has_used_test_package FROM users WHERE id = ?"
            user_status = await db.execute_query_single(check_user_query,
                                                        (user_internal_id,))

            if not user_status or user_status['has_used_test_package']:
                return {"status": "ALREADY_USED", "link": None}

            pkg_query = "SELECT id, volume_gb FROM packages WHERE is_test_package = 1 AND is_active = 1"
            test_pkg = await db.execute_query_single(pkg_query)
            if not test_pkg:
                return {"status": "NO_TEST_PACKAGE_DEFINED", "link": None}

            if PANEL_ALLOCATION_MODE == "AUTO":
                generated_link = None
                vol_gb = float(test_pkg['volume_gb'])

                try:
                    # تلاش برای ساخت کانفیگ در پنل
                    generated_link = await panel_api.create_user_config(
                        limit_gb=vol_gb, sub_type="Test",
                        telegram_id=telegram_id)
                except Exception as api_ex:
                    # مکانیزم دفاعی هوشمند: نجات کانفیگ در صورت بازگرداندن استاتوس موفقیت‌آمیز 201
                    import re
                    err_msg = str(api_ex)
                    if "201 -" in err_msg and "subscription_url" in err_msg:
                        # استخراج لینک سابسکریپشن از بدنه جی‌سون موجود در متن خطا
                        match = re.search(r'"subscription_url"\s*:\s*"([^"]+)"',
                                          err_msg)
                        if match:
                            generated_link = match.group(1)
                            logger.info(
                                f"Successfully salvaged subscription link from 201 response: {generated_link}")
                        else:
                            raise api_ex
                    else:
                        # اگر خطا واقعاً جدی بود (مثل قطعی سرور یا ۴۰۰)، خطا را بالا بفرست
                        raise api_ex

                # اجرای تراکنش دیتابیس در صورت داشتن لینک (چه از مسیر عادی چه از مسیر نجات)
                try:
                    auto_transaction = """
                                    BEGIN TRY
                                        BEGIN TRANSACTION;

                                        -- ۱. ثبت کانفیگ در موجودی انبار
                                        INSERT INTO subscription_inventory (package_id, subscription_link, is_assigned, created_at)
                                        VALUES (?, ?, 1, GETDATE());
                                        DECLARE @InventoryId INT = SCOPE_IDENTITY();

                                        -- ۲. تخصیص کانفیگ به کاربر
                                        INSERT INTO user_subscriptions (user_id, inventory_id, invoice_id, assigned_at, config_name)
                                        VALUES (?, @InventoryId, NULL, GETDATE(), N'تست رایگان');

                                        -- ۳. علامت‌گذاری استفاده کاربر
                                        UPDATE users SET has_used_test_package = 1 WHERE id = ?;

                                        COMMIT TRANSACTION;
                                        SELECT 1 AS success;
                                    END TRY
                                    BEGIN CATCH
                                        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
                                        THROW;
                                    END CATCH
                                    """
                    await db.execute_query_single(auto_transaction, (
                        test_pkg['id'], generated_link, user_internal_id,
                        user_internal_id
                    ))
                    return {"status": "SUCCESS", "link": generated_link}

                except Exception as db_ex:
                    logger.error(
                        f"Critical Error saving AUTO config to database: {db_ex} | Link was: {generated_link}")
                    return {"status": "ERROR", "link": None}
            else:
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
                               INSERT INTO user_subscriptions (user_id, inventory_id, invoice_id, assigned_at, config_name)
                               VALUES (?, @InventoryId, NULL, GETDATE(), N'تست رایگان');

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
        query = "UPDATE invoices SET status_id = 4 WHERE status_id = 1 AND expires_at < GETDATE()"
        await db.execute_non_query(query)

    async def create_manual_admin_config(self, admin_internal_id: int,
                                         admin_tg_id: int, volume_gb: float,
                                         brand_name: str,
                                         custom_name: str = None) -> Dict[
        str, Any]:
        try:
            generated_link = await panel_api.create_user_config(
                sub_type="Manual",
                telegram_id=admin_tg_id,
                limit_gb=volume_gb,
                brand_name=brand_name,
                custom_name=custom_name
            )

            memo = f"NR-{secrets.randbelow(900000) + 100000}"
            volume_mb = int(volume_gb * 1024)
            pkg_snapshot_title = f"🛠️ کانفیگ دستی ادمین ({volume_gb} GB) - {brand_name}"

            transaction_query = """
            SET NOCOUNT ON;
            BEGIN TRY
                BEGIN TRANSACTION;

                DECLARE @PkgId INT;
                SELECT TOP 1 @PkgId = id FROM packages WHERE title = N'🛠️ کانفیگ دستی ادمین';

                IF @PkgId IS NULL
                BEGIN
                    INSERT INTO packages (title, volume_mb, price_rial, is_test_package, is_active, is_gift_package, volume_gb)
                    VALUES (N'🛠️ کانفیگ دستی ادمین', 0, 0, 0, 1, 0, 0);
                    SET @PkgId = SCOPE_IDENTITY();
                END

                INSERT INTO invoices (
                    user_id, package_id, memo, status_id, 
                    package_title_snapshot, package_price_snapshot_rial, package_volume_snapshot_mb, 
                    payment_currency_code, expected_payment_amount, amount_received, tx_hash, expires_at, created_at
                ) 
                VALUES (
                    ?, @PkgId, ?, 3, 
                    ?, 0, ?, 
                    'MANUAL', 0.0, 0.0, ?, GETDATE(), GETDATE()
                );
                DECLARE @InvoiceId INT = SCOPE_IDENTITY();

                INSERT INTO subscription_inventory (package_id, subscription_link, is_assigned, created_at)
                VALUES (@PkgId, ?, 1, GETDATE());
                DECLARE @InventoryId INT = SCOPE_IDENTITY();

                INSERT INTO user_subscriptions (user_id, inventory_id, invoice_id, assigned_at, config_name)
                VALUES (?, @InventoryId, @InvoiceId, GETDATE(), ?);

                COMMIT TRANSACTION;
                SELECT 1 AS success;
            END TRY
            BEGIN CATCH
                IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
                THROW;
            END CATCH
            """

            await db.execute_query_single(
                transaction_query,
                (admin_internal_id, memo, pkg_snapshot_title, volume_mb,
                 None, generated_link, admin_internal_id, custom_name)
            )

            return {"status": "SUCCESS", "link": generated_link, "memo": memo}

        except Exception as e:
            logger.error(
                f"Error creating manual admin config for user {admin_internal_id}: {e}")
            return {"status": "ERROR", "message": str(e)}