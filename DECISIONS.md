# DECISIONS

Every ambiguity, trap or inconsistency found in `ai-2-data/`, and what the system does about it.

## Document timeline (source of truth for `as_of_date`)

| Document | Date | Authority |
|---|---|---|
| `policy_master_v1.md` (v1.0) | effective 01 Jan 2026 | Authoritative base text |
| `merchant_faq_2026-03.md` | last updated 12 Mar 2026 | **Not authoritative**. Customer-facing summary; used only to quote it or to flag where it is wrong |
| `circular_2026_08_amendment.md` (MS/2026/17) | issued 20 Jul 2026, effective 01 Aug 2026; item D effective 01 Sep 2026 | Authoritative; overrides master clauses it names |

**D1. Precedence rule.** Circular (if in force on `as_of_date`) > Master v1.0 > FAQ. The FAQ never overrides a policy clause. When the FAQ disagrees with the policy in force, the answer follows the policy and the status is `CONFLICT_RESOLVED` with an explanation.

**D2. Issued vs effective.** The circular was issued 20 Jul 2026 but is effective 01 Aug 2026. For `as_of_date` between 20 Jul and 31 Jul, the old master clauses apply. Effective dates are inclusive (a rule effective 01 Aug applies on 01 Aug).

**D3. Item D has its own date.** "(Effective 01 September 2026.)" is printed under item D only, so only D (deletion of 3.3) is deferred to 01 Sep. A, B, C, E are effective 01 Aug.

**D4. Before 01 Jan 2026.** No policy document is in force, so the answer is `CANNOT_ANSWER`.

**D5. Default date.** If the caller gives no `as_of_date`, use 15 Aug 2026 (per the brief). A date written inside the question text ("on 5 Sep 2026") overrides the default only if the caller did not pass one explicitly.

## Settlement

**D6. Circular A drops the working-day definition.** Original 1.1 contained "Working days exclude Sundays and bank holidays." Item A *replaces* 1.1 with a sentence that doesn't contain it. Clause 1.3 (unchanged) still uses "next working day", so the term must still mean something. I keep the original definition and cite it as master 1.1 (v1.0 text), noting the gap.

**D7. T+0 depends on the add-on, not on merchant size.** From 01 Aug, UPI is T+0 (by 11:59 PM) only with the "Instant Settlement" add-on, otherwise T+1. Q1 asks about a "small merchant", but size is irrelevant to settlement, so the answer gives both branches. The FAQ's "next working day" is stale for add-on merchants after 01 Aug.

**D8. T+0 on a holiday.** The circular doesn't say whether T+0 applies on Sundays or bank holidays. Clause 1.3 (next working day if the settlement date is a bank holiday) is unchanged, so I mention it but don't compute a date.

**D9. Cards are never same-day.** The Instant Settlement add-on in A applies to UPI only. Card transactions stay T+2 (1.2), so "same-day card settlement" is answered No.

**D10. No bank-holiday calendar is provided.** I never compute a concrete calendar date that depends on bank holidays. (15 Aug 2026 is a Saturday and Independence Day in India, a likely bank holiday, which shows why guessing dates is unsafe.)

## MDR and GST

**D11. Small vs large.** The policy defines bands by monthly volume: "up to ₹10 lakh" (inclusive, so exactly ₹10,00,000 is small) and "above ₹10 lakh". "Small"/"large" are FAQ words; I map small to up to ₹10 lakh and large to above. If size is unknown, I answer for both bands.

**D12. Rates and caps by date.**

| Period | ≤ ₹10 lakh | > ₹10 lakh |
|---|---|---|
| 01 Jan to 31 Jul 2026 | 0.30%, cap ₹15 (2.1, 2.3) | 0.50%, cap ₹15 (2.2, 2.3) |
| from 01 Aug 2026 | 0.25%, cap ₹15 (Circ. B, C) | 0.50%, cap ₹25 (2.2, Circ. C) |

