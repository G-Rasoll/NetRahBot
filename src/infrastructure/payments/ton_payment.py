import logging
from typing import Dict, Any
import httpx
from src.domain.payment_interface import PaymentGateway

logger = logging.getLogger(__name__)


class TonPayment(PaymentGateway):
    def __init__(self, wallet_address: str):
        self.wallet_address = wallet_address
        self.api_url = "https://toncenter.com/api/v2/getTransactions"

    def create_invoice_link(self, amount: float) -> str:
        try:
            nanoton_amount = int(amount * 1_000_000_000)
            payment_url = f"ton://transfer/{self.wallet_address}?amount={nanoton_amount}"
            logger.info(
                f"Successfully generated TON invoice link for amount: {amount}")
            return payment_url
        except Exception as e:
            logger.error(
                f"Failed to generate TON payment link for amount {amount}: {e}")
            raise RuntimeError(f"Error generating TON payment link: {e}")

    async def verify_transaction(self, expected_amount: float) -> Dict[
        str, Any]:
        """
        جستجوی بلاکچین برای پیدا کردن تراکنشی با مبلغ دقیق
        """
        try:
            params = {
                "address": self.wallet_address,
                "limit": 30,  # واکشی 30 تراکنش آخر برای اطمینان
                "to_lt": 0,
                "archival": "false"
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.api_url, params=params)

                if response.status_code != 200:
                    return {"status": "PENDING", "amount_received": 0.0,
                            "tx_hash": None, "tx_time": None}

                data = response.json()
                if not data.get("ok") or "result" not in data:
                    return {"status": "PENDING", "amount_received": 0.0,
                            "tx_hash": None, "tx_time": None}

                for tx in data["result"]:
                    out_msgs = tx.get("out_msgs", [])
                    if out_msgs:
                        continue

                    in_msg = tx.get("in_msg", {})

                    value_nanoton = int(in_msg.get("value", 0))
                    amount_received = value_nanoton / 1_000_000_000

                    # مقایسه دقیق مبالغ اعشاری
                    if abs(amount_received - expected_amount) < 0.000001:
                        tx_hash = tx.get("transaction_id", {}).get("hash")
                        tx_utime = tx.get("utime")  # زمان تراکنش روی بلاکچین

                        logger.info(
                            f"🎯 Valid transaction found on-chain! Amount: {expected_amount}, Hash: {tx_hash}")
                        return {
                            "status": "PAID",
                            "amount_received": amount_received,
                            "tx_hash": tx_hash,
                            "tx_time": tx_utime
                        }

            return {"status": "PENDING", "amount_received": 0.0,
                    "tx_hash": None, "tx_time": None}

        except Exception as e:
            logger.error(
                f"Error verifying TON transaction for amount {expected_amount}: {e}")
            return {"status": "PENDING", "amount_received": 0.0,
                    "tx_hash": None, "tx_time": None}