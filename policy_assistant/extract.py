"""Pull structured facts out of a free-text question with plain regexes.

Nothing here guesses: if a fact is not stated, the field stays None and the
assistant answers for every case (e.g. both merchant bands) instead.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from .rules import SMALL_BAND_MAX

_UNITS = {"lakh": Decimal("100000"), "lakhs": Decimal("100000"), "lac": Decimal("100000"),
          "crore": Decimal("10000000"), "cr": Decimal("10000000")}

# "₹1,50,000", "Rs.4,000", "Rs 10 lakh", "INR 2000"
_CURRENCY_RE = re.compile(
    r"(?:₹|\brs\.?|\binr)\s*(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lac|crore|cr)?\b", re.I)
# "1.5 lakh" with no currency symbol
_UNIT_RE = re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lac|crore|cr)\b", re.I)

_VOLUME_AFTER = re.compile(r"^\W*(monthly|per month|a month|in monthly|of monthly|volume|turnover)", re.I)
# the volume word must sit right before the amount: "monthly volume of ₹12 lakh", "turnover is ₹8 lakh"
_VOLUME_BEFORE = re.compile(
    r"(volume|turnover|monthly|per month|a month)\s*(of|is|was|at|about|around|=|:)?\s*"
    r"(above|over|more than|exceeding|greater than|up to|upto|below|under|less than|at most)?\s*$", re.I)
_ABOVE_BEFORE = re.compile(r"(above|over|more than|exceeding|greater than)\s*$", re.I)
_BELOW_BEFORE = re.compile(r"(up to|upto|below|under|less than|at most)\s*$", re.I)

_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
_DATE_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTHS})[a-z]*\.?,?\s+(\d{{4}})\b", re.I)
_DATE_MDY = re.compile(rf"\b({_MONTHS})[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

_HOURS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?)\b", re.I)
_MINUTES_RE = re.compile(r"(\d+)\s*(minutes?|mins?)\b", re.I)
_DAYS_RE = re.compile(r"(\d+)\s*days?\b", re.I)


@dataclass
class Facts:
    txn_amounts: list[Decimal] = field(default_factory=list)
    monthly_volume: Decimal | None = None
    large: bool | None = None          # None = merchant band not stated
    size_note: str | None = None       # set when stated word and stated volume disagree
    hours_after_sale: float | None = None
    dates: list[date] = field(default_factory=list)
    category: str | None = None        # "capital markets" / "insurance" / None
    enhanced_kyc: bool | None = None
    instant_addon: bool | None = None
    repeat_count: int = 1              # "twice" -> 2


def _to_decimal(num: str, unit: str | None) -> Decimal:
    value = Decimal(num.replace(",", ""))
    return value * _UNITS[unit.lower()] if unit else value


def _month_num(token: str) -> int:
    return datetime.strptime(token[:3].title(), "%b").month


def parse_date(text: str) -> date | None:
    """Parse one date string: ISO, '20 Aug 2026', 'August 20, 2026'."""
    found = find_dates(text)
    return found[0] if found else None


def find_dates(text: str) -> list[date]:
    hits: list[tuple[int, date]] = []
    for m in _DATE_ISO.finditer(text):
        hits.append((m.start(), date(int(m[1]), int(m[2]), int(m[3]))))
    for m in _DATE_DMY.finditer(text):
        hits.append((m.start(), date(int(m[3]), _month_num(m[2]), int(m[1]))))
    for m in _DATE_MDY.finditer(text):
        hits.append((m.start(), date(int(m[3]), _month_num(m[1]), int(m[2]))))
    out: list[date] = []
    for _, d in sorted(hits):
        if d not in out:
            out.append(d)
    return out


def _amounts(q: str) -> list[tuple[int, int, Decimal]]:
    spans: list[tuple[int, int, Decimal]] = []
    for rx in (_CURRENCY_RE, _UNIT_RE):
        for m in rx.finditer(q):
            if any(s <= m.start() < e for s, e, _ in spans):
                continue
            spans.append((m.start(), m.end(), _to_decimal(m.group(1), m.group(2))))
    return sorted(spans)


def extract(question: str) -> Facts:
    q = question
    low = q.lower()
    f = Facts()

    band_hint: str | None = None
    for start, end, value in _amounts(q):
        before, after = q[max(0, start - 30):start], q[end:end + 30]
        if _VOLUME_AFTER.search(after) or _VOLUME_BEFORE.search(before):
            f.monthly_volume = value
            if _ABOVE_BEFORE.search(before):
                band_hint = "above"
            elif _BELOW_BEFORE.search(before):
                band_hint = "below"
        else:
            f.txn_amounts.append(value)

    # Merchant band: the policy defines it by monthly volume (D11); words are a fallback.
    if f.monthly_volume is not None:
        if band_hint == "above":
            f.large = f.monthly_volume >= SMALL_BAND_MAX
        elif band_hint == "below":
            f.large = f.monthly_volume > SMALL_BAND_MAX
        else:
            f.large = f.monthly_volume > SMALL_BAND_MAX
        word = "large" if re.search(r"\b(large|big)\b", low) else "small" if re.search(r"\bsmall\b", low) else None
        if word and (word == "large") != f.large:
            f.size_note = (f"The question calls the merchant '{word}', but the policy bands by monthly "
                           f"volume, so the stated volume decides.")
    elif re.search(r"\b(large|big)\b", low):
        f.large = True
    elif re.search(r"\bsmall\b", low):
        f.large = False

    if (m := _HOURS_RE.search(q)):
        f.hours_after_sale = float(m.group(1))
    elif (m := _MINUTES_RE.search(q)):
        f.hours_after_sale = int(m.group(1)) / 60
    elif re.search(r"refund", low) and (m := _DAYS_RE.search(q)):
        f.hours_after_sale = int(m.group(1)) * 24.0
    elif re.search(r"\b(same day|immediately|right away|straight away)\b", low):
        f.hours_after_sale = 0.0
    elif re.search(r"\b(next day|following day)\b", low):
        f.hours_after_sale = None  # could be under or over 24h: left unknown on purpose

    f.dates = find_dates(q)

    if "capital market" in low:
        f.category = "capital markets"
    elif "insurance" in low:
        f.category = "insurance"

    if "kyc" in low:
        neg = re.search(r"(without|no|not|hasn'?t|haven'?t|never|pending|incomplete)\b[^.]{0,30}kyc", low)
        f.enhanced_kyc = False if neg else (True if "enhanced kyc" in low else None)

    if "instant settlement" in low or "add-on" in low or "addon" in low:
        f.instant_addon = not re.search(r"(without|no|not|don'?t have)\b[^.]{0,30}(instant|add-?on)", low)

    if re.search(r"\b(twice|two times|2 times|two payments|two transactions)\b", low):
        f.repeat_count = 2
    elif re.search(r"\b(three times|thrice|3 times)\b", low):
        f.repeat_count = 3
    return f
