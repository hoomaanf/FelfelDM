"""Error translation for aria2 error codes to user-friendly messages
and auto-recovery strategies."""

from typing import Dict, Any, List, Optional


class ErrorHandler:
    """Translate aria2 error codes to user-friendly Persian messages
    with auto-recovery strategies."""

    ERROR_MAP: Dict[int, str] = {
        1: "خطای عمومی aria2. لطفاً لاگها را بررسی کنید.",
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

    # HIGH FIX: Auto-recovery strategies for common errors
    RECOVERY_STRATEGIES: Dict[int, str] = {
        3: "retry_connection",
        10: "check_disk_space",
        14: "retry_chunk",
        17: "retry_request",
        20: "retry_dns",
        22: "retry_connection",
    }

    def translate(self, code: int, message: str, method: str = "") -> str:
        base = self.ERROR_MAP.get(
            code,
            f"خطای aria2: {message} (کد: {code})"
        )
        if method:
            base += f" (در متد {method})"
        return base

    def get_recovery_strategy(self, code: int) -> Optional[str]:
        return self.RECOVERY_STRATEGIES.get(code)

    def should_retry(self, code: int, attempt: int, max_attempts: int = 5) -> bool:
        if attempt >= max_attempts:
            return False
        retryable_codes = {3, 14, 17, 20, 22}
        return code in retryable_codes

    def get_retry_delay(self, attempt: int, base_delay: float = 1.0) -> float:
        return min(base_delay * (2 ** attempt), 30.0)

    def get_recovery_action(self, code: int, context: Dict[str, Any]) -> Dict[str, Any]:
        strategy = self.get_recovery_strategy(code)
        action: Dict[str, Any] = {
            "strategy": strategy or "none",
            "retry": False,
            "delay": 0,
            "message": self.translate(code, "", ""),
        }

        if strategy in ("retry_connection", "retry_request", "retry_dns"):
            action["retry"] = True
            action["delay"] = 2.0
            action["message"] = "تلاش مجدد برای اتصال..."
        elif strategy == "check_disk_space":
            action["retry"] = False
            action["message"] = "فضای دیسک کافی نیست. لطفاً حداقل ۱۰۰ مگابایت فضا آزاد کنید."
        elif strategy == "retry_chunk":
            action["retry"] = True
            action["delay"] = 5.0
            action["message"] = "خطا در دانلود قطعه. تلاش مجدد..."

        return action
