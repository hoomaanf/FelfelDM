# core/rule_engine.py

"""
Download Rules Engine for FelfelDM.

Rules let the user define conditions (URL/extension/size/domain) and
actions (queue/folder/connections/speed) that are applied automatically
when a new download is added.

Example:
    IF url_contains == ".iso"
    THEN queue = "Linux", folder = "~/Downloads/ISO"
"""

import os
import re
import uuid
from typing import Dict, List, Optional, Any


class Rule:
    """
    A single download rule.

    Conditions (all must match — AND logic):
        url_contains:  substring match (case-insensitive)
        url_matches:   regex pattern
        extension:     file extension (with or without dot)
        domain:        hostname (e.g. "github.com", supports "*.example.com")
        size_min:      minimum size in bytes
        size_max:      maximum size in bytes

    Actions (applied in this order, first non-empty wins):
        queue:         name of target queue
        folder:        save path (supports ~ expansion)
        connections:   number of connections (1-16)
        speed_limit:   per-download speed limit in KB/s (0 = unlimited)
    """

    def __init__(
        self,
        rule_id: Optional[str] = None,
        name: str = "New Rule",
        enabled: bool = True,
        url_contains: str = "",
        url_matches: str = "",
        extension: str = "",
        domain: str = "",
        size_min: int = 0,
        size_max: int = 0,
        queue: str = "",
        folder: str = "",
        connections: int = 0,
        speed_limit: int = 0,
    ):
        self.id = rule_id or uuid.uuid4().hex[:12]
        self.name = name
        self.enabled = enabled

        # Conditions
        self.url_contains = (url_contains or "").strip()
        self.url_matches = (url_matches or "").strip()
        self.extension = (extension or "").strip().lstrip(".").lower()
        self.domain = (domain or "").strip().lower()
        self.size_min = max(0, int(size_min or 0))
        self.size_max = max(0, int(size_max or 0))

        # Actions
        self.queue = (queue or "").strip()
        self.folder = (folder or "").strip()
        self.connections = max(0, min(16, int(connections or 0)))
        self.speed_limit = max(0, int(speed_limit or 0))

    # ─────────────────────────────────────────────
    # Serialization
    # ─────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "url_contains": self.url_contains,
            "url_matches": self.url_matches,
            "extension": self.extension,
            "domain": self.domain,
            "size_min": self.size_min,
            "size_max": self.size_max,
            "queue": self.queue,
            "folder": self.folder,
            "connections": self.connections,
            "speed_limit": self.speed_limit,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Rule":
        return cls(
            rule_id=d.get("id"),
            name=d.get("name", "New Rule"),
            enabled=bool(d.get("enabled", True)),
            url_contains=d.get("url_contains", ""),
            url_matches=d.get("url_matches", ""),
            extension=d.get("extension", ""),
            domain=d.get("domain", ""),
            size_min=d.get("size_min", 0),
            size_max=d.get("size_max", 0),
            queue=d.get("queue", ""),
            folder=d.get("folder", ""),
            connections=d.get("connections", 0),
            speed_limit=d.get("speed_limit", 0),
        )

    # ─────────────────────────────────────────────
    # Matching
    # ─────────────────────────────────────────────

    def has_any_condition(self) -> bool:
        return bool(
            self.url_contains
            or self.url_matches
            or self.extension
            or self.domain
            or self.size_min > 0
            or self.size_max > 0
        )

    def has_any_action(self) -> bool:
        return bool(
            self.queue or self.folder or self.connections > 0 or self.speed_limit > 0
        )

    def matches(self, url: str, size: Optional[int] = None) -> bool:
        """
        Check if this rule matches the given URL (and optional size).
        Empty conditions are ignored (i.e. not evaluated).
        If ALL conditions are empty, the rule is considered non-matching.
        """
        if not self.enabled:
            return False

        if not self.has_any_condition():
            return False

        # url_contains
        if self.url_contains:
            if self.url_contains.lower() not in url.lower():
                return False

        # url_matches (regex)
        if self.url_matches:
            try:
                if not re.search(self.url_matches, url, re.IGNORECASE):
                    return False
            except re.error:
                # Invalid regex → don't match
                return False

        # extension
        if self.extension:
            # Extract filename without query
            filename = url.split("/")[-1].split("?")[0]
            if "." not in filename:
                return False
            ext = filename.rsplit(".", 1)[-1].lower()
            if ext != self.extension:
                return False

        # domain
        if self.domain:
            host = self._extract_host(url)
            if not host:
                return False
            if not self._domain_matches(host, self.domain):
                return False

        # size (only evaluated if size is provided)
        if size is not None and size > 0:
            if self.size_min > 0 and size < self.size_min:
                return False
            if self.size_max > 0 and size > self.size_max:
                return False

        return True

    @staticmethod
    def _extract_host(url: str) -> str:
        """Extract hostname from URL."""
        try:
            # Remove scheme
            if "://" in url:
                rest = url.split("://", 1)[1]
            else:
                rest = url
            # Remove path
            host = rest.split("/", 1)[0]
            # Remove userinfo
            if "@" in host:
                host = host.split("@", 1)[1]
            # Remove port
            if ":" in host:
                host = host.split(":", 1)[0]
            return host.lower()
        except Exception:
            return ""

    @staticmethod
    def _domain_matches(host: str, pattern: str) -> bool:
        """
        Match host against a domain pattern.
        Supports:
            "github.com"      → exact match
            "*.github.com"    → subdomain match
            ".github.com"     → any subdomain (github.com or *.github.com)
        """
        if pattern.startswith("*."):
            base = pattern[2:]
            return host == base or host.endswith("." + base)
        if pattern.startswith("."):
            base = pattern[1:]
            return host == base or host.endswith("." + base)
        # Exact match
        return host == pattern


