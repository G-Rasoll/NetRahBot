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