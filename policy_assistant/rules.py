"""Date-versioned policy rules.

Each function answers "what does the policy in force on `as_of` say about X?" and returns
the value together with the clauses it rests on and any supersession that happened
(old clause -> new clause), so the assistant can report CONFLICT_RESOLVED honestly.

Dates come from the document headers (DECISIONS D1-D4). Effective dates are inclusive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .corpus import CIRCULAR, MASTER, Citation, cite

MASTER_EFFECTIVE = date(2026, 1, 1)
CIRCULAR_ISSUED = date(2026, 7, 20)
CIRCULAR_EFFECTIVE = date(2026, 8, 1)       # items A, B, C, E
CIRCULAR_D_EFFECTIVE = date(2026, 9, 1)     # item D only (deletion of 3.3)

SMALL_BAND_MAX = Decimal("1000000")         # "up to ₹10 lakh" (inclusive), D11
PER_TXN_LIMIT = Decimal("100000")           # 4.1
ENHANCED_TXN_LIMIT = Decimal("200000")      # 4.2 (subject to 4.4)
DAILY_LIMIT = Decimal("100000")             # 4.3 / circular E
ENHANCED_CATEGORIES = ("capital markets", "insurance")


class PolicyNotInForce(Exception):
    """as_of_date precedes every document (D4)."""


@dataclass
class Rule:
    value: object
    citations: list[Citation]
    supersessions: list[str] = field(default_factory=list)  # human-readable "how resolved"


def m(ref: str) -> Citation:
    return cite(MASTER, ref)


def c(ref: str) -> Citation:
    return cite(CIRCULAR, ref)


def check_in_force(as_of: date) -> None:
    if as_of < MASTER_EFFECTIVE:
        raise PolicyNotInForce(
            f"No policy document is in force on {as_of:%d %b %Y}; "
            f"Master v1.0 takes effect {MASTER_EFFECTIVE:%d %b %Y}.")


def circular_in_force(as_of: date) -> bool:
    return as_of >= CIRCULAR_EFFECTIVE


def circular_d_in_force(as_of: date) -> bool:
    return as_of >= CIRCULAR_D_EFFECTIVE


# ---------------------------------------------------------------- settlement

def upi_settlement(as_of: date) -> Rule:
    check_in_force(as_of)
    if circular_in_force(as_of):
        return Rule(
            {"instant_addon": "T+0 (same day, by 11:59 PM)", "default": "T+1 (next working day)"},
            [c("A"), m("1.3")],
            ["Circular MS/2026/17 item A (effective 01 Aug 2026) replaced master clause 1.1."],
        )
    return Rule({"instant_addon": None, "default": "T+1 (next working day)"}, [m("1.1"), m("1.3")])


def card_settlement(as_of: date) -> Rule:
    check_in_force(as_of)
    return Rule("T+2", [m("1.2"), m("1.3")])


# ---------------------------------------------------------------- MDR

def mdr_terms(as_of: date, large: bool) -> Rule:
    """Rate and cap for a merchant band on a date (DECISIONS D12)."""
    check_in_force(as_of)
    notes: list[str] = []
    if large:
        rate, cites = Decimal("0.005"), [m("2.2")]
    elif circular_in_force(as_of):
        rate, cites = Decimal("0.0025"), [c("B")]
        notes.append("Circular item B (effective 01 Aug 2026) replaced clause 2.1: 0.30% -> 0.25%.")
    else:
        rate, cites = Decimal("0.003"), [m("2.1")]

    if circular_in_force(as_of):
        cap = Decimal("25") if large else Decimal("15")
        cites.append(c("C"))
        notes.append("Circular item C (effective 01 Aug 2026) replaced clause 2.3: "
                     "cap ₹15 up to ₹10 lakh monthly volume, ₹25 above.")
    else:
        cap = Decimal("15")
        cites.append(m("2.3"))
    cites.append(m("2.4"))
    return Rule({"rate": rate, "cap": cap}, cites, notes)


def is_large(monthly_volume: Decimal) -> bool:
    return monthly_volume > SMALL_BAND_MAX


# ---------------------------------------------------------------- refunds

def refund_mdr_reversed(as_of: date, hours_after_sale: float | None) -> Rule:
    """Is MDR returned on a refund made `hours_after_sale` after the sale? (D15-D18)"""
    check_in_force(as_of)
    if circular_d_in_force(as_of):
        return Rule(False, [m("3.2"), c("D")],
                    ["Circular item D deleted clause 3.3 effective 01 Sep 2026; "
                     "clause 3.2 now applies without exception."])
    if hours_after_sale is not None and hours_after_sale <= 24:
        return Rule(True, [m("3.3"), m("3.2")])
    return Rule(False, [m("3.2")])


def refund_window_days(as_of: date) -> Rule:
    check_in_force(as_of)
    return Rule(90, [m("3.1")])


# ---------------------------------------------------------------- limits

def per_txn_limit(as_of: date) -> Rule:
    check_in_force(as_of)
    return Rule({"standard": PER_TXN_LIMIT, "enhanced": ENHANCED_TXN_LIMIT,
                 "enhanced_categories": ENHANCED_CATEGORIES},
                [m("4.1"), m("4.2"), m("4.4")])


def daily_limit(as_of: date) -> Rule:
    check_in_force(as_of)
    if circular_in_force(as_of):
        return Rule({"amount": DAILY_LIMIT, "or_bank_limit_if_lower": True}, [c("E")],
                    ["Circular item E (effective 01 Aug 2026) amended clause 4.3: "
                     "₹1,00,000 or the customer's own bank limit, whichever is lower."])
    return Rule({"amount": DAILY_LIMIT, "or_bank_limit_if_lower": False}, [m("4.3")])


# ---------------------------------------------------------------- closure

def closure_terms(as_of: date) -> Rule:
    check_in_force(as_of)
    return Rule({"notice_days": 30, "release_working_days": 10}, [m("5.1"), m("5.2")])
