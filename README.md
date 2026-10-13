# Policy Assistant (AI-2: The Policy That Changed)

A grounded question-answering assistant over the merchant policy documents in `ai-2-data/`. Answers depend on `as_of_date`: amendments, a delayed clause deletion and a stale FAQ are resolved by effective date and document precedence. Every citation is checked against the parsed documents, and every fee is computed in code.

## How to run

Python 3.10+, standard library only. No install, no API key, works offline.
use can use python ask.py to ask you own question's from terminal.
some demo question are given below.

```bash
python ask.py --demo                                   # the brief's Q1–Q8
python ask.py "When does a small merchant receive UPI money?"
python ask.py "A merchant refunds 3 hours after the sale. Is MDR returned?" --date 2026-09-05
python ask.py --json "Can a customer pay Rs.1,00,000 twice in one day?"
python run_eval.py -v                                  # eval.json score table
python -m unittest discover -s tests -t .              # unit tests
```

From Python:

```python
from policy_assistant.assistant import ask
r = ask("A large merchant (above Rs.10 lakh monthly) receives a Rs.4,000 UPI payment. What MDR and GST?", "2026-08-15")
r.status       # 'CONFLICT_RESOLVED'
r.answer       # 'Merchant above ₹10 lakh monthly volume: MDR = 0.50% × ₹4,000 = ₹20, below the ₹25 cap ...'
r.citations    # [policy_master_v1.md clause 2.2, circular_2026_08_amendment.md item C, policy_master_v1.md clause 2.4]
r.resolution   # 'Circular item C (effective 01 Aug 2026) replaced clause 2.3 ...'
```

`as_of_date` accepts a `date`, `"2026-09-05"` or `"5 Sep 2026"`. If omitted, a date written in the question is used, else **15 Aug 2026**.

## Output

| Field | Meaning |
|---|---|
| `answer` | Text built only from rule values and calculated numbers |
| `citations` | Document + clause (`policy_master_v1.md clause 2.3`), circular item (`item C`), or FAQ question heading (the FAQ has no clause numbers, so none are invented) |
| `status` | `ANSWERED` / `CONFLICT_RESOLVED` / `CANNOT_ANSWER` |
| `resolution` | For `CONFLICT_RESOLVED`: which clause superseded which, or how the FAQ disagrees |

## Design

```
policy_assistant/
  corpus.py     parses clauses / circular items / FAQ questions; cite() refuses unknown refs
  rules.py      date-versioned rules: master from 01 Jan 2026, circular A/B/C/E from 01 Aug, D from 01 Sep
  calc.py       Decimal MDR / cap / GST arithmetic, half-up to the paisa, Indian ₹ formatting
  extract.py    regex extraction: amounts (₹, Rs., lakh), monthly volume vs payment, band, hours, dates, KYC
  assistant.py  ask(): keyword routing to topic handlers; unknown topics -> CANNOT_ANSWER
ask.py          CLI and Q1–Q8 demo
run_eval.py     runs eval.json, scores status / citations / answer, prints table
eval.json       30 cases: 21 own (17 adversarial) + the brief's questions
```

Precedence: circular (if in force) > master v1.0 > FAQ. The FAQ is never authoritative; it is quoted only to point out where it is wrong or stale. All ambiguities and choices are in [DECISIONS.md](DECISIONS.md).

## Answers to the brief (as_of 15 Aug 2026 unless stated)

| Q | Status | Answer |
|---|---|---|
| Q1 | CONFLICT_RESOLVED | T+1 next working day; T+0 by 11:59 PM with Instant Settlement add-on (circular A). Size is irrelevant |
| Q2 | CONFLICT_RESOLVED | MDR 0.50% × ₹4,000 = ₹20 (under the ₹25 cap, circular C), GST ₹3.60, total ₹23.60 |
| Q3 | CONFLICT_RESOLVED | ₹1,50,000 exceeds the ₹1,00,000 limit (4.1) unless Capital Markets/Insurance with enhanced KYC (4.2, 4.4), and exceeds the daily limit (4.3/E). If processed: ₹25 + ₹4.50 = ₹29.50 |
| Q4 | 20 Aug: ANSWERED / 5 Sep: CONFLICT_RESOLVED | 20 Aug: yes, reversed (3.3). 5 Sep: no, 3.3 deleted by circular D, 3.2 applies |
| Q5 | CONFLICT_RESOLVED | FAQ says "no upper limit". Wrong since 01 Jan (2.3: ₹15); now ₹15 / ₹25 (C) |
| Q6 | CONFLICT_RESOLVED | No: daily limit ₹1,00,000 per customer account, or the bank's lower limit (4.3/E) |
| Q7 | CONFLICT_RESOLVED | 30 days' notice first (5.1); then within 10 working days of closure, minus dues (5.2) |
| Q8 | ANSWERED | No: cards settle T+2 (1.2); T+0 is UPI-only |

## What works

- Date-dependent answers across all boundaries: before 01 Jan 2026 (CANNOT_ANSWER), 20–31 Jul (circular issued, not effective), 01 Aug, 01 Sep.
- Deterministic fee arithmetic with caps, GST outside the cap, and both merchant bands when size is unknown.
- Limit checks run before fee calculation (an impossible payment isn't priced).
- Stale/incorrect FAQ detection with the specific reason.
- Clause lookup with status ("Is clause 3.3 still in force?"); non-existent clauses give CANNOT_ANSWER.
- CANNOT_ANSWER for card MDR, Annexure C, add-on pricing, holiday calendars and off-topic questions.
- **Eval: 30/30** (17/17 own adversarial). **Unit tests: 15/15.**

## What doesn't (see [WHERE_IT_BREAKS.md](WHERE_IT_BREAKS.md))

- Negations like "not within 24 hours" are misread, giving a confidently wrong answer.
- Transactions that straddle a rule change (sale 31 Aug, refund 1 Sep) are answered per date instead of reasoned about.
- False premises inside a question are not challenged unless specifically modelled.
- Keyword routing is brittle to slang/unusual phrasing (fails safe to CANNOT_ANSWER mostly, not always).
- `ask()` is stateless: "Same merchant…" follow-ups don't carry context.
- The 4.2 vs 4.3 limit contradiction is flagged, not resolved.

The eval scores 30/30 because I wrote the cases knowing the rules; it measures regressions on known traps, not robustness to unseen phrasing.

## Required files

[DECISIONS.md](DECISIONS.md) · [AI_USAGE.md](AI_USAGE.md) · [WHERE_IT_BREAKS.md](WHERE_IT_BREAKS.md) · [eval.json](eval.json) · [run_eval.py](run_eval.py)
