"""Load the three source documents and index their citable units.

Citable units:
  - master:   numbered clauses, e.g. "2.3"
  - circular: lettered items, e.g. "C"
  - faq:      question headings (the FAQ has no clause numbers, so we never invent one)

Every citation the assistant returns is validated against this index (DECISIONS D24).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "ai-2-data"

MASTER = "policy_master_v1.md"
CIRCULAR = "circular_2026_08_amendment.md"
FAQ = "merchant_faq_2026-03.md"

_MASTER_RE = re.compile(r"^(\d+\.\d+)\s+(.+)$")
_CIRCULAR_RE = re.compile(r"^([A-Z])\.\s+(.+)$")
_FAQ_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")


@dataclass(frozen=True)
class Citation:
    document: str
    ref: str  # clause number, circular item letter, or FAQ question text

    def __str__(self) -> str:
        if self.document == MASTER:
            return f"{MASTER} clause {self.ref}"
        if self.document == CIRCULAR:
            return f"{CIRCULAR} item {self.ref}"
        return f'{FAQ} § "{self.ref}"'


def _read(name: str) -> list[str]:
    return (DATA_DIR / name).read_text(encoding="utf-8").splitlines()


def _parse_master() -> dict[str, str]:
    return {m.group(1): m.group(2).strip()
            for line in _read(MASTER) if (m := _MASTER_RE.match(line.strip()))}


def _parse_circular() -> dict[str, str]:
    items: dict[str, str] = {}
    current = None
    for raw in _read(CIRCULAR):
        line = raw.strip()
        m = _CIRCULAR_RE.match(line)
        if m:
            current = m.group(1)
            items[current] = m.group(2).strip()
        elif current and line:  # continuation line, e.g. "(Effective 01 September 2026.)"
            items[current] += " " + line
    return items


def _parse_faq() -> dict[str, str]:
    entries: dict[str, str] = {}
    current = None
    for raw in _read(FAQ):
        line = raw.strip()
        m = _FAQ_RE.match(line)
        if m:
            current = m.group(1)
            entries[current] = ""
        elif current and line:
            entries[current] = (entries[current] + " " + line).strip()
    return entries


@lru_cache(maxsize=1)
def corpus() -> dict[str, dict[str, str]]:
    return {MASTER: _parse_master(), CIRCULAR: _parse_circular(), FAQ: _parse_faq()}


def text_of(c: Citation) -> str:
    return corpus()[c.document][c.ref]


def cite(document: str, ref: str) -> Citation:
    """Build a citation, refusing any ref that does not exist in the parsed text."""
    if ref not in corpus().get(document, {}):
        raise KeyError(f"Refusing to cite non-existent unit {ref!r} in {document}")
    return Citation(document, ref)


def faq_cite(keyword: str) -> Citation:
    """Cite the FAQ entry whose question contains `keyword` (case-insensitive)."""
    matches = [q for q in corpus()[FAQ] if keyword.lower() in q.lower()]
    if len(matches) != 1:
        raise KeyError(f"FAQ keyword {keyword!r} matched {matches}")
    return Citation(FAQ, matches[0])