Clause 2.2 still says "subject to the cap in 2.3". I read that as pointing to 2.3 *as amended* by C.

**D13. GST.** 18% on the MDR amount, computed on the post-cap MDR and **not** included in the cap (2.4). Total charge = MDR + GST.

**D14. Arithmetic.** Done in `Decimal`, rounded half-up to the paisa. No float, no LLM.

## Refunds

**D15. Which date decides the refund rule?** The policy doesn't say whether it's the transaction date or the refund date. I use `as_of_date` as the date of the refund, and assume the sale and refund both fall under the same regime. A sale on 31 Aug refunded on 1 Sep is flagged as unresolved in WHERE_IT_BREAKS.md.

**D16. 3.3 deleted from 01 Sep.** Up to 31 Aug, a refund within 24h gets MDR reversed in full (3.3). From 01 Sep, 3.2 applies without exception, so MDR is not returned, even though the 3.2 text still says "except as provided in 3.3". The circular's words "now applies without exception" settle it. The FAQ's "within 24 hours we reverse the fee" is stale from 01 Sep.

**D17. GST on a reversed MDR.** Not stated anywhere. I say the MDR is reversed and that GST treatment is not specified.

**D18. Exactly 24 hours.** "Within 24 hours" is read as ≤ 24h.

## Limits

**D19. ₹2 lakh needs category AND enhanced KYC.** 4.2 is limited by 4.4 (enhanced KYC, Annexure C). The FAQ omits the KYC condition. Annexure C isn't in the data, so questions about what enhanced KYC involves are `CANNOT_ANSWER`.

**D20. 4.2 vs 4.3 conflict inside the master.** 4.2 allows a single ₹2,00,000 payment, but 4.3 caps a customer account at ₹1,00,000 per day across all UPI transactions (from 01 Aug: ₹1,00,000 or the customer's bank limit, whichever is lower). Read literally, any payment above ₹1,00,000 breaches 4.3. I don't silently pick one: the answer states the per-transaction permission **and** the daily-limit problem, and flags it as needing a policy owner's clarification.

**D21. Q3 (₹1,50,000 by a large merchant).** It's above the ₹1,00,000 per-transaction limit (4.1) unless the merchant is Capital Markets/Insurance with enhanced KYC. The system reports that first. It then computes the fee only for the case where the payment could go through: MDR = min(0.5% × 150000, ₹25) = ₹25, GST ₹4.50, total ₹29.50.

**D22. Daily limit is per customer account, not per merchant.** So "pay ₹1,00,000 twice in one day to a merchant" is No under 4.3 / E.

## Account closure

**D23. "I closed my account yesterday."** 5.1 requires 30 days' written notice, so the closure date is the end of the notice period, not the request date. Funds come within **10 working days of closure** after outstanding dues are deducted (5.2). The FAQ's "10 days" is imprecise (working days, and minus dues).

## Citations

**D24. Clause numbers come only from parsed text.** Master clause IDs are parsed from `policy_master_v1.md`. Circular items are cited by their letter (A–F). Every citation is checked against the parsed set before it's returned, so an unknown ID raises an error instead of being invented.

**D25. The FAQ has no clause numbers.** FAQ citations use the question heading, e.g. `merchant_faq_2026-03.md § "What do I pay on a UPI transaction?"`.

## Out of scope means CANNOT_ANSWER

**D26.** Card MDR, cost/eligibility of the Instant Settlement add-on, Annexure C contents, bank holiday lists, international payments, and anything not in the three documents all get `CANNOT_ANSWER`, with no guessing.

## Approach

**D27. Rules, not an LLM.** With 3 short documents and a 60-minute budget, hand-written intent rules over a date-versioned rule table are deterministic, fully offline and auditable. The trade-off is lower recall on phrasings I didn't anticipate, documented in WHERE_IT_BREAKS.md.
