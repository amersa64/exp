"""
Safety boundary (Section 4.4, Principle 2.8, Rubric B5).

This is intentionally simple and intentionally STRICT: if any of the high-risk
signal patterns appear in user input, the coach refuses to prescribe and hands
off. False positives are far cheaper than false negatives here.

This is NOT a substitute for clinical judgment — it is a hard floor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SafetySignal:
    category: str            # "injury" | "medical" | "mental_health" | "disordered_eating"
    matched: str
    handoff: str             # what to say to the user


# Patterns are deliberately broad. Tune later, never narrow without review.
_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("mental_health",
     re.compile(r"\b(suicid\w*|kill myself|end (it|my life)|self[- ]?harm|hopeless)\b", re.I),
     "I'm not the right help for what you just described. Please reach out now — "
     "in the US you can call or text 988. If you're outside the US, "
     "https://findahelpline.com lists options by country. I'll be here when you're ready."),
    ("disordered_eating",
     re.compile(r"\b(purge|purging|starv\w*|haven'?t eaten in \d+ days|binge[- ]restrict)\b", re.I),
     "What you described sits outside what I'm qualified to coach. Please talk to a doctor or "
     "a specialist — NEDA helpline (US) is 1-800-931-2237. I'll pause prescribing until you've "
     "spoken with someone."),
    ("medical",
     re.compile(r"\b(chest pain|shortness of breath|fainted|passing out|heart racing|bleeding)\b", re.I),
     "That sounds like something to take to a clinician, not a fitness coach. Please contact "
     "your doctor — or if it's acute, urgent care or 911. I won't prescribe over symptoms like this."),
    ("injury",
     re.compile(r"\b(sharp pain|tore|torn|popped|can'?t walk|swollen|numb(ness)?|tingling)\b", re.I),
     "That doesn't sound like normal soreness. I'd rather hand off than guess — please get this "
     "looked at by a physio or doctor before we touch the program again. I'll hold the plan."),
]


def scan(text: str) -> SafetySignal | None:
    if not text:
        return None
    for category, pattern, handoff in _PATTERNS:
        m = pattern.search(text)
        if m:
            return SafetySignal(category=category, matched=m.group(0), handoff=handoff)
    return None
