"""
Error translation for aria2 error codes to user-friendly messages.
"""

from typing import Dict, Any


class ErrorHandler:
    """Translate aria2 error codes to user-friendly Persian messages."""

    ERROR_MAP: Dict[int, str] = {
        1: "خطای عمومی aria2. لطفاً لاگ‌ها را بررسی کنید.",
        2: "پارامترهای ارسالی به aria2 نامعتبر است.",
        3: "aria2 قادر به اتصال به سرور مقصد نیست.",
        4: "aria2 از سرور پاسخ غیرمنتظره دریافت کرد.",
        5: "خطا در اتمام دانلود (پایان غیرمنتظره).",
        6: "فایل مقصد از قبل وجود دارد یا قابل نوشتن نیست.",
        7: "خطا در ایجاد دایرکتوری مقصد.",
        8: "خطا در بازنویسی فایل (مشکل دسترسی).",
        9: "خطا در باز کردن فایل برای نوشتن.",
        10: "aria2 فضای کافی روی دیسک ندارد.",
        11: "فایل با checksum مطابقت ندارد. ممکن است فایل ناقص باشد.",
        12: "خطا در محاسبه checksum.",
        13: "خطا در اعتبارسنجی قطعه (chunk).",
        14: "خطا در دانلود قطعه (چون سرور قطع شده).",
        15: "خطا در باز کردن فایل موقت.",
        16: "خطا در خواندن فایل متادیتا.",
        17: "خطا در ارسال درخواست به سرور.",
        18: "خطا در دریافت پاسخ از سرور.",
        19: "فایل با checksum مطابقت ندارد.",
        20: "خطا در حل کردن نام دامنه.",
        21: "خطا در ایجاد socket.",
        22: "خطا در اتصال به سرور.",
        23: "خطا در TLS/SSL.",
        24: "احراز هویت aria2 ناموفق. رمز عبور را بررسی کنید.",
        25: "درخواست aria2 معتبر نیست (Bad Request).",
    }

    def translate(self, code: int, message: str, method: str = "") -> str:
        """Return a user-friendly error message."""
        base = self.ERROR_MAP.get(code, f"خطای aria2: {message} (کد: {code})")
        if method:
            base += f" (در متد {method})"
        return base
