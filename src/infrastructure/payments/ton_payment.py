import logging
import urllib.parse
from typing import Dict, Any
import httpx
from src.domain.payment_interface import PaymentGateway
from config import  INVOICE_EXPIRY_MINUTES
logger = logging.getLogger(__name__)


class TonPayment(PaymentGateway):
    def __init__(self, wallet_address: str):

        self.wallet_address = wallet_address
        self.api_url = "https://toncenter.com/api/v2/getTransactions"

    def create_invoice_link(self, amount: float, memo: str,
                            expires_in_minutes: int = 15) -> str:

        try:
            nanoton_amount = int(amount * 1_000_000_000)

            safe_memo = urllib.parse.quote(memo)

            payment_url = f"ton://transfer/{self.wallet_address}?amount={nanoton_amount}&text={safe_memo}"

            logger.info(
                f"Successfully generated TON invoice link for memo: {memo}")
            return payment_url

        except Exception as e:
            logger.error(
                f"Failed to generate TON payment link for amount {amount}: {e}")
            raise RuntimeError(f"Error generating TON payment link: {e}")

    async def verify_transaction(self, memo: str) -> Dict[str, Any]:
        """
        جستجوی بلاکچین برای پیدا کردن تراکنشی با ممو و مشخصات معتبر
        """
        try:
            # ارسال درخواست به API شبکه TON برای دریافت 20 تراکنش آخر ولت ادمین
            params = {
                "address": self.wallet_address,
                "limit": 20,
                "to_lt": 0,
                "archival": "false"
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.api_url, params=params)

                if response.status_code != 200:
                    logger.error(
                        f"TON API error: Status {response.status_code}")
                    return {"status": "PENDING", "amount_received": 0.0,
                            "tx_hash": None}

                data = response.json()
                if not data.get("ok") or "result" not in data:
                    return {"status": "PENDING", "amount_received": 0.0,
                            "tx_hash": None}

                # گردش میان تراکنش‌های دریافت شده روی بلاکچین
                for tx in data["result"]:
                    out_msgs = tx.get("out_msgs", [])
                    # ما به دنبال تراکنش‌های ورودی (In) به ولت خودمان هستیم، پس تراکنش‌های خروجی ولت را رد می‌کنیم
                    if out_msgs:
                        continue

                    in_msg = tx.get("in_msg", {})
                    # استخراج کامنت یا همان مموی تراکنش روی بلاکچین
                    tx_memo = in_msg.get("message", "").strip()

                    # اگر مموی تراکنش روی زنجیره با مموی فاکتور ما یکی بود:
                    if tx_memo == memo:
                        # تبدیل مقدار نانو‌تون دریافتی به واحد TON
                        value_nanoton = int(in_msg.get("value", 0))
                        amount_received = value_nanoton / 1_000_000_000
                        tx_hash = tx.get("transaction_id", {}).get("hash")

                        logger.info(
                            f"🎯 Valid transaction found on-chain! Memo: {memo}, Hash: {tx_hash}")
                        return {
                            "status": "PAID",
                            "amount_received": amount_received,
                            "tx_hash": tx_hash
                        }

            # اگر در تراکنش‌های اخیر چیزی یافت نشد
            return {"status": "PENDING", "amount_received": 0.0,
                    "tx_hash": None}

        except Exception as e:
            logger.error(
                f"Error verifying TON transaction for memo {memo}: {e}")
            return {"status": "PENDING", "amount_received": 0.0,
                    "tx_hash": None}