"""Variety guard tests (Rubric D2)."""

from coach.variety import check


def test_accepts_distinct_text():
    v = check("Laptop's about to close — Lower A, shoes by the door.",
              ["Window's open: Lower B fits at 5:30. Start when you stand up."])
    assert v.accept


def test_rejects_near_duplicate():
    v = check("Laptop's about to close — Lower A, shoes by the door.",
              ["Laptop's about to close — Lower A, shoes by the door."])
    assert not v.accept
    assert v.avoid_phrases


def test_rejects_same_opening_bigram():
    v = check("Laptop's closing in 10 — Lower B fits the gap.",
              ["Laptop's about to close — Lower A, shoes by the door."])
    assert not v.accept


def test_empty_rejected():
    assert not check("", []).accept
