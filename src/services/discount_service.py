import logging
from datetime import datetime
from typing import Optional, Dict, Any
from src.infrastructure.database import db

logger = logging.getLogger(__name__)


class DiscountService:

    async def create_discount(self, data: Dict[str, Any]) -> int:
        """ساخت کد تخفیف جدید توسط ادمین"""
        query = """
            INSERT INTO discount_codes 
            (code, discount_type, discount_value, max_discount_amount, min_order_amount, 
             total_usage_limit, user_usage_limit, bound_user_id, bound_package_id, expires_at)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data['code'], data['type'], data['value'], data.get('max_amount'),
            data.get('min_amount'), data.get('total_limit'),
            data.get('user_limit', 1),
            data.get('bound_user_id'), data.get('bound_package_id'),
            data.get('expires_at')
        )
        return await db.execute_insert_return_id(query, params)

    async def get_discount_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM discount_codes WHERE code = ?"
        return await db.execute_query_single(query, (code,))

    async def validate_discount_for_invoice(self, code: str, user_id: int,
                                            package_id: int,
                                            base_price: float) -> Dict[str, Any]:
        """ولیدیشن بیزینسی کد تخفیف"""
        discount = await self.get_discount_by_code(code)

        if not discount:
            return {"is_valid": False, "msg": "❌ کد تخفیف یافت نشد یا معتبر نیست."}

        if discount.get('status') and discount['status'] != 'ACTIVE':
            return {"is_valid": False, "msg": "❌ این کد تخفیف غیرفعال شده است."}

        if discount.get('expires_at') and datetime.now() > discount['expires_at']:
            return {"is_valid": False, "msg": "❌ تاریخ انقضای این کد گذشته است."}

        if discount.get('min_order_amount') and base_price < float(discount['min_order_amount']):
            return {"is_valid": False, "msg": f"❌ این کد برای خریدهای بالای {discount['min_order_amount']:,} ریال است."}

        if discount.get('bound_user_id') and discount['bound_user_id'] != user_id:
            return {"is_valid": False, "msg": "❌ این کد تخفیف اختصاصی شما نیست."}

        if discount.get('bound_package_id') and discount['bound_package_id'] != package_id:
            return {"is_valid": False, "msg": "❌ این کد روی این سرویس اعمال نمی‌شود."}

        # محاسبه مبلغ تخفیف
        discount_amount = 0.0
        if discount['discount_type'] == 'PERCENT':
            discount_amount = base_price * (float(discount['discount_value']) / 100.0)
            if discount.get('max_discount_amount') and discount['max_discount_amount'] is not None:
                discount_amount = min(discount_amount, float(discount['max_discount_amount']))
        elif discount['discount_type'] == 'FIXED':
            discount_amount = float(discount['discount_value'])

        discount_amount = min(discount_amount, base_price)

        if discount_amount <= 0:
            return {"is_valid": False, "msg": "❌ مبلغ تخفیف برای این سرویس صفر است."}

        return {
            "is_valid": True,
            "discount_id": discount['id'],
            "discount_amount": discount_amount,
            "total_limit": discount.get('total_usage_limit'),
            "user_limit": discount.get('user_usage_limit', 1)
        }