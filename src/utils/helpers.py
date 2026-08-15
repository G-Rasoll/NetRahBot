import io
import logging

import qrcode
from qrcode.constants import ERROR_CORRECT_M

logger = logging.getLogger(__name__)


def format_bytes(size: int) -> str:
    if not size:
        return "0 B"
    power = 2 ** 10
    n = 0
    power_labels = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"


def generate_qr_bytes(data: str):
    """
    ساخت تصویر QR Code از روی متن/لینک ورودی، به صورت کاملاً لوکال و آفلاین
    (بدون هیچ تماس شبکه‌ای با سرویس‌های ثالث مثل api.qrserver.com).

    چرا لوکال به‌جای API خارجی؟
    ۱. امنیت/حریم خصوصی: لینک ساب هر کاربر عملاً یک توکن دسترسی خصوصی است.
       اگر آن را به یک API بیرونی (qrserver و مشابه) پاس بدهیم، آن سرویس ثالث
       این لینک را در لاگ‌ها/کش خودش ذخیره می‌کند؛ این یک ریسک امنیتی غیرضروری‌ست.
    ۲. سرعت و پایداری: هیچ Round-trip شبکه‌ی اضافه‌ای لازم نیست، پس نه Timeout
       سرویس ثالث گریبان ربات را می‌گیرد و نه کاربر منتظر یک HTTP Call اضافه می‌ماند.
    ۳. کم‌ریسک بودن: هیچ وابستگی جدیدی به یک سرویس بیرونی که ممکن است قطع،
       Rate-limit یا تغییر رفتار بدهد ایجاد نمی‌شود؛ کتابخانه‌ی qrcode آفلاین
       و کاملاً پایدار عمل می‌کند.

    Returns:
        io.BytesIO حاوی تصویر PNG در صورت موفقیت، یا None در صورت بروز هرگونه خطا
        (تا لایه‌ی بالادست بتواند Fallback امن به ارسال پیام متنی خالی بزند و
        ربات هرگز به‌خاطر خطای ساخت QR ریز/کرش نکند).
    """
    if not data:
        return None

    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        buffer.name = "netrah_subscription_qr.png"
        return buffer
    except Exception as e:
        logger.error(f"Error generating QR code locally: {e}", exc_info=True)
        return None
