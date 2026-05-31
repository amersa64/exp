"""
End-to-end demo of the LLM-driven program builder.

Run:
    cd /Users/amer/productivity/the-coach
    source .venv/bin/activate
    PYTHONPATH=backend python cli/ai_program_demo.py

What it does:
    1. Loads .env (so OPENAI_API_KEY is picked up)
    2. Builds a sample UserProfile in memory — no DB, no server
    3. Runs split planner (1 LLM call) → per-day pickers (N parallel) → validation
    4. Pretty-prints the generated split, exercises, and any validation issues

This is for kicking the tires on the architecture before wiring it into the
live persona flow. Tweak PROFILES below to test different scenarios.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

# --- Load .env so OPENAI_API_KEY etc. are present -------------------------
# Replicate the trivial loader from backend/api/app.py so the demo doesn't
# require the FastAPI app to be started first.

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _REPO_ROOT / ".env"
if _ENV_PATH.exists():
    for raw in _ENV_PATH.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

sys.path.insert(0, str(_REPO_ROOT / "backend"))

from coach.ai_program import build_program  # noqa: E402
from coach.llm import LLMClient  # noqa: E402
from coach.models import UserProfile  # noqa: E402


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


# Three sample profiles you can switch between by changing CHOICE below.
# Each has the shape a real intake would produce after derive_profile.
PROFILES: dict[str, UserProfile] = {
    "novice_strength": UserProfile(
        user_id="demo-novice",
        domain="strength",
        answers={
            "goal": "get_stronger",
            "experience": "novice",
            "days_per_week": "3",
            "equipment": "barbell+rack at home",
            "injuries": "none",
            "minutes_per_session": "60",
        },
        derived={
            "experience": "novice",
            "days_per_week": 3,
            "injuries": "none",
            "equipment": "barbell+rack",
            "minutes_per_session": 60,
            "1rm_squat_lb": 185,
            "1rm_bench_lb": 135,
            "1rm_deadlift_lb": 225,
        },
    ),
    "intermediate_hypertrophy_shoulder": UserProfile(
        user_id="demo-hyp-shoulder",
        domain="hypertrophy",
        answers={
            "goal": "build_muscle",
            "experience": "intermediate, 2 years lifting",
            "days_per_week": "4",
            "equipment": "full commercial gym",
            "injuries": "right shoulder impingement — avoid overhead pressing",
            "minutes_per_session": "75",
        },
        derived={
            "experience": "intermediate",
            "days_per_week": 4,
            "injuries": "right shoulder impingement, avoid overhead pressing",
            "equipment": "full_gym",
            "minutes_per_session": 75,
        },
    ),
    "weight_loss_dumbbells_only": UserProfile(
        user_id="demo-weightloss",
        domain="conditioning",
        answers={
            "goal": "lose_weight",
            "experience": "beginner, restarting after 5 years off",
            "days_per_week": "5",
            "equipment": "dumbbells only at home, up to 50lb pairs",
            "injuries": "occasional low-back tightness",
            "minutes_per_session": "45",
        },
        derived={
            "experience": "beginner",
            "days_per_week": 5,
            "injuries": "low back tightness — avoid heavy bilateral hinging",
            "equipment": "dumbbell",
            "minutes_per_session": 45,
        },
    ),
}


def main() -> int:
    choice = os.environ.get("DEMO_PROFILE", "novice_strength")
    if choice not in PROFILES:
        print(f"Unknown DEMO_PROFILE={choice}. Options: {list(PROFILES)}")
        return 2

    profile = PROFILES[choice]
    llm = LLMClient()

    print(f"=== AI Program Demo — profile: {choice} ===")
    print(f"provider={llm.provider_name} default_model={llm.model}")
    print(f"used profile.derived={json.dumps(profile.derived, default=str)}")
    print()

    t0 = time.time()
    program = build_program(profile, llm)
    elapsed = time.time() - t0

    print(f"=== Generated in {elapsed:.1f}s ===\n")
    print("Rationale:")
    print(f"  {program.split.rationale}\n")

    for plan in program.days:
        spec = plan.spec
        print(f"--- Day {spec.day_index}: {spec.name} "
              f"({spec.target_minutes} min, focus: {spec.pattern_focus}) ---")
        print(f"  primary:   {spec.primary_muscles}")
        print(f"  secondary: {spec.secondary_muscles}")
        if not plan.exercises:
            print("  (no exercises picked)")
        for i, pick in enumerate(plan.exercises, 1):
            print(f"  {i}. [{pick.slot}] {pick.catalog_name}")
            print(f"       — {pick.rationale}")
        print()

    if program.issues:
        print(f"=== Validation issues ({len(program.issues)}) ===")
        for issue in program.issues:
            print(f"  day {issue.day_index} :: {issue.catalog_name} :: {issue.issue}")
    else:
        print("=== No validation issues ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
