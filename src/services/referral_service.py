import logging
from typing import Optional, Dict, Any
from src.infrastructure.database import db

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
            # بررسی وجود دعوت ثبت شده فعال برای این کاربر
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

            # اضافه شدن SET NOCOUNT ON جهت وادار کردن دیتابیس به بازگرداندنِ مستقیم نتایج SELECT نهایی به پایتون
            transaction_query = """
            SET NOCOUNT ON;
            BEGIN TRY
                BEGIN TRANSACTION;

                DECLARE @RequiredInvites INT;
                DECLARE @GiftPkgId INT;
                SELECT @RequiredInvites = required_invites, @GiftPkgId = gift_package_id FROM referral_settings WHERE id = 1;

                -- ۱. تبدیل وضعیت دعوت به تکمیل شده
                UPDATE referrals 
                SET status = 'COMPLETED', completed_at = GETDATE() 
                WHERE referee_telegram_id = ? AND status = 'PENDING';

                -- ۲. تضمین وجود سطر آماری برای دعوت‌کننده
                IF NOT EXISTS (SELECT 1 FROM user_referral_stats WHERE user_id = ?)
                BEGIN
                    INSERT INTO user_referral_stats (user_id, current_points, total_invites) VALUES (?, 0, 0);
                END

                -- ۳. افزایش آنی امتیازهای فعال و کل دعوت‌ها
                UPDATE user_referral_stats
                SET current_points = current_points + 1,
                    total_invites = total_invites + 1
                WHERE user_id = ?;

                DECLARE @CurrentPoints INT;
                SELECT @CurrentPoints = current_points FROM user_referral_stats WHERE user_id = ?;

                DECLARE @RewardGranted BIT = 0;
                DECLARE @SubLink NVARCHAR(MAX) = NULL;
                DECLARE @OutOfStock BIT = 0;

                -- ۴. بررسی رسیدن به حد نصاب دریافت پکیج هدیه
                IF @CurrentPoints >= @RequiredInvites
                BEGIN
                    -- کسر امتیاز حد نصاب (با متد کسر ریاضی جهت حفظ امتیازهای مازاد احتمالی)
                    UPDATE user_referral_stats 
                    SET current_points = current_points - @RequiredInvites 
                    WHERE user_id = ?;

                    -- صید اتمیک کانفیگ هدیه از انبار
                    DECLARE @UpdatedInventory TABLE (id INT, subscription_link NVARCHAR(MAX));

                    UPDATE TOP (1) subscription_inventory 
                    SET is_assigned = 1 
                    OUTPUT INSERTED.id, INSERTED.subscription_link INTO @UpdatedInventory 
                    WHERE package_id = @GiftPkgId AND is_assigned = 0;

                    IF EXISTS (SELECT 1 FROM @UpdatedInventory)
                    BEGIN
                        DECLARE @InventoryId INT;
                        SELECT @InventoryId = id, @SubLink = subscription_link FROM @UpdatedInventory;

                        -- ثبت کانفیگ هدیه در اشتراک‌های کاربر (بدون invoice_id چون هدیه است)
                        INSERT INTO user_subscriptions (user_id, inventory_id, invoice_id, assigned_at) 
                        VALUES (?, @InventoryId, NULL, GETDATE());

                        SET @RewardGranted = 1;
                    END
                    ELSE
                    BEGIN
                        -- بن‌بست انبار خالی: عودت امتیاز کسر شده به کاربر تا هدیه نسوزد
                        UPDATE user_referral_stats 
                        SET current_points = current_points + @RequiredInvites 
                        WHERE user_id = ?;

                        SET @OutOfStock = 1;
                    END
                END

                SELECT @CurrentPoints = current_points FROM user_referral_stats WHERE user_id = ?;

                COMMIT TRANSACTION;

                -- خروجی نهایی که مستقیماً به دست پایتون می‌رسد
                SELECT 1 AS success, @RewardGranted AS reward_granted, @SubLink AS link, 
                       @RequiredInvites AS required_invites, @CurrentPoints AS current_points, @OutOfStock AS out_of_stock;

            END TRY
            BEGIN CATCH
                IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
                THROW;
            END CATCH
            """


            params = (
                referee_telegram_id,
                inviter_id,
                inviter_id,
                inviter_id,
                inviter_id,
                inviter_id,
                inviter_id,
                inviter_id,
                inviter_id
            )

            res = await db.execute_query_single(transaction_query, params)
            if res:
                res['inviter_telegram_id'] = inviter_tg_id
            return res
        except Exception as e:
            logger.error(
                f"Error completing referral for {referee_telegram_id}: {e}")
            return None