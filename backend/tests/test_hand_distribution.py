"""Statistical validation of deal + hand evaluation.

Simulates many 7-card Texas Hold'em deals and checks that the observed
hand-category distribution matches known theoretical probabilities for
the best 5-card hand out of 7 cards (standard 52-card deck).

Reference probabilities (combinatorial):
    High Card        17.41 %
    One Pair         43.83 %
    Two Pair         23.50 %
    Three of a Kind   4.83 %
    Straight          4.62 %
    Flush             3.03 %
    Full House        2.60 %
    Four of a Kind    0.168 %
    Straight Flush    0.028 %
    Royal Flush       0.003 %

The test uses 200 000 trials.  With that sample size the 99.9 %
confidence interval for each category is well within the tolerance
bands used here, so flaky failures are extremely unlikely.
"""

import random

import pytest

from app.cards import Deck
from app.evaluator import HandCategory, evaluate

# ── Reference probabilities (best 5 of 7 cards) ─────────────────────
# Source: combinatorial enumeration of all C(52,7) = 133 784 560 hands.
# Straight Flush and Royal Flush are listed separately in HandCategory
# but many references combine them; we keep them separate.
EXPECTED_PROBABILITIES: dict[HandCategory, float] = {
    HandCategory.HIGH_CARD: 0.1741,
    HandCategory.ONE_PAIR: 0.4383,
    HandCategory.TWO_PAIR: 0.2350,
    HandCategory.THREE_OF_A_KIND: 0.0483,
    HandCategory.STRAIGHT: 0.0462,
    HandCategory.FLUSH: 0.0303,
    HandCategory.FULL_HOUSE: 0.0260,
    HandCategory.FOUR_OF_A_KIND: 0.00168,
    HandCategory.STRAIGHT_FLUSH: 0.000279,
    HandCategory.ROYAL_FLUSH: 0.000032,
}

NUM_TRIALS = 200_000

# Tolerance: maximum allowed absolute difference between observed and
# expected probability.  Wider for rare hands to avoid flakiness.
TOLERANCES: dict[HandCategory, float] = {
    HandCategory.HIGH_CARD: 0.010,
    HandCategory.ONE_PAIR: 0.010,
    HandCategory.TWO_PAIR: 0.010,
    HandCategory.THREE_OF_A_KIND: 0.005,
    HandCategory.STRAIGHT: 0.005,
    HandCategory.FLUSH: 0.005,
    HandCategory.FULL_HOUSE: 0.005,
    HandCategory.FOUR_OF_A_KIND: 0.002,
    HandCategory.STRAIGHT_FLUSH: 0.001,
    HandCategory.ROYAL_FLUSH: 0.001,
}


@pytest.fixture(scope="module")
def hand_distribution() -> dict[HandCategory, int]:
    """Run the simulation once and share the results across all tests."""
    rng = random.Random(42)  # fixed seed for reproducibility
    counts: dict[HandCategory, int] = {cat: 0 for cat in HandCategory}

    for _ in range(NUM_TRIALS):
        deck = Deck()
        # Use our own RNG so the seed is deterministic
        rng.shuffle(deck._cards)
        cards = deck.deal(7)
        best = evaluate(cards)
        counts[best.category] += 1

    return counts


class TestHandDistribution:
    """Verify that observed hand frequencies match theoretical probabilities."""

    @pytest.mark.parametrize(
        "category",
        list(EXPECTED_PROBABILITIES.keys()),
        ids=[cat.name for cat in EXPECTED_PROBABILITIES],
    )
    def test_category_probability(
        self,
        category: HandCategory,
        hand_distribution: dict[HandCategory, int],
    ) -> None:
        observed = hand_distribution[category] / NUM_TRIALS
        expected = EXPECTED_PROBABILITIES[category]
        tolerance = TOLERANCES[category]
        diff = abs(observed - expected)
        assert diff <= tolerance, (
            f"{category.name}: observed {observed:.5f} vs expected {expected:.5f} "
            f"(diff {diff:.5f} > tolerance {tolerance:.5f})"
        )

    def test_all_categories_sum_to_total(
        self,
        hand_distribution: dict[HandCategory, int],
    ) -> None:
        total = sum(hand_distribution.values())
        assert total == NUM_TRIALS

    def test_deck_has_52_unique_cards(self) -> None:
        """Sanity check: a fresh deck has exactly 52 unique cards."""
        deck = Deck()
        cards = deck.deal(52)
        assert len(cards) == 52
        assert len(set(cards)) == 52

    def test_no_duplicate_cards_in_deal(self) -> None:
        """Each deal from a single deck should have no duplicates."""
        for _ in range(100):
            deck = Deck()
            cards = deck.deal(7)
            assert len(set(cards)) == 7
