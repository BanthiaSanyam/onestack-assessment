# AI USAGE

AI tools **were** used for this assignment.

## Tool

- **Claude Code** (Anthropic, model Claude Opus 5.5) in the VS Code extension, used as a pair programmer that I directed step by step.

## How the work was split

**What I did**
- Set the overall approach for the session: understand the brief and the data first, list every date constraint and data problem before writing code, then build in small steps with a commit after each one.
- Asked for a written analysis and a step-by-step plan before any code was written, and controlled the order and pace of each step ("now build part 2", "now part 3", ...).
- Set up the GitHub repository and made every commit and push myself from my own terminal. I wrote the commit messages and decided what went into each commit (for example, holding the eval suite and docs for the final commit).
- Reviewed each step before committing, and edited the generated code (e.g. removed module docstrings from `rules.py` and `extract.py`).
- Pushed back on the drafts, including this file.

**What the AI did**
- Read the PDF and the three data files and wrote up the constraints, traps and expected answers for Q1–Q8. That analysis became `DECISIONS.md`.
- Proposed the technical design (rule-based, offline, standard-library Python; date-versioned rules; Decimal arithmetic) and a commit-by-commit breakdown, which I then followed and adjusted.
- Wrote the code, tests and docs: `policy_assistant/`, `ask.py`, `run_eval.py`, `eval.json`, `tests/`, and drafts of `README.md`, `DECISIONS.md`, `WHERE_IT_BREAKS.md` and this file.
- Ran the tests, demo and eval and fixed the bugs they exposed.

## Where the AI got things wrong (and how it was caught)

- **Unit test miscount.** It asserted 18 master clauses; there are 17. Caught by running the tests.
- **Amount mis-classification.** In Q2, the ₹4,000 payment was parsed as monthly volume because "monthly" appeared earlier in the sentence. Caught by running the Q1–Q8 demo; the regex was tightened.
- **Missing citations.** Q6 omitted master clause 4.3, and Q1 omitted 1.1. Fixed.
- **Bugs found by the eval suite (first run 26/30).**
  - FAQ refund questions were routed to the FAQ fee entry.
  - "Penalty" wasn't recognised as out of scope, so it got a wrong settlement answer.
  - The FAQ's missing KYC condition went unflagged.
  - One expectation in `eval.json` (E04) was itself wrong.
- **Known remaining failures** are documented in `WHERE_IT_BREAKS.md`.

## What no AI does at runtime

The assistant calls **no LLM or external API**. Answers come from hand-written rules over the parsed documents, and all arithmetic is Python `Decimal`. It runs fully offline with no API key.
