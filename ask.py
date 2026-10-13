"""CLI for the policy assistant.

  python ask.py "When does a small merchant receive UPI money?"
  python ask.py "Do I get the MDR back on a refund 3 hours after the sale?" --date 2026-09-05
  python ask.py --demo        # runs the eight brief questions
  python ask.py --json "..."  # machine-readable output
"""
from __future__ import annotations

import argparse
import json
import sys

from policy_assistant.assistant import ask

DEMO = [
    ("Q1", "When does a small merchant receive UPI money?", "2026-08-15"),
    ("Q2", "A large merchant (above Rs.10 lakh monthly) receives a Rs.4,000 UPI payment. "
           "What MDR and GST do they pay?", "2026-08-15"),
    ("Q3", "Same merchant, a Rs.1,50,000 payment. What do they pay?", "2026-08-15"),
    ("Q3+", "A large merchant (above Rs.10 lakh monthly), a Rs.1,50,000 payment. What do they pay?", "2026-08-15"),
    ("Q4a", "A merchant refunds a customer 3 hours after the sale. Do they get the MDR back?", "2026-08-20"),
    ("Q4b", "A merchant refunds a customer 3 hours after the sale. Do they get the MDR back?", "2026-09-05"),
    ("Q5", "What does the FAQ say about the MDR cap, and is the FAQ right?", "2026-08-15"),
    ("Q6", "Can a customer pay Rs.1,00,000 twice in one day to a merchant?", "2026-08-15"),
    ("Q7", "I closed my account yesterday. When will I get my money?", "2026-08-15"),
    ("Q8", "Does the policy allow me to settle card payments same day?", "2026-08-15"),
]


def _print(label: str, question: str, result, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"id": label, "question": question, **result.to_dict()}, ensure_ascii=False, indent=2))
        return
    d = result.to_dict()
    print(f"[{label}] {question}")
    print(f"  as_of:      {d['as_of_date'] or '(per date in question)'}")
    print(f"  status:     {d['status']}")
    print(f"  answer:     {d['answer']}")
    print("  citations:  " + ("; ".join(d["citations"]) or "-"))
    if d["resolution"]:
        print(f"  resolution: {d['resolution']}")
    print()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # ₹ on Windows consoles
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("question", nargs="?")
    p.add_argument("--date", help="as_of_date (YYYY-MM-DD or '5 Sep 2026'); default 15 Aug 2026")
    p.add_argument("--demo", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if args.demo:
        for label, q, d in DEMO:
            _print(label, q, ask(q, d), args.json)
    elif args.question:
        _print("Q", args.question, ask(args.question, args.date), args.json)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
