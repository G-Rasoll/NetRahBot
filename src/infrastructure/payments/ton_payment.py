import logging
import urllib.parse
from typing import Dict, Any
from src.domain.payment_interface import PaymentGateway
from config import  INVOICE_EXPIRY_MINUTES
logger = logging.getLogger(__name__)


class TonPayment(PaymentGateway):
    def __init__(self, wallet_address: str):

        self.wallet_address = wallet_address

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

    def verify_transaction(self, memo: str) -> Dict[str, Any]:

        return {
            "status": "PENDING",
            "amount_received": 0.0,
            "tx_hash": None
        }