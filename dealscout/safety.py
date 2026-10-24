"""Safety checks that run as plain Python (no model involved), so a prompt injection cannot talk its
way past them.

1. User input guard   - blocks direct prompt-injection / secret-stealing attempts in the chat box.
2. Untrusted text     - cleans web-derived text (hidden characters, HTML comments, injected orders).
3. Grounding checks   - a deal survives only if its link came from a real search result and its
                        quoted sentence actually supports the number the agent reported.
4. Secret redaction   - nothing that looks like an API key ever reaches the screen.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

from . import config

MAX_NOTE_CHARS = 400

# Phrases that try to change the agent's instructions or pull out secrets.
INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier|your) (instructions|rules|prompts?)",
    r"disregard (all |any |the )?(previous|prior|above|your) (instructions|rules)",
    r"forget (all |your )?(previous |prior )?(instructions|rules)",
    r"(system|developer) prompt",
    r"you are now\b",
    r"\bact as (an? )?(unrestricted|jailbroken|dan|admin)",
    r"developer mode|jailbreak|do anything now",
    r"(reveal|print|show|leak|send|output|repeat) (me )?(your |the )?(api[_ ]?key|secret|password|token|\.env|instructions|prompt)",
    r"portkey[_ ]?api[_ ]?key|openai[_ ]?api[_ ]?key",
    r"new instructions?:",
    r"(rate|rank|list|mark) (this|that) (deal|company) (as )?(the )?(best|#1|number one|top)",
    r"(visit|fetch|open|call|request) https?://\S+\?(\S*=)",
    r"<\s*/?\s*(system|assistant|instructions?)\s*>",
]
_INJ = [re.compile(p, re.I) for p in INJECTION_PATTERNS]
_ZERO_WIDTH = re.compile(r"[​-‏⁠-⁤﻿­]")
_KEYLIKE = re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_\-]{12,}\b")


@dataclass
class SafetyEvent:
    kind: str          # e.g. "blocked input", "injection removed", "fake link", "number mismatch"
    where: str         # which step / deal
    detail: str


@dataclass
class SafetyLog:
    events: list[SafetyEvent] = field(default_factory=list)

    def add(self, kind: str, where: str, detail: str) -> None:
        self.events.append(SafetyEvent(kind, where, redact(detail)[:300]))


def find_injection(text: str) -> str | None:
    """Return the suspicious phrase if the text contains one, else None."""
    flat = _ZERO_WIDTH.sub("", text or "")
    for rx in _INJ:
        m = rx.search(flat)
        if m:
            return m.group(0)
    return None


# ------------------------------------------------------------------ 1. user input guard
def check_user_note(note: str, log: SafetyLog) -> str:
    """The free-text box is the only place a user can type anything. Trim it, and refuse it if it
    looks like an attack. Returns the text that is safe to pass to the Scout."""
    note = _ZERO_WIDTH.sub("", (note or "").strip())[:MAX_NOTE_CHARS]
    hit = find_injection(note)
    if hit:
        log.add("blocked input", "user note", f"Removed the extra-instructions box because it contained: “{hit}”")
        return ""
    return note


# ------------------------------------------------------------------ 2. untrusted text from the web
def clean_untrusted(text: str, field_name: str, where: str, log: SafetyLog, limit: int = 400) -> str:
    """Text the Scout copied from web pages is data, not instructions. Strip hidden characters and
    markup; if it carries an injected order, drop the field and record it."""
    t = _ZERO_WIDTH.sub("", text or "")
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    t = re.sub(r"<[^>]{0,200}>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    hit = find_injection(t)
    if hit:
        log.add("injection removed", where, f"{field_name} contained “{hit}” – field discarded")
        return "[removed: suspicious text found in source]"
    return t[:limit]


def visible_page_text(html: str) -> str:
    """Turn a fetched page into the text a human would actually see: no scripts, styles, comments,
    hidden elements, or zero-width characters (the usual places attackers hide instructions)."""
    h = re.sub(r"(?is)<(script|style|noscript|template)\b.*?</\1>", " ", html)
    h = re.sub(r"(?s)<!--.*?-->", " ", h)
    hidden = r"(display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|opacity\s*:\s*0|left\s*:\s*-\d{3,}px)"
    h = re.sub(rf"(?is)<(\w+)[^>]*style\s*=\s*['\"][^'\"]*{hidden}[^'\"]*['\"][^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?is)<(\w+)[^>]*\bhidden\b[^>]*>.*?</\1>", " ", h)
    t = re.sub(r"<[^>]+>", " ", h)
    t = _ZERO_WIDTH.sub("", t)
    t = re.sub(r"&nbsp;|&#160;", " ", t)
    t = re.sub(r"&amp;", "&", t)
    return re.sub(r"\s+", " ", t)


# ------------------------------------------------------------------ 3. grounding checks
def _norm(url: str) -> str:
    p = urlparse((url or "").strip())
    host = p.netloc.lower().removeprefix("www.")
    return host + p.path.rstrip("/").lower()


def url_was_searched(url: str, searched: set[str], tool_urls: set[str]) -> bool:
    """True only if the link came back from a real web search or from our SEC tool."""
    n = _norm(url)
    if not n:
        return False
    pool = {_norm(u) for u in searched | tool_urls}
    return n in pool or any(n.startswith(p) or p.startswith(n) for p in pool if len(p) > 12)


_AMOUNT = re.compile(r"(?<![A-Za-z€£¥])(US\$|USD\s?|\$)\s?(\d[\d,]*(?:\.\d+)?)\s*(trillion|billion|bn|million|mn|m|b)?\b", re.I)
_FOREIGN = re.compile(r"(C\$|CA\$|A\$|AU\$|NZ\$|HK\$|S\$|€|£|¥|EUR|GBP|CAD|AUD|JPY)\s?\d", re.I)
_UNIT = {"trillion": 1e6, "billion": 1e3, "bn": 1e3, "b": 1e3, "million": 1, "mn": 1, "m": 1}


def usd_amounts(quote: str) -> list[float]:
    """Every US-dollar amount stated in a quote, in $ millions ('$3.45 billion' -> 3450).
    Amounts in other currencies (C$, €, £ ...) are ignored on purpose."""
    vals = []
    for m in _AMOUNT.finditer(quote or ""):
        num = float(m.group(2).replace(",", ""))
        mult = _UNIT.get((m.group(3) or "").lower())
        if mult is None:
            if num < 1e5:  # a bare "$500" is not a deal value
                continue
            mult = 1e-6
        vals.append(num * mult)
    return vals


def amount_in_quote(quote: str) -> float | None:
    vals = usd_amounts(quote)
    return max(vals) if vals else None


def quote_supports_value(value: float | None, quote: str) -> tuple[bool, str]:
    """Check the agent's number against its own quoted sentence: some US$ amount in the quote must
    match the reported value within 3%."""
    if value is None:
        return True, "value not disclosed"
    vals = usd_amounts(quote)
    if not vals:
        if _FOREIGN.search(quote or ""):
            return False, "the quote states the price only in a foreign currency"
        return False, "the quoted sentence states no dollar amount"
    for q in vals:
        if abs(q - value) <= max(0.03 * value, 1):
            return True, f"quote says ${q:,.0f}M"
    return False, f"agent said ${value:,.0f}M but the quote says ${max(vals):,.0f}M"


def fetch_and_match(url: str, quote: str, timeout: int = 12) -> tuple[str, str]:
    """Try to open the source ourselves and find the quote's key number in the visible text.
    Returns (status, detail): status is 'matched', 'not found on page', 'site blocked bots', or
    'page contains an injection attempt'. Page text is only ever compared with numbers here; it is
    never handed to a model."""
    headers = {"User-Agent": config.SEC_USER_AGENT if "sec.gov" in url else
               "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        return "site blocked bots", type(e).__name__
    if r.status_code != 200:
        return "site blocked bots", f"HTTP {r.status_code}"
    text = visible_page_text(r.text[:3_000_000])
    hit = find_injection(text)
    if hit:
        return "page contains an injection attempt", f"visible text says “{hit}”; page not trusted"
    nums = re.findall(r"\d[\d,]*(?:\.\d+)?", quote or "")
    nums = [n for n in nums if len(n.replace(",", "").replace(".", "")) >= 2]
    if not nums:
        return "not found on page", "no number to match"
    found = [n for n in nums if n in text]
    if found:
        return "matched", f"found {', '.join(found[:3])} on the page"
    return "not found on page", f"none of {', '.join(nums[:3])} appear in the page text"


# ------------------------------------------------------------------ 4. secrets
def redact(text: str) -> str:
    out = _KEYLIKE.sub("[redacted]", text or "")
    for name in ("PORTKEY_API_KEY", "OPENAI_API_KEY"):
        v = os.getenv(name, "")
        if len(v) >= 8:
            out = out.replace(v, "[redacted]")
    return out
