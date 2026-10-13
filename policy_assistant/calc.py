"""Deterministic fee arithmetic. Decimal only, rounded half-up to the paisa (DECISIONS D13, D14)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

PAISA = Decimal("0.01")
GST_RATE = Decimal("0.18")  # clause 2.4


def money(x: Decimal | int | str) -> Decimal:
    return Decimal(x).quantize(PAISA, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Fee:
    amount: Decimal
    rate: Decimal        # e.g. Decimal("0.005") for 0.50%
    cap: Decimal
    uncapped_mdr: Decimal
    mdr: Decimal
    gst: Decimal

    @property
    def capped(self) -> bool:
        return self.uncapped_mdr > self.cap

    @property
    def total(self) -> Decimal:
        return self.mdr + self.gst


def compute_fee(amount: Decimal | int | str, rate: Decimal, cap: Decimal) -> Fee:
    """MDR = min(rate * amount, cap); GST = 18% of MDR, outside the cap (2.4)."""
    amount = Decimal(amount)
    if amount <= 0:
        raise ValueError("amount must be positive")
    uncapped = money(amount * rate)
    mdr = min(uncapped, money(cap))
    return Fee(amount, rate, money(cap), uncapped, mdr, money(mdr * GST_RATE))


def inr(x: Decimal | int) -> str:
    """Format with Indian digit grouping: 150000 -> ₹1,50,000; 23.6 -> ₹23.60."""
    x = Decimal(x)
    whole, frac = divmod(abs(x), 1)
    digits = str(int(whole))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    sign = "-" if x < 0 else ""
    if frac:
        return f"{sign}₹{digits}.{str(money(frac))[2:]}"
    return f"{sign}₹{digits}"


def pct(rate: Decimal) -> str:
    return f"{(rate * 100).quantize(PAISA)}%"
