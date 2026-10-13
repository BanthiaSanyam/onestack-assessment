"""Run the assistant on eval.json and print a score table.

  python run_eval.py            # table + summary
  python run_eval.py -v         # also print the answer for every failing row

A row passes only if all three checks pass:
  status    returned status == expected_status
  cites     every expected citation is present (extra citations are allowed)
  answer    every must_contain substring present, no must_not_contain substring present
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from policy_assistant.assistant import ask
from policy_assistant.corpus import CIRCULAR, FAQ, MASTER, Citation

EVAL_PATH = Path(__file__).resolve().parent / "eval.json"
_DOCS = {"master": MASTER, "circular": CIRCULAR, "faq": FAQ}


def _has_citation(expected: str, got: list[Citation]) -> bool:
    kind, _, ref = expected.partition(":")
    doc = _DOCS[kind]
    if kind == "faq":  # FAQ is cited by question text; match on a fragment
        return any(c.document == doc and ref.lower() in c.ref.lower() for c in got)
    return Citation(doc, ref) in got


def score(case: dict) -> dict:
    res = ask(case["question"], case["as_of_date"])
    text = res.answer.lower()
    missing_cites = [e for e in case["expected_citations"] if not _has_citation(e, res.citations)]
    missing_text = [s for s in case["must_contain"] if s.lower() not in text]
    forbidden = [s for s in case["must_not_contain"] if s.lower() in text]
    checks = {
        "status": res.status == case["expected_status"],
        "cites": not missing_cites,
        "answer": not missing_text and not forbidden,
    }
    return {"case": case, "result": res, "checks": checks, "pass": all(checks.values()),
            "missing_cites": missing_cites, "missing_text": missing_text, "forbidden": forbidden}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))["questions"]
    rows = [score(c) for c in cases]

    mark = {True: "ok", False: "FAIL"}
    print(f"{'id':<5} {'as_of':<10} {'expected':<17} {'got':<17} {'status':<6} {'cites':<6} {'answer':<6} adversarial")
    print("-" * 110)
    for r in rows:
        c, ch = r["case"], r["checks"]
        print(f"{c['id']:<5} {c['as_of_date']:<10} {c['expected_status']:<17} {r['result'].status:<17} "
              f"{mark[ch['status']]:<6} {mark[ch['cites']]:<6} {mark[ch['answer']]:<6} {c['adversarial'] or '-'}")
    print("-" * 110)

    n = len(rows)
    adv = [r for r in rows if r["case"]["adversarial"] and not r["case"]["id"].startswith("B")]
    for key in ("status", "cites", "answer"):
        print(f"{key:<8} {sum(r['checks'][key] for r in rows)}/{n}")
    print(f"{'overall':<8} {sum(r['pass'] for r in rows)}/{n}   "
          f"(own adversarial: {sum(r['pass'] for r in adv)}/{len(adv)})")

    failures = [r for r in rows if not r["pass"]]
    if args.verbose and failures:
        print("\nFailures:")
        for r in failures:
            print(f"\n[{r['case']['id']}] {r['case']['question']}")
            print(f"  got:      {r['result'].status} | {r['result'].answer}")
            print(f"  cites:    {[str(c) for c in r['result'].citations]}")
            if r["missing_cites"]:
                print(f"  missing cites: {r['missing_cites']}")
            if r["missing_text"]:
                print(f"  missing text:  {r['missing_text']}")
            if r["forbidden"]:
                print(f"  forbidden:     {r['forbidden']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
