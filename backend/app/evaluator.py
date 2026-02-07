"""Texas Hold'em hand evaluator.

Evaluates the best 5-card hand from any combination of cards.
Returns a HandRank tuple that can be compared directly (higher is better).
"""

from __future__ import annotations

from collections import Counter
from enum import IntEnum
from itertools import combinations
from typing import Sequence

from app.cards import Card, Rank


class HandCategory(IntEnum):
    HIGH_CARD = 0
    ONE_PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8
    ROYAL_FLUSH = 9


HAND_NAMES = {
    HandCategory.HIGH_CARD: "High Card",
    HandCategory.ONE_PAIR: "One Pair",
    HandCategory.TWO_PAIR: "Two Pair",
    HandCategory.THREE_OF_A_KIND: "Three of a Kind",
    HandCategory.STRAIGHT: "Straight",
    HandCategory.FLUSH: "Flush",
    HandCategory.FULL_HOUSE: "Full House",
    HandCategory.FOUR_OF_A_KIND: "Four of a Kind",
    HandCategory.STRAIGHT_FLUSH: "Straight Flush",
    HandCategory.ROYAL_FLUSH: "Royal Flush",
}


class HandRank:
    """Comparable hand ranking.

    Composed of (category, primary_ranks...) where ranks are tuples
    ordered by significance.  Two HandRanks can be compared with < > ==.
    """

    __slots__ = ("category", "tiebreakers", "cards")

    def __init__(
        self,
        category: HandCategory,
        tiebreakers: tuple[int, ...],
        cards: list[Card],
    ) -> None:
        self.category = category
        self.tiebreakers = tiebreakers
        self.cards = cards

    @property
    def _key(self) -> tuple[int, ...]:
        return (self.category,) + self.tiebreakers

    def __lt__(self, other: HandRank) -> bool:
        return self._key < other._key

    def __gt__(self, other: HandRank) -> bool:
        return self._key > other._key

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HandRank):
            return NotImplemented
        return self._key == other._key

    def __le__(self, other: HandRank) -> bool:
        return self._key <= other._key

    def __ge__(self, other: HandRank) -> bool:
        return self._key >= other._key

    @property
    def name(self) -> str:
        return HAND_NAMES[self.category]

    def __repr__(self) -> str:
        return f"HandRank({self.name}, {self.tiebreakers})"


def _evaluate_five(cards: list[Card]) -> HandRank:
    """Evaluate exactly 5 cards and return their HandRank."""
    assert len(cards) == 5

    ranks = sorted([c.rank for c in cards], reverse=True)
    suits = [c.suit for c in cards]
    rank_counts = Counter(ranks)

    is_flush = len(set(suits)) == 1

    # Check for straight
    is_straight = False
    high_card = ranks[0]

    unique_ranks = sorted(set(ranks), reverse=True)
    if len(unique_ranks) == 5:
        if unique_ranks[0] - unique_ranks[4] == 4:
            is_straight = True
            high_card = unique_ranks[0]
        # Ace-low straight (A-2-3-4-5 = wheel)
        elif unique_ranks == [14, 5, 4, 3, 2]:
            is_straight = True
            high_card = 5  # 5-high straight

    if is_straight and is_flush:
        if high_card == 14 and min(ranks) == 10:
            return HandRank(HandCategory.ROYAL_FLUSH, (14,), cards)
        return HandRank(HandCategory.STRAIGHT_FLUSH, (high_card,), cards)

    # Group by count for pair/trips/quads evaluation
    # Sort by (count desc, rank desc)
    groups = sorted(rank_counts.items(), key=lambda x: (x[1], x[0]), reverse=True)

    if groups[0][1] == 4:
        quad_rank = groups[0][0]
        kicker = groups[1][0]
        return HandRank(HandCategory.FOUR_OF_A_KIND, (quad_rank, kicker), cards)

    if groups[0][1] == 3 and groups[1][1] == 2:
        trip_rank = groups[0][0]
        pair_rank = groups[1][0]
        return HandRank(HandCategory.FULL_HOUSE, (trip_rank, pair_rank), cards)

    if is_flush:
        return HandRank(HandCategory.FLUSH, tuple(ranks), cards)

    if is_straight:
        return HandRank(HandCategory.STRAIGHT, (high_card,), cards)

    if groups[0][1] == 3:
        trip_rank = groups[0][0]
        kickers = sorted([r for r, c in groups if c == 1], reverse=True)
        return HandRank(
            HandCategory.THREE_OF_A_KIND, (trip_rank,) + tuple(kickers), cards
        )

    if groups[0][1] == 2 and groups[1][1] == 2:
        pair_ranks = sorted([r for r, c in groups if c == 2], reverse=True)
        kicker = [r for r, c in groups if c == 1][0]
        return HandRank(
            HandCategory.TWO_PAIR, (pair_ranks[0], pair_ranks[1], kicker), cards
        )

    if groups[0][1] == 2:
        pair_rank = groups[0][0]
        kickers = sorted([r for r, c in groups if c == 1], reverse=True)
        return HandRank(
            HandCategory.ONE_PAIR, (pair_rank,) + tuple(kickers), cards
        )

    return HandRank(HandCategory.HIGH_CARD, tuple(ranks), cards)


def evaluate(cards: Sequence[Card]) -> HandRank:
    """Evaluate the best 5-card hand from any number of cards (typically 5-7).

    For Hold'em, pass 2 hole cards + up to 5 community cards.
    """
    if len(cards) < 5:
        raise ValueError(f"Need at least 5 cards, got {len(cards)}")

    if len(cards) == 5:
        return _evaluate_five(list(cards))

    best: HandRank | None = None
    for combo in combinations(cards, 5):
        rank = _evaluate_five(list(combo))
        if best is None or rank > best:
            best = rank

    assert best is not None
    return best


def determine_winners(
    player_hands: dict[str, HandRank],
) -> list[str]:
    """Given {player_id: HandRank}, return list of winner player_ids (ties possible)."""
    if not player_hands:
        return []

    best_rank = max(player_hands.values())
    return [pid for pid, rank in player_hands.items() if rank == best_rank]