class RuleEngine:
    """Manages a list of rules and applies them to new downloads."""

    def __init__(self, rules: Optional[List[Rule]] = None):
        self.rules: List[Rule] = list(rules or [])

    def load(self, rules_data: List[Dict[str, Any]]) -> None:
        self.rules = []
        for r in rules_data or []:
            try:
                self.rules.append(Rule.from_dict(r))
            except Exception as e:
                print(f"⚠️ [Rules] Failed to load rule: {e}")

    def to_dict_list(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self.rules]

    def find_match(self, url: str, size: Optional[int] = None) -> Optional[Rule]:
        """
        Find the first rule that matches the URL.
        Rules are evaluated in order (top-to-bottom).
        """
        for rule in self.rules:
            if rule.matches(url, size):
                return rule
        return None

    # ─────────────────────────────────────────────
    # CRUD
    # ─────────────────────────────────────────────

    def add(self, rule: Rule) -> None:
        self.rules.append(rule)

    def remove(self, rule_id: str) -> bool:
        for i, r in enumerate(self.rules):
            if r.id == rule_id:
                del self.rules[i]
                return True
        return False

    def get(self, rule_id: str) -> Optional[Rule]:
        for r in self.rules:
            if r.id == rule_id:
                return r
        return None

    def update(self, rule_id: str, new_rule: Rule) -> bool:
        for i, r in enumerate(self.rules):
            if r.id == rule_id:
                self.rules[i] = new_rule
                return True
        return False

    def move_up(self, rule_id: str) -> bool:
        for i, r in enumerate(self.rules):
            if r.id == rule_id and i > 0:
                self.rules[i - 1], self.rules[i] = self.rules[i], self.rules[i - 1]
                return True
        return False

    def move_down(self, rule_id: str) -> bool:
        for i, r in enumerate(self.rules):
            if r.id == rule_id and i < len(self.rules) - 1:
                self.rules[i + 1], self.rules[i] = self.rules[i], self.rules[i + 1]
                return True
        return False


# ─────────────────────────────────────────────
# Helpers for the UI
# ─────────────────────────────────────────────


def parse_size(text: str) -> int:
    """
    Parse a human-readable size like '5G', '500M', '2.5 GB' into bytes.
    Returns 0 if invalid or empty.
    """
    if not text:
        return 0
    text = text.strip().upper().replace(" ", "")
    match = re.match(r"^([\d.]+)\s*(B|KB|MB|GB|TB|K|M|G|T)?$", text)
    if not match:
        return 0
    try:
        num = float(match.group(1))
    except ValueError:
        return 0
    unit = match.group(2) or "B"
    multipliers = {
        "B": 1,
        "K": 1024,
        "KB": 1024,
        "M": 1024**2,
        "MB": 1024**2,
        "G": 1024**3,
        "GB": 1024**3,
        "T": 1024**4,
        "TB": 1024**4,
    }
    return int(num * multipliers.get(unit, 1))


def format_size_human(num_bytes: int) -> str:
    """Format bytes to human readable."""
    if num_bytes <= 0:
        return ""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            if unit == "B":
                return f"{int(num_bytes)}{unit}"
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}PB"


def expand_path(path: str) -> str:
    """Expand ~ and env vars in a path."""
    if not path:
        return ""
    return os.path.expandvars(os.path.expanduser(path))
