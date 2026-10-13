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
            [c("A"), m("1.3"), m("1.1")],  # 1.1 cited for the retained working-day definition (D6)
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
        return Rule({"amount": DAILY_LIMIT, "or_bank_limit_if_lower": True}, [m("4.3"), c("E")],
                    ["Circular item E (effective 01 Aug 2026) amended clause 4.3: "
                     "₹1,00,000 or the customer's own bank limit, whichever is lower."])
    return Rule({"amount": DAILY_LIMIT, "or_bank_limit_if_lower": False}, [m("4.3")])


# ---------------------------------------------------------------- clause status

# master clause -> (circular item, effective date, what happened)
AMENDMENTS = {
    "1.1": ("A", CIRCULAR_EFFECTIVE, "replaced"),
    "2.1": ("B", CIRCULAR_EFFECTIVE, "replaced"),
    "2.3": ("C", CIRCULAR_EFFECTIVE, "replaced"),
    "3.3": ("D", CIRCULAR_D_EFFECTIVE, "deleted"),
    "4.3": ("E", CIRCULAR_EFFECTIVE, "amended"),
}


def clause_status(ref: str, as_of: date) -> Rule:
    """Is master clause `ref` in force on `as_of`, or replaced/deleted/amended by the circular?"""
    check_in_force(as_of)
    cites = [m(ref)]
    if ref in AMENDMENTS:
        item, eff, action = AMENDMENTS[ref]
        if as_of >= eff:
            cites.append(c(item))
            return Rule(action, cites,
                        [f"Circular MS/2026/17 item {item} {action} clause {ref} "
                         f"effective {eff:%d %b %Y}."])
        return Rule(f"in force (will be {action} by circular item {item} from {eff:%d %b %Y})",
                    cites + [c(item)] if as_of >= CIRCULAR_ISSUED else cites)
    return Rule("in force", cites)


# ---------------------------------------------------------------- closure

def closure_terms(as_of: date) -> Rule:
    check_in_force(as_of)
    return Rule({"notice_days": 30, "release_working_days": 10}, [m("5.1"), m("5.2")])
