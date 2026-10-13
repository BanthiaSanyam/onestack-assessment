# Policy Assistant (AI-2: The Policy That Changed)

A grounded question-answering assistant over the merchant policy documents in `ai-2-data/`. Answers depend on `as_of_date`: amendments, deleted clauses and the stale FAQ are resolved by date and precedence.

> Work in progress. See commit history.

## Plan
1. Document analysis and decisions (`DECISIONS.md`)
2. Clause loader, date-versioned rules, deterministic fee calculator
3. `ask(question, as_of_date)` with intent routing and a CLI
4. `eval.json` and `run_eval.py`
5. `WHERE_IT_BREAKS.md`, `AI_USAGE.md`, final README
