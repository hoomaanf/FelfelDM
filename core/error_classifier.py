# core/error_classifier.py
"""
Centralised error classification and summarisation.

Design notes (stability):
- Pure functions. No Qt, no I/O, no globals. Safe to call from any thread.
- Classification is driven first by aria2's numeric `errorCode` (exact),
  then falls back to substring matching on `errorMessage` (best-effort).
- The retry logic must depend on `.retriable` (a bool), never on the
  display label. Labels are presentation-only.
- `summarize` / `summarize_detailed` are deterministic and safe to call
  on malformed / partial history lists.
- `classify` can produce a result from `errorCode` alone, even when
  `errorMessage` is empty.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional


# ─────────────────────────────────────────────────────────────────────
# Categories
# ─────────────────────────────────────────────────────────────────────

class ErrorCategory(str, Enum):
    DNS = "dns"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    TLS = "tls"
    HTTP_4XX = "http_4xx"
    HTTP_5XX = "http_5xx"
    RATE_LIMIT = "rate_limit"
    DISK_IO = "disk_io"
    AUTH = "auth"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


# Categories that should never be retried automatically.
# Everything else is retriable by default.
_PERMANENT_CATEGORIES = frozenset({
    ErrorCategory.AUTH,
    ErrorCategory.NOT_FOUND,
    ErrorCategory.TLS,
    ErrorCategory.DISK_IO,
})


# ─────────────────────────────────────────────────────────────────────
# aria2 numeric error codes
# Source: aria2c(1) man page, EXIT STATUS section.
# ─────────────────────────────────────────────────────────────────────

_ARIA2_CODE_MAP: dict[int, ErrorCategory] = {
    1:  ErrorCategory.UNKNOWN,
    2:  ErrorCategory.TIMEOUT,
    3:  ErrorCategory.NOT_FOUND,
    4:  ErrorCategory.HTTP_5XX,
    5:  ErrorCategory.CONNECTION,
    6:  ErrorCategory.CONNECTION,
    7:  ErrorCategory.CONNECTION,
    8:  ErrorCategory.CONNECTION,
    9:  ErrorCategory.DISK_IO,
    10: ErrorCategory.CONNECTION,
    11: ErrorCategory.CONNECTION,
    12: ErrorCategory.CONNECTION,
    13: ErrorCategory.CONNECTION,
    14: ErrorCategory.CONNECTION,
    15: ErrorCategory.CONNECTION,
    16: ErrorCategory.DISK_IO,
    17: ErrorCategory.DISK_IO,
    18: ErrorCategory.DISK_IO,
    19: ErrorCategory.DNS,
    20: ErrorCategory.CONNECTION,
    21: ErrorCategory.CONNECTION,
    22: ErrorCategory.HTTP_5XX,
    23: ErrorCategory.CONNECTION,
    24: ErrorCategory.AUTH,
    25: ErrorCategory.CONNECTION,
    26: ErrorCategory.CONNECTION,
    27: ErrorCategory.CONNECTION,
    28: ErrorCategory.CONNECTION,
    29: ErrorCategory.HTTP_5XX,
    30: ErrorCategory.CONNECTION,
    31: ErrorCategory.CONNECTION,
    32: ErrorCategory.CONNECTION,
}


# ─────────────────────────────────────────────────────────────────────
# Textual rules (fallback when no numeric code, or for HTTP refinement)
# Order matters: first match wins. Specific before generic.
# ─────────────────────────────────────────────────────────────────────

_PATTERN_RULES: tuple[tuple[str, ErrorCategory], ...] = (
    # Auth / permission — permanent
    ("401", ErrorCategory.AUTH),
    ("unauthorized", ErrorCategory.AUTH),
    ("403", ErrorCategory.AUTH),
    ("forbidden", ErrorCategory.AUTH),
    ("authorization failed", ErrorCategory.AUTH),

    # Not found — permanent
    ("404", ErrorCategory.NOT_FOUND),
    ("not found", ErrorCategory.NOT_FOUND),
    ("410", ErrorCategory.NOT_FOUND),
    ("gone", ErrorCategory.NOT_FOUND),
    ("451", ErrorCategory.NOT_FOUND),

    # Rate limit — retriable
    ("429", ErrorCategory.RATE_LIMIT),
    ("too many requests", ErrorCategory.RATE_LIMIT),

    # 5xx — retriable
    ("500", ErrorCategory.HTTP_5XX),
    ("internal server error", ErrorCategory.HTTP_5XX),
    ("502", ErrorCategory.HTTP_5XX),
    ("bad gateway", ErrorCategory.HTTP_5XX),
    ("503", ErrorCategory.HTTP_5XX),
    ("service unavailable", ErrorCategory.HTTP_5XX),
    ("504", ErrorCategory.HTTP_5XX),
    ("gateway timeout", ErrorCategory.HTTP_5XX),

    # TLS / certificate — permanent, except transient TLS packet errors
    ("ssl/tls handshake failure", ErrorCategory.TLS),
    ("handshake failure", ErrorCategory.TLS),
    ("cert verify", ErrorCategory.TLS),
    ("certificate", ErrorCategory.TLS),
    ("tls packet", ErrorCategory.CONNECTION),  # transient variant

    # DNS — retriable
    ("name resolution", ErrorCategory.DNS),
    ("could not resolve", ErrorCategory.DNS),
    ("unable to resolve", ErrorCategory.DNS),
    ("could not contact dns", ErrorCategory.DNS),
    ("dns servers", ErrorCategory.DNS),
    ("no uri available", ErrorCategory.DNS),

    # Disk / IO — permanent
    ("no space left", ErrorCategory.DISK_IO),
    ("disk full", ErrorCategory.DISK_IO),
    ("file i/o error", ErrorCategory.DISK_IO),
    ("read-only file system", ErrorCategory.DISK_IO),

    # Timeout — retriable
    ("timeout", ErrorCategory.TIMEOUT),
    ("timed out", ErrorCategory.TIMEOUT),

    # Connection — retriable
    ("reset by peer", ErrorCategory.CONNECTION),
    ("refused", ErrorCategory.CONNECTION),
    ("eof from the server", ErrorCategory.CONNECTION),
    ("got eof", ErrorCategory.CONNECTION),
    ("no route", ErrorCategory.CONNECTION),
    ("unreachable", ErrorCategory.CONNECTION),
    ("resource temporarily", ErrorCategory.CONNECTION),
    ("try again", ErrorCategory.CONNECTION),
    ("error in the pull function", ErrorCategory.CONNECTION),
    ("pull function", ErrorCategory.CONNECTION),
    ("network", ErrorCategory.CONNECTION),
    ("connection", ErrorCategory.CONNECTION),
)


# ─────────────────────────────────────────────────────────────────────
# Display labels
# ─────────────────────────────────────────────────────────────────────

_LABELS: dict[ErrorCategory, str] = {
    ErrorCategory.DNS: "DNS resolution failed",
    ErrorCategory.TIMEOUT: "Connection timeout",
    ErrorCategory.CONNECTION: "Connection error",
    ErrorCategory.TLS: "TLS/certificate error",
    ErrorCategory.HTTP_4XX: "HTTP client error",
    ErrorCategory.HTTP_5XX: "Server error",
    ErrorCategory.RATE_LIMIT: "Rate limited",
    ErrorCategory.DISK_IO: "Disk I/O error",
    ErrorCategory.AUTH: "Authentication failed",
    ErrorCategory.NOT_FOUND: "File not found",
    ErrorCategory.UNKNOWN: "Download failed",
}

_SHORT: dict[ErrorCategory, str] = {
    ErrorCategory.DNS: "DNS",
    ErrorCategory.TIMEOUT: "Timeout",
    ErrorCategory.CONNECTION: "Connection",
    ErrorCategory.TLS: "TLS",
    ErrorCategory.HTTP_4XX: "HTTP 4xx",
    ErrorCategory.HTTP_5XX: "HTTP 5xx",
    ErrorCategory.RATE_LIMIT: "429",
    ErrorCategory.DISK_IO: "Disk I/O",
    ErrorCategory.AUTH: "Auth",
    ErrorCategory.NOT_FOUND: "Not found",
    ErrorCategory.UNKNOWN: "Unknown",
}


# ─────────────────────────────────────────────────────────────────────
# ClassifiedError
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ClassifiedError:
    category: ErrorCategory
    retriable: bool
    http_code: Optional[int] = None

    @property
    def label(self) -> str:
        """Full human-readable label (e.g. '404 File not found')."""
        base = _LABELS.get(self.category, "Download failed")
        if self.http_code is not None and 400 <= self.http_code < 600:
            return f"{self.http_code} {base}"
        return base
    
    @property
    def short(self) -> str:
        """Compact tag for the Status column (e.g. 'DNS')."""
        return _SHORT.get(self.category, "Unknown")


# ─────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────

_HTTP_CODE_RE = re.compile(r"\b([45]\d{2})\b")


def _extract_http_code(msg: str) -> Optional[int]:
    """Best-effort HTTP status extraction (e.g. 'HTTP Error 404' -> 404)."""
    if not msg:
        return None
    m = _HTTP_CODE_RE.search(msg)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _is_retriable(category: ErrorCategory) -> bool:
    return category not in _PERMANENT_CATEGORIES


def _refine_with_http_code(
    category: ErrorCategory, http_code: Optional[int]
) -> ErrorCategory:
    """If we found an HTTP status in the text, use it to refine the category.

    This handles cases where the generic rule matched something like
    "connection" but the actual HTTP status was 403 (auth) or 503 (5xx).
    """
    if http_code is None:
        return category

    # Don't override categories that are already more specific than HTTP.
    if category in (
        ErrorCategory.AUTH,
        ErrorCategory.NOT_FOUND,
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.DNS,
        ErrorCategory.TIMEOUT,
        ErrorCategory.TLS,
        ErrorCategory.DISK_IO,
    ):
        return category

    if 500 <= http_code < 600:
        return ErrorCategory.HTTP_5XX
    if 400 <= http_code < 500:
        return ErrorCategory.HTTP_4XX
    return category


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

def classify(
    error_msg: str = "",
    error_code: Optional[int] = None,
) -> ClassifiedError:
    """Classify a download error.

    Priority:
      1. aria2 numeric `errorCode` (exact, if provided and known).
      2. Substring rules on `errorMessage` (first match wins).
      3. Unknown.

    `errorCode` alone is enough: `errorMessage` may be empty.
    """
    # ── 1. Numeric code ──
    if error_code is not None:
        try:
            code = int(error_code)
        except (TypeError, ValueError):
            code = None
        if code is not None and code in _ARIA2_CODE_MAP:
            cat = _ARIA2_CODE_MAP[code]
            http_code = _extract_http_code(error_msg or "")
            cat = _refine_with_http_code(cat, http_code)
            return ClassifiedError(
                category=cat,
                retriable=_is_retriable(cat),
                http_code=http_code,
            )

    # ── 2. Textual rules ──
    msg = (error_msg or "").lower()
    if not msg:
        return ClassifiedError(
            category=ErrorCategory.UNKNOWN,
            retriable=True,
            http_code=None,
        )

    http_code = _extract_http_code(msg)

    for needle, category in _PATTERN_RULES:
        if needle in msg:
            category = _refine_with_http_code(category, http_code)
            return ClassifiedError(
                category=category,
                retriable=_is_retriable(category),
                http_code=http_code,
            )

    # ── 3. Unknown ──
    return ClassifiedError(
        category=ErrorCategory.UNKNOWN,
        retriable=True,
        http_code=http_code,
    )


def make_entry(
    error_msg: str = "",
    error_code: Optional[int] = None,
) -> dict:
    """Build a history entry. Pure; safe to call from any thread.

    The raw message is truncated to 2000 chars to bound storage size.
    Timestamp uses wall clock (time.time()); we never compare across
    processes, so monotonicity is not required.
    """
    ce = classify(error_msg, error_code)
    return {
        "category": ce.category.value,
        "raw": (error_msg or "")[:2000],
        "retriable": ce.retriable,
        "http_code": ce.http_code,
        "ts": time.time(),
    }


def summarize(history: Iterable[dict]) -> str:
    """Short summary for the Status column: 'DNS ×3, Timeout ×2'.

    Robust against malformed entries; skips anything it cannot parse.
    Returns an empty string when there is no history.
    """
    if not history:
        return ""

    counts: dict[ErrorCategory, int] = {}
    for entry in history:
        if not isinstance(entry, dict):
            continue
        try:
            cat = ErrorCategory(entry.get("category"))
        except (ValueError, TypeError):
            cat = ErrorCategory.UNKNOWN
        counts[cat] = counts.get(cat, 0) + 1

    if not counts:
        return ""

    order = {cat: i for i, cat in enumerate(ErrorCategory)}
    items = sorted(
        counts.items(), key=lambda kv: (-kv[1], order.get(kv[0], 999))
    )

    parts = []
    for cat, n in items:
        short = _SHORT[cat]
        parts.append(f"{short} ×{n}" if n > 1 else short)
    return ", ".join(parts)


def summarize_detailed(history: Iterable[dict]) -> str:
    """Multi-line summary for tooltips / dialogs.

    Format per category:
        <label> — <n>×
            last: <raw message>

    Categories are ordered by count (desc), then by category order.
    Returns an empty string when there is no history.
    """
    if not history:
        return ""

    groups: dict[ErrorCategory, dict] = {}
    for entry in history:
        if not isinstance(entry, dict):
            continue
        try:
            cat = ErrorCategory(entry.get("category"))
        except (ValueError, TypeError):
            cat = ErrorCategory.UNKNOWN

        g = groups.setdefault(cat, {"count": 0, "last_raw": "", "last_ts": 0.0})
        g["count"] += 1

        raw = entry.get("raw") or ""
        ts = entry.get("ts", 0.0)
        if not isinstance(ts, (int, float)):
            ts = 0.0
        if ts >= g["last_ts"]:
            g["last_ts"] = ts
            g["last_raw"] = raw

    order = {cat: i for i, cat in enumerate(ErrorCategory)}
    rows = sorted(
        groups.items(), key=lambda kv: (-kv[1]["count"], order.get(kv[0], 999))
    )

    lines = []
    for cat, g in rows:
        label = _LABELS[cat]
        count = g["count"]
        raw = (g["last_raw"] or "").strip()
        if len(raw) > 160:
            raw = raw[:157] + "..."

        if count > 1:
            head = f"{label} — {count}×"
        else:
            head = label

        if raw:
            lines.append(f"{head}\n    last: {raw}")
        else:
            lines.append(head)

    return "\n".join(lines)