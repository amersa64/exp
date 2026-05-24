"""
Variety guard for nudge content (Rubric D2 — "never the same templated ping twice").

The LLM is prompted to vary tone, but prompts drift toward modes; restraint must
be structural. This module checks a candidate nudge body against the user's last
N nudges and either:
  (a) accepts it,
  (b) asks the engine to re-roll once with explicit "avoid these phrasings" guidance,
  (c) gives up (and lets the engine fall back to silence — Rubric D3).

The check is intentionally cheap: token-set Jaccard + opening-bigram match. We
don't need NLP — we need to refuse near-duplicates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_WORD = re.compile(r"[a-z0-9']+")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


_STOPWORDS = {"a", "an", "the", "and", "or", "but", "so", "to", "of", "in", "on",
              "for", "it", "it's", "is", "are", "was", "you", "your", "i", "we",
              "this", "that", "ok", "okay", "hey", "hi"}


def _opening_signature(text: str) -> str:
    """The first content word — repeating it feels templated (e.g. 'Laptop's…')."""
    toks = _WORD.findall(text.lower())
    for t in toks:
        if t not in _STOPWORDS:
            return t
    return toks[0] if toks else ""


@dataclass
class VarietyVerdict:
    accept: bool
    reason: str
    avoid_phrases: list[str]  # for the re-roll prompt


def check(candidate: str, recent_bodies: list[str], jaccard_max: float = 0.55) -> VarietyVerdict:
    if not candidate.strip():
        return VarietyVerdict(False, "empty", [])
    cand_toks = _tokens(candidate)
    if not cand_toks:
        return VarietyVerdict(False, "no content tokens", [])
    cand_open = _opening_signature(candidate)

    avoid: list[str] = []
    worst_jaccard = 0.0
    for body in recent_bodies:
        toks = _tokens(body)
        if not toks:
            continue
        inter = len(cand_toks & toks)
        union = len(cand_toks | toks)
        j = inter / union if union else 0.0
        worst_jaccard = max(worst_jaccard, j)
        if j >= jaccard_max:
            avoid.append(body)
        elif _opening_signature(body) and _opening_signature(body) == cand_open:
            avoid.append(body)

    if avoid:
        return VarietyVerdict(
            accept=False,
            reason=f"too similar to {len(avoid)} recent nudge(s), worst jaccard={worst_jaccard:.2f}",
            avoid_phrases=list({a for a in avoid})[:3],
        )
    return VarietyVerdict(True, f"distinct (worst jaccard={worst_jaccard:.2f})", [])
