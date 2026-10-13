# WHERE IT BREAKS

Three questions this system gets wrong or should not be trusted with. All three were reproduced with `python ask.py "<question>"` on the final code. They are deliberately **not** in `eval.json` as passing cases, because the system does not handle them.

---

## 1. Negated time conditions → confidently wrong answer

```
python ask.py "My refund was not processed within 24 hours, do I still get MDR back?" --date 2026-08-15
```

**Got:** `ANSWERED`: "Yes. A refund initiated 24 hours after the sale is within 24 hours of the transaction, so the MDR is reversed in full (clause 3.3)…"

**Correct:** No. If the refund was initiated *after* 24 hours, clause 3.3 does not apply and MDR is not returned (3.2).

**Why:** `extract.py` pulls "24 hours" with a regex and has no notion of negation ("not within", "more than", "after", "over"). The number is read but the logic around it is not. This is the most dangerous failure: wrong, confident, and with real-looking citations. A fix would parse comparison phrases ("more than N hours", "not within N hours") into an interval instead of a single number, and fall back to the "it depends" answer when unsure.

---

## 2. A refund that crosses a rule change (sale and refund on different regimes)

```
python ask.py "A sale happened at 11 PM on 31 Aug 2026 and I refunded it 2 hours later on 1 Sep 2026. Do I get the MDR back?"
```

**Got:** `CONFLICT_RESOLVED` with two contradictory answers, "On 31 Aug 2026: Yes… | On 01 Sep 2026: No…".

**Correct:** Unknown from the documents. Circular D deletes 3.3 effective 01 Sep, but nothing says whether the rule is fixed by the **transaction date** or the **refund date** (DECISIONS D15). The honest answer is "probably No, because the refund was initiated on 1 Sep after the deletion, but the documents don't settle this; confirm with the policy owner".

**Why:** When a question contains several dates, `ask()` treats each one as an alternative `as_of_date` (designed for "ask on 20 Aug and again on 5 Sep"). It has no concept of an event timeline (sale date vs refund date), so it cannot reason about a transaction that straddles the 01 Sep boundary.

---

## 3. False premises are answered around, not challenged

```
python ask.py "Since the August circular removed the MDR cap, how much MDR does a large merchant pay on a Rs.50,000 payment?"
```

**Got:** `CONFLICT_RESOLVED`: "MDR = 0.50% × ₹50,000 = ₹250, capped at ₹25, so MDR is ₹25… Total charge ₹29.50."

**Correct numbers, but** the answer never says "the circular did not remove the cap; item C raised it to ₹25 for large merchants". A support agent reading quickly could miss that the merchant's belief is wrong.

**Why:** Routing is intent-based (fee question → fee handler). Claims embedded in the question ("since X…") are never extracted or checked against the documents. Only premises the code explicitly models are caught: non-existent clause numbers (E20), the KYC condition (E11), and "closed yesterday" vs the 30-day notice (Q7).

---

## Other known limits (less severe)

- **Brittle phrasing.** Routing and extraction are keyword/regex based. "4k", "big merchant's cut" and similar slang give `CANNOT_ANSWER`. That's safe but unhelpful. Questions phrased very differently from anything anticipated may also route to the wrong handler.
- **No conversation memory.** `ask()` is stateless, so the brief's Q3 ("Same merchant…") does not know the merchant is large. It shows both bands instead of guessing. `python ask.py --demo` also shows the explicit variant (Q3+).
- **Clause 4.2 vs 4.3 is flagged, not resolved.** A ₹1,50,000 payment is allowed per transaction for an eligible merchant (4.2) but exceeds the customer's ₹1,00,000 daily limit (4.3). The system reports the contradiction; it cannot know which the policy owner intended.
- **No bank-holiday calendar.** The system never computes a concrete settlement or payout date, only the rule (T+1, 10 working days…).
- **GST on a reversed MDR** (3.3) is unspecified in the documents and reported as such.
