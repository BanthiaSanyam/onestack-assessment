"""ask(question, as_of_date) -> Answer.

Routing is hand-written keyword rules (DECISIONS D27). Every handler gets its facts from
`rules` (date-versioned) and its numbers from `calc` (Decimal), so the answer text is
assembled from verified pieces only. Anything not matched returns CANNOT_ANSWER.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from . import rules
from .calc import compute_fee, inr, pct
from .corpus import MASTER, Citation, faq_cite, text_of
from .extract import Facts, extract, parse_date

ANSWERED = "ANSWERED"
CONFLICT_RESOLVED = "CONFLICT_RESOLVED"
CANNOT_ANSWER = "CANNOT_ANSWER"

DEFAULT_AS_OF = date(2026, 8, 15)


@dataclass
class Answer:
    answer: str
    citations: list[Citation]
    status: str
    resolution: str | None = None
    as_of_date: date | None = None

    def to_dict(self) -> dict:
        return {"as_of_date": self.as_of_date.isoformat() if self.as_of_date else None,
                "status": self.status, "answer": self.answer,
                "citations": [str(c) for c in self.citations], "resolution": self.resolution}


class _Builder:
    """Collects answer lines, citations (deduped, ordered) and conflict-resolution notes."""

    def __init__(self, as_of: date):
        self.as_of = as_of
        self.lines: list[str] = []
        self.cites: list[Citation] = []
        self.notes: list[str] = []

    def say(self, text: str) -> None:
        self.lines.append(text)

    def cite(self, *cs: Citation) -> None:
        for c in cs:
            if c not in self.cites:
                self.cites.append(c)

    def use(self, rule: rules.Rule):
        self.cite(*rule.citations)
        for n in rule.supersessions:
            if n not in self.notes:
                self.notes.append(n)
        return rule.value

    def conflict(self, note: str, *cs: Citation) -> None:
        self.cite(*cs)
        if note not in self.notes:
            self.notes.append(note)

    def build(self, status: str | None = None) -> Answer:
        if status is None:
            status = CONFLICT_RESOLVED if self.notes else ANSWERED
        return Answer(" ".join(self.lines), self.cites, status,
                      " ".join(self.notes) or None, self.as_of)


def _cannot(as_of: date, reason: str, *cs: Citation) -> Answer:
    return Answer(f"CANNOT_ANSWER: {reason}", list(cs), CANNOT_ANSWER, None, as_of)


def _has(q: str, *patterns: str) -> bool:
    return any(re.search(p, q) for p in patterns)


def _upcoming_circular_note(b: _Builder) -> None:
    if rules.CIRCULAR_ISSUED <= b.as_of < rules.CIRCULAR_EFFECTIVE:
        b.say("Note: Circular MS/2026/17 (issued 20 Jul 2026) changes settlement, MDR and limits "
              "from 01 Aug 2026; it is not yet in force on this date.")


# ===================================================================== FAQ checks
# Each returns (faq_citation, faq_claim, verdict, is_wrong) for the policy in force on `d`.

def _faq_fees(d: date):
    cite = faq_cite("What do I pay")
    small = rules.mdr_terms(d, large=False).value
    large = rules.mdr_terms(d, large=True).value
    verdict = (f"Wrong. There is an upper limit and there has been since Master v1.0 took effect on "
               f"01 Jan 2026 (clause 2.3 capped MDR at ₹15 per transaction). On {d:%d %b %Y} the cap is "
               f"{inr(small['cap'])} for merchants up to ₹10 lakh monthly volume and "
               f"{inr(large['cap'])} above ₹10 lakh")
    verdict += " (circular item C)." if rules.circular_in_force(d) else " (clause 2.3)."
    if rules.circular_in_force(d):
        verdict += (f" The 0.30% small-merchant rate is also stale: it is {pct(small['rate'])} "
                    f"from 01 Aug 2026 (circular item B).")
    verdict += " The FAQ also omits the 18% GST charged on top of MDR (clause 2.4)."
    return cite, True, verdict


def _faq_settlement(d: date):
    cite = faq_cite("UPI money")
    if rules.circular_in_force(d):
        return cite, True, ("Partly stale. From 01 Aug 2026 merchants with the Instant Settlement add-on "
                            "get UPI money T+0 (same day, by 11:59 PM) under circular item A; others still "
                            "get T+1. The card answer (two working days) matches clause 1.2.")
    return cite, False, "Correct on this date: UPI T+1 (clause 1.1), cards T+2 (clause 1.2)."


def _faq_refund(d: date):
    cite = faq_cite("refund")
    if rules.circular_d_in_force(d):
        return cite, True, ("Stale. Circular item D deleted clause 3.3 from 01 Sep 2026; MDR on a refunded "
                            "transaction is no longer returned, even within 24 hours (clause 3.2).")
    return cite, False, "Correct on this date: MDR is reversed in full for a refund within 24 hours (clause 3.3)."


def _faq_limits(d: date):
    cite = faq_cite("maximum amount")
    daily = rules.daily_limit(d).value
    tail = " or the customer's own bank limit, whichever is lower" if daily["or_bank_limit_if_lower"] else ""
    return cite, True, ("Incomplete. The ₹2,00,000 limit for Insurance and Capital Markets merchants applies "
                        "only after enhanced KYC (clause 4.4), and the FAQ ignores the daily limit of "
                        f"₹1,00,000 per customer account{tail} (clause 4.3"
                        + (" as amended by circular item E)." if daily["or_bank_limit_if_lower"] else ")."))


def _faq_closure(d: date):
    cite = faq_cite("close my account")
    return cite, True, ("Imprecise. Pending settlements are released within 10 *working* days of closure, "
                        "after deducting outstanding dues (clause 5.2), not '10 days'. "
                        "The 30 days' notice is correct (clause 5.1).")


def _faq_policy_cites(d: date, topic: str) -> list[Citation]:
    m = rules.m
    if topic == "fees":
        return rules.mdr_terms(d, False).citations + rules.mdr_terms(d, True).citations
    if topic == "settlement":
        return rules.upi_settlement(d).citations + [m("1.2")]
    if topic == "refund":
        return rules.refund_mdr_reversed(d, 1).citations
    if topic == "limits":
        return rules.per_txn_limit(d).citations + rules.daily_limit(d).citations
    return rules.closure_terms(d).citations


_FAQ_TOPICS = [
    ("fees", (r"\bcap\b", r"\bmdr\b", r"\bfee", r"\bcharge", r"\bpay on\b", r"\brate\b", r"upper limit"), _faq_fees),
    ("refund", (r"refund",), _faq_refund),
    ("settlement", (r"settle", r"\bupi money\b", r"when will i get", r"receive"), _faq_settlement),
    ("limits", (r"\blimit", r"maximum", r"how much can"), _faq_limits),
    ("closure", (r"\bclos",), _faq_closure),
]


def _handle_faq(q: str, b: _Builder) -> Answer:
    topics = [t for t in _FAQ_TOPICS if _has(q, *t[1])] or _FAQ_TOPICS
    wrong_any = False
    for name, _, check in topics[:1] if len(topics) < len(_FAQ_TOPICS) else topics:
        cite, wrong, verdict = check(b.as_of)
        b.cite(cite, *_faq_policy_cites(b.as_of, name))
        b.say(f'The FAQ (updated 12 Mar 2026) says: "{text_of(cite)}" Verdict: {verdict}')
        wrong_any |= wrong
        if wrong:
            b.notes.append(f"FAQ answer on '{cite.ref}' conflicts with the policy in force on "
                           f"{b.as_of:%d %b %Y}; the policy documents take precedence over the FAQ.")
    return b.build()


# ===================================================================== topic handlers

def _handle_clause(ref: str, b: _Builder) -> Answer:
    try:
        status = rules.clause_status(ref, b.as_of)
    except KeyError:
        return _cannot(b.as_of, f"There is no clause {ref} in the Merchant Services Policy Master v1.0.")
    value = b.use(status)
    b.say(f'Clause {ref} (Master v1.0) reads: "{text_of(rules.m(ref))}"')
    b.say(f"Status on {b.as_of:%d %b %Y}: {value}.")
    if ref in rules.AMENDMENTS and value in ("replaced", "amended"):
        item = rules.AMENDMENTS[ref][0]
        b.say(f'Current text (circular item {item}): "{text_of(rules.c(item))}"')
    return b.build()


def _handle_settlement(q: str, f: Facts, b: _Builder) -> Answer:
    card = _has(q, r"\bcards?\b", r"credit", r"debit")
    upi = _has(q, r"\bupi\b")
    if card and not upi:
        b.use(rules.card_settlement(b.as_of))
        if _has(q, r"same day", r"\bt\s*\+\s*0\b", r"instant", r"today", r"immediate"):
            b.say("No. Card transactions settle T+2 (clause 1.2), moved to the next working day if that "
                  "falls on a bank holiday (clause 1.3). The same-day (T+0) option in circular item A "
                  "applies only to UPI with the Instant Settlement add-on, not to cards.")
            if rules.circular_in_force(b.as_of):
                b.cite(rules.c("A"))
        else:
            b.say("Card transactions settle T+2 (clause 1.2); if the settlement date is a bank holiday "
                  "it moves to the next working day (clause 1.3).")
        return b.build()

    v = b.use(rules.upi_settlement(b.as_of))
    if v["instant_addon"]:
        if f.instant_addon is True:
            b.say(f"With the Instant Settlement add-on, UPI money is settled {v['instant_addon']} "
                  "(circular item A).")
        elif f.instant_addon is False:
            b.say(f"Without the Instant Settlement add-on, UPI money is settled {v['default']} "
                  "(circular item A).")
        else:
            b.say(f"UPI settlement is {v['default']} for most merchants, or {v['instant_addon']} if the "
                  "merchant has an active Instant Settlement add-on (circular item A). It depends on the "
                  "add-on, not on merchant size.")
        b.say("Working days exclude Sundays and bank holidays (definition from original clause 1.1, "
              "retained because clause 1.3 still relies on it); a settlement date on a bank holiday "
              "moves to the next working day (clause 1.3).")
        cite, wrong, _ = _faq_settlement(b.as_of)
        if wrong:
            b.conflict("The FAQ ('next working day' for everyone) predates circular item A and is stale "
                       "for add-on merchants.", cite)
    else:
        b.say(f"UPI settlement is {v['default']} (clause 1.1); working days exclude Sundays and bank "
              "holidays, and a settlement date on a bank holiday moves to the next working day (clause 1.3).")
        _upcoming_circular_note(b)
    if card:
        b.use(rules.card_settlement(b.as_of))
        b.say("Card transactions settle T+2 (clause 1.2).")
    return b.build()


def _fee_lines(amount: Decimal, large: bool, b: _Builder) -> bool:
    terms = b.use(rules.mdr_terms(b.as_of, large))
    fee = compute_fee(amount, terms["rate"], terms["cap"])
    who = "Merchant above ₹10 lakh monthly volume: " if large else "Merchant up to ₹10 lakh monthly volume: "
    calc = f"MDR = {pct(fee.rate)} × {inr(amount)} = {inr(fee.uncapped_mdr)}"
    calc += (f", capped at {inr(fee.cap)}" if fee.capped else f", below the {inr(fee.cap)} cap")
    b.say(f"{who}{calc}, so MDR is {inr(fee.mdr)}. GST at 18% on the MDR = {inr(fee.gst)} "
          f"(outside the cap, clause 2.4). Total charge {inr(fee.total)}.")
    return fee.capped


def _limit_check_lines(amount: Decimal, f: Facts, b: _Builder) -> bool:
    """Explain per-transaction / daily limits for an amount. Returns False if it can never be accepted."""
    rule = rules.per_txn_limit(b.as_of)
    lim = rule.value
    if amount <= lim["standard"]:
        return True  # within limits: nothing to say, nothing to cite
    b.use(rule)
    if amount > lim["enhanced"]:
        b.say(f"{inr(amount)} exceeds the maximum UPI amount any merchant may accept per transaction "
              f"({inr(lim['enhanced'])}, clauses 4.1 and 4.2), so this payment cannot be accepted and no "
              "MDR arises.")
        return False
    b.say(f"{inr(amount)} is above the standard UPI per-transaction limit of {inr(lim['standard'])} "
          f"(clause 4.1). Only merchants in the Capital Markets or Insurance categories that have completed "
          f"enhanced KYC may accept up to {inr(lim['enhanced'])} (clauses 4.2 and 4.4).")
    if f.category is None and f.enhanced_kyc is None:
        b.say("The question does not say whether this merchant qualifies.")
    elif f.category is None or f.enhanced_kyc is False:
        b.say("This merchant does not qualify, so the payment cannot be accepted.")
        return False
    daily = b.use(rules.daily_limit(b.as_of))
    b.say(f"Separately, the customer's daily UPI limit is {inr(daily['amount'])}"
          + (" or their own bank's limit if lower" if daily["or_bank_limit_if_lower"] else "")
          + " (clause 4.3" + (" as amended by circular item E" if daily["or_bank_limit_if_lower"] else "")
          + "), which a single payment of this size would also exceed. The documents do not reconcile "
            "clause 4.2 with clause 4.3; confirm with the policy owner before relying on it.")
    return True


def _handle_fee(q: str, f: Facts, b: _Builder) -> Answer:
    amount = f.txn_amounts[0]
    if not _limit_check_lines(amount, f, b):
        return b.build()
    if amount > rules.PER_TXN_LIMIT:
        b.say("If the payment is permitted and processed:")
    if f.size_note:
        b.say(f.size_note)
    bands = [f.large] if f.large is not None else [False, True]
    if f.large is None:
        b.say("The merchant's monthly volume is not stated, so both bands are shown.")
    capped_any = False
    for large in bands:
        capped_any |= _fee_lines(amount, large, b)
    if not rules.circular_in_force(b.as_of):
        _upcoming_circular_note(b)
    if capped_any:
        cite, _, _ = _faq_fees(b.as_of)
        b.conflict("The FAQ says there is no upper limit on the fee; that is wrong (clause 2.3"
                   + (" / circular item C" if rules.circular_in_force(b.as_of) else "") + ").", cite)
    return b.build()


def _handle_rates(q: str, f: Facts, b: _Builder) -> Answer:
    if _has(q, r"\bgst\b") and not _has(q, r"\brate\b", r"\bmdr\b.*\bfor\b"):
        b.cite(rules.m("2.4"))
        b.say("GST at 18% is charged on the MDR amount and is not part of the MDR cap (clause 2.4).")
        return b.build()
    bands = [f.large] if f.large is not None else [False, True]
    for large in bands:
        t = b.use(rules.mdr_terms(b.as_of, large))
        who = "above ₹10 lakh" if large else "up to ₹10 lakh"
        b.say(f"UPI MDR for merchants with monthly volume {who}: {pct(t['rate'])} of the transaction value, "
              f"capped at {inr(t['cap'])} per transaction.")
    b.say("GST at 18% is charged on the MDR and is outside the cap (clause 2.4).")
    _upcoming_circular_note(b)
    cite, _, _ = _faq_fees(b.as_of)
    if _has(q, r"\bcap\b", r"upper limit", r"maximum fee", r"\bsmall\b") or rules.circular_in_force(b.as_of):
        b.conflict("The FAQ's 'no upper limit on the fee'"
                   + (" and 0.30% small-merchant rate are" if rules.circular_in_force(b.as_of) else " is")
                   + " not the policy in force.", cite)
    return b.build()


def _handle_refund(q: str, f: Facts, b: _Builder) -> Answer:
    if not _has(q, r"\bmdr\b", r"\bfee", r"\bcharge", r"\bback\b", r"revers", r"return"):
        b.use(rules.refund_window_days(b.as_of))
        b.say("A merchant may initiate a refund within 90 days of the original transaction (clause 3.1).")
        return b.build()
    if f.hours_after_sale is None and not rules.circular_d_in_force(b.as_of):
        b.use(rules.refund_mdr_reversed(b.as_of, 1))
        b.cite(rules.m("3.2"))
        b.say("It depends on timing: on this date MDR is reversed in full if the refund is initiated within "
              "24 hours of the transaction (clause 3.3); otherwise MDR is not returned (clause 3.2). "
              "From 01 Sep 2026 circular item D deletes clause 3.3, so MDR is never returned.")
        b.cite(rules.c("D"))
        return b.build()
    reversed_ = b.use(rules.refund_mdr_reversed(b.as_of, f.hours_after_sale))
    when = f" {f.hours_after_sale:g} hours after the sale" if f.hours_after_sale is not None else ""
    if rules.circular_d_in_force(b.as_of):
        b.say(f"No. For a refund{when} on {b.as_of:%d %b %Y}, the MDR is not returned: circular item D "
              "deleted clause 3.3 (the 24-hour reversal) effective 01 Sep 2026, and clause 3.2 now applies "
              "without exception.")
        cite, _, _ = _faq_refund(b.as_of)
        b.conflict("The FAQ's 'refund within 24 hours and we reverse the fee' is stale from 01 Sep 2026.", cite)
    elif reversed_:
        b.say(f"Yes. A refund initiated{when} is within 24 hours of the transaction, so the MDR is reversed "
              "in full (clause 3.3, the exception to clause 3.2). The documents do not say whether the GST "
              "on that MDR is also reversed. Note: circular item D deletes this exception from "
              "01 Sep 2026.")
        b.cite(rules.c("D"))
    else:
        b.say(f"No. The refund is more than 24 hours after the transaction, so the 24-hour reversal in "
              "clause 3.3 does not apply and MDR is not returned (clause 3.2).")
    return b.build()


def _handle_limits(q: str, f: Facts, b: _Builder) -> Answer:
    lim = rules.per_txn_limit(b.as_of).value  # cited below only where the answer relies on it
    daily = rules.daily_limit(b.as_of)
    dv = b.use(daily)
    bank = " or the customer's own bank limit, whichever is lower" if dv["or_bank_limit_if_lower"] else ""
    daily_cite = "clause 4.3 as amended by circular item E" if dv["or_bank_limit_if_lower"] else "clause 4.3"
    amounts = f.txn_amounts
    if amounts:
        total = sum(amounts) * f.repeat_count if len(amounts) == 1 else sum(amounts)
        count = f.repeat_count if len(amounts) == 1 else len(amounts)
        biggest = max(amounts)
        if count > 1:
            ok = total <= dv["amount"] and biggest <= lim["standard"]
            b.cite(rules.m("4.1"))
            verdict = "Yes" if ok else "No"
            b.say(f"{verdict}. {count} payments totalling {inr(total)} in one day "
                  f"{'stay within' if ok else 'exceed'} the daily limit of {inr(dv['amount'])} per customer "
                  f"account across all UPI transactions{bank} ({daily_cite}). The daily limit is per "
                  "customer account, so it applies whichever merchant is paid.")
            if ok and dv["or_bank_limit_if_lower"]:
                b.say("This assumes the customer's bank has not set a lower limit.")
        else:
            if biggest <= lim["standard"]:
                b.cite(rules.m("4.1"))
                b.say(f"Yes, {inr(biggest)} is within the standard per-transaction UPI limit of "
                      f"{inr(lim['standard'])} (clause 4.1), provided the customer has not already used their "
                      f"daily limit of {inr(dv['amount'])}{bank} ({daily_cite}).")
            else:
                _limit_check_lines(biggest, f, b)
    else:
        b.use(rules.per_txn_limit(b.as_of))
        b.say(f"The per-transaction UPI limit is {inr(lim['standard'])} (clause 4.1). Merchants in the "
              f"Capital Markets and Insurance categories may accept up to {inr(lim['enhanced'])} per "
              "transaction, but only after completing enhanced KYC (clauses 4.2 and 4.4). Each customer "
              f"account is also limited to {inr(dv['amount'])} per day across all UPI transactions{bank} "
              f"({daily_cite}).")
        cite, _, _ = _faq_limits(b.as_of)
        b.conflict("The FAQ states the ₹2,00,000 limit without the enhanced-KYC condition and omits the "
                   "daily limit.", cite)
    _upcoming_circular_note(b)
    return b.build()


def _handle_closure(q: str, f: Facts, b: _Builder) -> Answer:
    b.use(rules.closure_terms(b.as_of))
    if _has(q, r"\bclosed\b", r"\bclose[d]? (it|my account) (yesterday|today|last)"):
        b.say("Closing an account requires 30 days' written notice (clause 5.1), so if you gave notice "
              "yesterday the account actually closes when that notice period ends, not yesterday.")
    else:
        b.say("You may close the account with 30 days' written notice (clause 5.1).")
    b.say("Pending settlements are released within 10 working days of the closure date, after deducting "
          "any outstanding dues (clause 5.2). Working days exclude Sundays and bank holidays; the documents "
          "include no bank-holiday calendar, so an exact date is not computed.")
    cite, _, _ = _faq_closure(b.as_of)
    b.conflict("The FAQ says money is released 'within 10 days'; clause 5.2 says 10 working days and "
               "after deducting outstanding dues.", cite)
    return b.build()


# ===================================================================== out of scope

_OUT_OF_SCOPE = [
    (r"\bannexure\b|what (is|does) enhanced kyc|how (do|can) i (complete|do|get) (enhanced )?kyc|kyc (documents|process|requirements)",
     "Clause 4.4 refers to enhanced KYC in Annexure C, but Annexure C is not included in the documents.",
     ("4.4",)),
    (r"\bcards?\b.*\b(mdr|fee|fees|charge|charges|rate|cost)\b|\b(mdr|fee|fees|charge|charges|rate|cost)\b.*\bcards?\b",
     "The documents specify card settlement timing (clause 1.2) but no MDR or fee for card transactions.",
     ("1.2",)),
    (r"instant settlement.*\b(cost|price|fee|charge|how (do|can) i|apply|eligib|sign up|activate)|"
     r"\b(cost|price|fee|charge|how (do|can) i|apply|eligib|activate)\b.*instant settlement",
     "Circular item A mentions the Instant Settlement add-on but the documents do not describe its cost, "
     "eligibility or how to activate it.", ()),
    (r"\bholiday(s)?\b.*\b(list|which|calendar|is .* a)\b|\bis .* a (bank )?holiday",
     "The documents refer to bank holidays but contain no holiday calendar.", ("1.3",)),
    (r"\b(neft|imps|rtgs|wallet|international|foreign|forex|cross[- ]border|emi|crypto|net ?banking|"
     r"interest|penalt|late fee|tds|income tax|loan|credit line)\b",
     "This topic is not covered by the policy documents.", ()),
]


def _route(question: str, as_of: date) -> Answer:
    q = question.lower()
    b = _Builder(as_of)
    f = extract(question)

    if (m := re.search(r"\bclause\s+(\d+\.\d+)", q)):
        return _handle_clause(m.group(1), b)
    if re.search(r"\bfaq\b", q):
        return _handle_faq(q, b)
    for pattern, reason, refs in _OUT_OF_SCOPE:
        if re.search(pattern, q):
            if pattern.startswith(r"\bcards?") and _has(q, r"settle", r"same day"):
                continue
            return _cannot(as_of, reason, *[rules.m(r) for r in refs])
    if _has(q, r"\bclos(e|ed|ing|ure)\b.*\baccount\b", r"\baccount\b.*\bclos"):
        return _handle_closure(q, f, b)
    if _has(q, r"chargeback", r"dispute"):
        b.cite(rules.m("3.4"))
        b.say("Chargeback disputes must be raised by the customer's bank within 120 days (clause 3.4).")
        return b.build()
    if _has(q, r"refund"):
        return _handle_refund(q, f, b)
    if _has(q, r"settle", r"receive .*money", r"get (my|the|their) (upi )?money", r"when (will|do|does) .*(get|receive)",
            r"\bt\s*\+\s*[0-2]\b", r"payout"):
        return _handle_settlement(q, f, b)
    if _has(q, r"\btwice\b", r"\bdaily\b", r"per day", r"in (one|a) day", r"\blimit\b", r"maximum",
            r"can (a|the|my) customer", r"allowed to (pay|accept)", r"\baccept\b"):
        return _handle_limits(q, f, b)
    if f.txn_amounts and _has(q, r"\bmdr\b", r"\bgst\b", r"\bfee", r"\bcharge", r"\bpay\b", r"\bcost", r"\bdeduct"):
        return _handle_fee(q, f, b)
    if _has(q, r"\bmdr\b", r"\bgst\b", r"merchant discount", r"\bfee", r"\bcap\b"):
        return _handle_rates(q, f, b)
    return _cannot(as_of, "The policy documents do not cover this question.")


def _coerce_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    parsed = parse_date(value)
    if parsed is None:
        raise ValueError(f"Unrecognised as_of_date {value!r}")
    return parsed


def ask(question: str, as_of_date: date | str | None = None) -> Answer:
    """Answer `question` under the policy in force on `as_of_date`.

    If `as_of_date` is omitted, dates written in the question are used (one answer per date),
    falling back to 15 Aug 2026 (DECISIONS D5).
    """
    explicit = _coerce_date(as_of_date)
    if explicit is not None:
        dates = [explicit]
    else:
        dates = extract(question).dates or [DEFAULT_AS_OF]

    results = []
    for d in dates:
        try:
            results.append(_route(question, d))
        except rules.PolicyNotInForce as e:
            results.append(_cannot(d, str(e)))
    if len(results) == 1:
        return results[0]

    # Several dates in one question: answer each and merge.
    cites: list[Citation] = []
    for r in results:
        cites += [c for c in r.citations if c not in cites]
    statuses = {r.status for r in results}
    status = (CONFLICT_RESOLVED if CONFLICT_RESOLVED in statuses else
              ANSWERED if ANSWERED in statuses else CANNOT_ANSWER)
    text = " | ".join(f"On {r.as_of_date:%d %b %Y}: {r.answer}" for r in results)
    notes = " ".join(r.resolution for r in results if r.resolution) or None
    return Answer(text, cites, status, notes, None)
