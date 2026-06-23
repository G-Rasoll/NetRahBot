import logging
from typing import Optional, Dict, Any
from src.infrastructure.database import db
from src.infrastructure.panel_api import panel_api
from config import PANEL_ALLOCATION_MODE

logger = logging.getLogger(__name__)


class ReferralService:

    async def get_user_referral_stats(self, user_id: int) -> Dict[str, Any]:
        """دریافت آمار زیرمجموعه‌گیری کاربر و تنظیمات حد نصاب سیستم"""
        try:
            settings = await db.execute_query_single(
                "SELECT required_invites FROM referral_settings WHERE id = 1")
            required_invites = settings['required_invites'] if settings else 5

            stats = await db.execute_query_single(
                "SELECT current_points, total_invites FROM user_referral_stats WHERE user_id = ?",
                (user_id,)
            )
            if stats:
                return {
                    "current_points": stats['current_points'],
                    "total_invites": stats['total_invites'],
                    "required_invites": required_invites
                }
            return {"current_points": 0, "total_invites": 0,
                    "required_invites": required_invites}
        except Exception as e:
            logger.error(
                f"Error fetching referral stats for user {user_id}: {e}")
            return {"current_points": 0, "total_invites": 0,
                    "required_invites": 5}

    async def record_pending_referral(self, inviter_id: int,
                                      referee_telegram_id: int) -> bool:
        """ثبت دعوت اولیه به صورت در انتظار با اعمال فیلترهای سخت‌گیرانه ضد تقلب"""
        try:
            # تقلب ۱: کاربر نباید خودش را دعوت کند
            inviter = await db.execute_query_single(
                "SELECT telegram_id FROM users WHERE id = ?", (inviter_id,))
            if inviter and inviter['telegram_id'] == referee_telegram_id:
                logger.warning(
                    f"Anti-Fraud: User {referee_telegram_id} tried to invite themselves.")
                return False

            # تقلب ۲: کاربر دعوت‌شده نباید از قبل در دیتابیس ربات عضو بوده باشد (عضو قدیمی نباشد)
            user_exists = await db.execute_query_single(
                "SELECT id FROM users WHERE telegram_id = ?",
                (referee_telegram_id,))
            if user_exists:
                logger.warning(
                    f"Anti-Fraud: User {referee_telegram_id} is already a registered user.")
                return False

            # تقلب ۳: این تلگرام آیدی نباید قبلاً توسط شخص دیگری دعوت شده باشد (یکبار مصرف بودن پتانسیل دعوت)
            ref_exists = await db.execute_query_single(
                "SELECT id FROM referrals WHERE referee_telegram_id = ?",
                (referee_telegram_id,))
            if ref_exists:
                logger.warning(
                    f"Anti-Fraud: User {referee_telegram_id} has a historical referral record.")
                return False

            # درج دعوت اولیه به صورت PENDING
            query = """
                INSERT INTO referrals (inviter_id, referee_telegram_id, status, created_at)
                VALUES (?, ?, 'PENDING', GETDATE())
            """
            await db.execute_non_query(query, (inviter_id, referee_telegram_id))
            return True
        except Exception as e:
            logger.error(f"Error recording pending referral: {e}")
            return False

    async def complete_referral_if_exists(self, referee_telegram_id: int) -> \
    Optional[Dict[str, Any]]:
        """تکمیل اتمیک فرآیند دعوت و تخصیص آنی کانفیگ هدیه در صورت رسیدن به حد نصاب"""
        try:
            check_query = """
                        SELECT r.inviter_id, u.telegram_id as inviter_telegram_id 
                        FROM referrals r
                        JOIN users u ON r.inviter_id = u.id
                        WHERE r.referee_telegram_id = ? AND r.status = 'PENDING'
                    """
            ref_info = await db.execute_query_single(check_query,
                                                     (referee_telegram_id,))
            if not ref_info:
                return None

            inviter_id = ref_info['inviter_id']
            inviter_tg_id = ref_info['inviter_telegram_id']

            # 1. تکمیل رفرال و محاسبه امتیاز (بدون اعطای پاداش در این مرحله)
            grant_points_query = """
                    SET NOCOUNT ON;
                    BEGIN TRY
                        BEGIN TRANSACTION;
                        DECLARE @RequiredInvites INT;
                        DECLARE @GiftPkgId INT;
                        SELECT @RequiredInvites = required_invites, @GiftPkgId = gift_package_id FROM referral_settings WHERE id = 1;

                        UPDATE referrals SET status = 'COMPLETED', completed_at = GETDATE() WHERE referee_telegram_id = ? AND status = 'PENDING';

                        IF NOT EXISTS (SELECT 1 FROM user_referral_stats WHERE user_id = ?)
                            INSERT INTO user_referral_stats (user_id, current_points, total_invites) VALUES (?, 0, 0);

                        UPDATE user_referral_stats SET current_points = current_points + 1, total_invites = total_invites + 1 WHERE user_id = ?;

                        DECLARE @CurrentPoints INT;
                        SELECT @CurrentPoints = current_points FROM user_referral_stats WHERE user_id = ?;

                        COMMIT TRANSACTION;
                        SELECT 1 AS success, @CurrentPoints AS current_points, @RequiredInvites AS required_invites, @GiftPkgId AS gift_package_id;
                    END TRY
                    BEGIN CATCH
                        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
                        THROW;
                    END CATCH
                    """
            points_res = await db.execute_query_single(grant_points_query, (
            referee_telegram_id, inviter_id, inviter_id, inviter_id,
            inviter_id))

            if not points_res:
                return None

            current_points = points_res['current_points']
            required_invites = points_res['required_invites']
            gift_package_id = points_res['gift_package_id']

            response_data = {
                "success": 1,
                "inviter_telegram_id": inviter_tg_id,
                "reward_granted": False,
                "link": None,
                "required_invites": required_invites,
                "current_points": current_points,
                "out_of_stock": False
            }

            # 2. بررسی رسیدن به حد نصاب و تخصیص جایزه
            if current_points >= required_invites:
                if PANEL_ALLOCATION_MODE == "AUTO":
                    try:
                        pkg_query = "SELECT volume_gb FROM packages WHERE id = ?"
                        gift_pkg = await db.execute_query_single(pkg_query, (
                        gift_package_id,))
                        vol_gb = float(gift_pkg['volume_gb'])

                        generated_link = await panel_api.create_user_config(
                            vol_gb)

                        auto_reward_tx = """
                                BEGIN TRY
                                    BEGIN TRANSACTION;
                                    UPDATE user_referral_stats SET current_points = current_points - ? WHERE user_id = ?;

                                    INSERT INTO subscription_inventory (package_id, subscription_link, is_assigned, created_at)
                                    VALUES (?, ?, 1, GETDATE());
                                    DECLARE @InventoryId INT = SCOPE_IDENTITY();

                                    INSERT INTO user_subscriptions (user_id, inventory_id, invoice_id, assigned_at)
                                    VALUES (?, @InventoryId, NULL, GETDATE());

                                    COMMIT TRANSACTION;
                                    SELECT current_points FROM user_referral_stats WHERE user_id = ?;
                                END TRY
                                BEGIN CATCH
                                    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
                                    THROW;
                                END CATCH
                                """
                        await db.execute_query_single(auto_reward_tx, (
                        required_invites, inviter_id, gift_package_id,
                        generated_link, inviter_id, inviter_id))
                        response_data.update(
                            {"reward_granted": True, "link": generated_link,
                             "current_points": current_points - required_invites})

                    except Exception as e:
                        logger.error(
                            f"Error auto-generating referral gift: {e}")
                        response_data["out_of_stock"] = True

                else:
                    # حالت DATABASE
                    db_reward_tx = """
                            BEGIN TRY
                                BEGIN TRANSACTION;
                                DECLARE @SubLink NVARCHAR(MAX) = NULL;
                                DECLARE @UpdatedInventory TABLE (id INT, subscription_link NVARCHAR(MAX));

                                UPDATE user_referral_stats SET current_points = current_points - ? WHERE user_id = ?;

                                UPDATE TOP (1) subscription_inventory 
                                SET is_assigned = 1 OUTPUT INSERTED.id, INSERTED.subscription_link INTO @UpdatedInventory 
                                WHERE package_id = ? AND is_assigned = 0;

                                IF EXISTS (SELECT 1 FROM @UpdatedInventory)
                                BEGIN
                                    DECLARE @InventoryId INT;
                                    SELECT @InventoryId = id, @SubLink = subscription_link FROM @UpdatedInventory;
                                    INSERT INTO user_subscriptions (user_id, inventory_id, invoice_id, assigned_at) 
                                    VALUES (?, @InventoryId, NULL, GETDATE());
                                    COMMIT TRANSACTION;
                                    SELECT 1 AS reward_granted, @SubLink AS link;
                                END
                                ELSE
                                BEGIN
                                    -- بازگشت امتیاز در صورت خالی بودن انبار
                                    UPDATE user_referral_stats SET current_points = current_points + ? WHERE user_id = ?;
                                    COMMIT TRANSACTION;
                                    SELECT 0 AS reward_granted, NULL AS link;
                                END
                            END TRY
                            BEGIN CATCH
                                IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
                                THROW;
                            END CATCH
                            """
                    res = await db.execute_query_single(db_reward_tx, (
                    required_invites, inviter_id, gift_package_id, inviter_id,
                    required_invites, inviter_id))
                    if res and res['reward_granted']:
                        response_data.update(
                            {"reward_granted": True, "link": res['link'],
                             "current_points": current_points - required_invites})
                    else:
                        response_data["out_of_stock"] = True

            return response_data

        except Exception as e:
            logger.error(
                f"Error completing referral for {referee_telegram_id}: {e}")
            return None

    async def verify_user_joined(self, referee_telegram_id: int) -> \
    Optional[int]:
        """
        تغییر وضعیت رفرال از PENDING به JOINED پس از تایید عضویت در کانال
        و بازگرداندن آیدی تلگرام دعوت‌کننده جهت ارسال نوتیفیکیشن
        """
        try:
            check_query = """
                SELECT r.id, u.telegram_id as inviter_telegram_id 
                FROM referrals r
                JOIN users u ON r.inviter_id = u.id
                WHERE r.referee_telegram_id = ? AND r.status = 'PENDING'
            """
            ref = await db.execute_query_single(check_query,
                                                (referee_telegram_id,))

            if ref:
                update_query = "UPDATE referrals SET status = 'JOINED' WHERE referee_telegram_id = ? AND status = 'PENDING'"
                await db.execute_non_query(update_query,
                                           (referee_telegram_id,))
                return ref['inviter_telegram_id']

            return None
        except Exception as e:
            logger.error(
                f"Error verifying user join in referrals for {referee_telegram_id}: {e}")
            return None

    async def claim_reward(self, user_id: int, telegram_id: int) -> Dict[
        str, Any]:
        """
        تخلیه امتیازات کاربر، ساخت کانفیگ معادل حجم امتیازات و ثبت در دیتابیس به صورت اتمیک
        """
        try:
            stats_query = "SELECT current_points FROM user_referral_stats WHERE user_id = ?"
            stats = await db.execute_query_single(stats_query, (user_id,))

            if not stats or stats['current_points'] <= 0:
                return {"status": "NO_POINTS"}

            points = stats['current_points']

            # هر امتیاز معادل ۱ گیگابایت (تبدیل به float برای پنل)
            limit_gb = float(points)

            # ساخت کانفیگ در پنل
            generated_link = await panel_api.create_user_config(
                sub_type="Gift", telegram_id=telegram_id, limit_gb=limit_gb)

            # تراکنش اتمیک برای ثبت هدیه و صفر کردن امتیاز
            reward_tx = """
            BEGIN TRY
                BEGIN TRANSACTION;

                -- صفر کردن امتیاز کاربر
                UPDATE user_referral_stats SET current_points = 0 WHERE user_id = ?;

                -- پیدا کردن آیدی پکیج هدیه (برای رفرنس انبار)
                DECLARE @GiftPkgId INT;
                SELECT TOP 1 @GiftPkgId = id FROM packages WHERE is_gift_package = 1;

                -- ثبت کانفیگ جدید در انبار
                INSERT INTO subscription_inventory (package_id, subscription_link, is_assigned, created_at)
                VALUES (@GiftPkgId, ?, 1, GETDATE());

                DECLARE @InventoryId INT = SCOPE_IDENTITY();

                -- تخصیص هدیه به کاربر در لیست سرویس‌های من
                INSERT INTO user_subscriptions (user_id, inventory_id, invoice_id, assigned_at)
                VALUES (?, @InventoryId, NULL, GETDATE());

                COMMIT TRANSACTION;
                SELECT 1 AS success;
            END TRY
            BEGIN CATCH
                IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
                THROW;
            END CATCH
            """
            await db.execute_query_single(reward_tx, (
            user_id, generated_link, user_id))
            return {"status": "SUCCESS", "link": generated_link,
                    "gb": points}

        except Exception as e:
            logger.error(f"Error claiming reward for user {user_id}: {e}")
            return {"status": "ERROR"}

    async def process_referral_on_purchase(self,
                                           referee_telegram_id: int) -> \
    Optional[Dict[str, Any]]:
        """بررسی دیتابیس در زمان خرید؛ اگر اولین خرید زیرمجموعه باشد، وضعیت COMPLETED شده و ۱ امتیاز به دعوت‌کننده تخصیص می‌یابد."""
        try:
            # بررسی اینکه آیا کاربر زیرمجموعه تایید شده هست و هنوز امتیازاش آزاد نشده یا خیر
            query_check = "SELECT inviter_id FROM referrals WHERE referee_telegram_id = ? AND status = 'JOINED'"
            referral = await db.execute_query_single(query_check,
                                                     (referee_telegram_id,))
            if not referral:
                return None

            inviter_id = referral['inviter_id']

            transaction_query = """
            BEGIN TRANSACTION;
            BEGIN TRY
                -- تغییر وضعیت رفرال به COMPLETED برای سوختن دفعات بعدی خرید
                UPDATE referrals 
                SET status = 'COMPLETED', completed_at = GETDATE() 
                WHERE referee_telegram_id = ? AND status = 'JOINED';

                -- افزایش امتیازات فعلی و کل دعوت‌های کاربر دعوت‌کننده
                IF EXISTS (SELECT 1 FROM user_referral_stats WHERE user_id = ?)
                BEGIN
                    UPDATE user_referral_stats 
                    SET current_points = current_points + 1, total_invites = total_invites + 1 
                    WHERE user_id = ?;
                END
                ELSE
                BEGIN
                    INSERT INTO user_referral_stats (user_id, current_points, total_invites) 
                    VALUES (?, 1, 1);
                END

                COMMIT TRANSACTION;
                SELECT 1 AS success;
            END TRY
            BEGIN CATCH
                IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
                THROW;
            END CATCH
            """
            res = await db.execute_query_single(transaction_query, (
            referee_telegram_id, inviter_id, inviter_id, inviter_id))
            if res and res['success'] == 1:
                # واکشی تلگرام‌آیدی دعوت‌کننده جهت ارسال نوتیفیکیشن لحظه‌ای
                inviter_user = await db.execute_query_single(
                    "SELECT telegram_id FROM users WHERE id = ?",
                    (inviter_id,))
                return {"inviter_telegram_id": inviter_user[
                    'telegram_id'] if inviter_user else None}
            return None
        except Exception as e:
            logger.error(
                f"Error processing referral points on purchase for {referee_telegram_id}: {e}")
            return None
