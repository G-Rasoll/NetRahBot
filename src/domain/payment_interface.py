from abc import ABC, abstractmethod
from typing import Dict, Any

class PaymentGateway(ABC):

    @abstractmethod
    def create_invoice_link(self, amount: float, memo: str, expires_in_minutes: int = 15) -> str:
        """
        تولید لینک یا دکمه پرداخت برای کاربر
        :param amount: مقداری که کاربر باید پرداخت کند (به ارز مربوطه)
        :param memo: متن یا مموی منحصربه‌فرد برای رهگیری
        :param expires_in_minutes: زمان انقضای تراکنش
        :return: رشته متنی لینک پرداخت (مثلا ton://transfer/...)
        """
        pass

    @abstractmethod
    def verify_transaction(self, memo: str) -> Dict[str, Any]:
        """
        بررسی وضعیت تراکنش روی بلاکچین یا درگاه بانکی
        :param memo: همان مموی یکتایی که به تراکنش اختصاص داده بودیم
        :return: دیکشنری حاوی اطلاعات (status, amount_received, tx_hash)
        """
        pass