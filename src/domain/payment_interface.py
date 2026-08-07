from abc import ABC, abstractmethod
from typing import Dict, Any

class PaymentGateway(ABC):

    @abstractmethod
    def create_invoice_link(self, amount: float) -> str:
        """
        تولید لینک پرداخت برای کاربر
        """
        pass

    @abstractmethod
    async def verify_transaction(self, expected_amount: float) -> Dict[
        str, Any]:
        """
        بررسی وضعیت تراکنش روی بلاکچین براساس مبلغ دقیق
        """
        pass