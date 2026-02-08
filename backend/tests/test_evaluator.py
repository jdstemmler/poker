"""Tests for the hand evaluator."""

import pytest
from app.cards import Card, Rank, Suit
from app.evaluator import (
    HandCategory,
    HandRank,
    HAND_NAMES,
    _evaluate_five,
    evaluate,
    determine_winners,
)


def _cards(s: str) -> list[Card]:
    """Parse a space-separated string of card codes into Card objects."""
    return [Card.from_str(c) for c in s.split()]


# ── Five-card evaluation ─────────────────────────────────────────────

class TestEvaluateFive:
    def test_high_card(self):
        hand = _cards("2h 5c 7d 9s Kh")
        r = _evaluate_five(hand)
        assert r.category == HandCategory.HIGH_CARD
        assert r.tiebreakers[0] == Rank.KING

    def test_one_pair(self):
        hand = _cards("3h 3d 7c Ts Ah")
        r = _evaluate_five(hand)
        assert r.category == HandCategory.ONE_PAIR
        assert r.tiebreakers[0] == Rank.THREE

    def test_two_pair(self):
        hand = _cards("Jh Jd 4c 4s 9h")
        r = _evaluate_five(hand)
        assert r.category == HandCategory.TWO_PAIR
        assert r.tiebreakers[0] == Rank.JACK
        assert r.tiebreakers[1] == Rank.FOUR
        assert r.tiebreakers[2] == Rank.NINE

    def test_three_of_a_kind(self):
        hand = _cards("8h 8d 8c 3s Kh")
        r = _evaluate_five(hand)
        assert r.category == HandCategory.THREE_OF_A_KIND
        assert r.tiebreakers[0] == Rank.EIGHT

    def test_straight(self):
        hand = _cards("5h 6d 7c 8s 9h")
        r = _evaluate_five(hand)
        assert r.category == HandCategory.STRAIGHT
        assert r.tiebreakers == (9,)

    def test_straight_ace_high(self):
        hand = _cards("Th Jd Qc Ks Ah")
        r = _evaluate_five(hand)
        assert r.category == HandCategory.STRAIGHT
        assert r.tiebreakers == (Rank.ACE,)

    def test_straight_ace_low(self):
        """A-2-3-4-5 wheel should be a 5-high straight."""
        hand = _cards("Ah 2d 3c 4s 5h")
        r = _evaluate_five(hand)
        assert r.category == HandCategory.STRAIGHT
        assert r.tiebreakers == (5,)

    def test_flush(self):
        hand = _cards("2h 5h 8h Jh Kh")
        r = _evaluate_five(hand)
        assert r.category == HandCategory.FLUSH
        assert r.tiebreakers[0] == Rank.KING

    def test_full_house(self):
        hand = _cards("Qh Qd Qc 7s 7h")
        r = _evaluate_five(hand)
        assert r.category == HandCategory.FULL_HOUSE
        assert r.tiebreakers == (Rank.QUEEN, Rank.SEVEN)

    def test_four_of_a_kind(self):
        hand = _cards("9h 9d 9c 9s 3h")
        r = _evaluate_five(hand)
        assert r.category == HandCategory.FOUR_OF_A_KIND
        assert r.tiebreakers == (Rank.NINE, Rank.THREE)

    def test_straight_flush(self):
        hand = _cards("4h 5h 6h 7h 8h")
        r = _evaluate_five(hand)
        assert r.category == HandCategory.STRAIGHT_FLUSH
        assert r.tiebreakers == (8,)

    def test_royal_flush(self):
        hand = _cards("Th Jh Qh Kh Ah")
        r = _evaluate_five(hand)
        assert r.category == HandCategory.ROYAL_FLUSH
        assert r.tiebreakers == (Rank.ACE,)

    def test_straight_flush_ace_low(self):
        hand = _cards("Ah 2h 3h 4h 5h")
        r = _evaluate_five(hand)
        assert r.category == HandCategory.STRAIGHT_FLUSH
        assert r.tiebreakers == (5,)


# ── HandRank comparison ──────────────────────────────────────────────

class TestHandRankComparison:
    def test_flush_beats_straight(self):
        straight = _evaluate_five(_cards("5h 6d 7c 8s 9h"))
        flush = _evaluate_five(_cards("2h 5h 8h Jh Kh"))
        assert flush > straight

    def test_full_house_beats_flush(self):
        flush = _evaluate_five(_cards("2h 5h 8h Jh Kh"))
        fh = _evaluate_five(_cards("Qh Qd Qc 7s 7h"))
        assert fh > flush

    def test_royal_flush_beats_four_of_a_kind(self):
        quads = _evaluate_five(_cards("9h 9d 9c 9s Ah"))
        royal = _evaluate_five(_cards("Th Jh Qh Kh Ah"))
        assert royal > quads

    def test_pair_vs_pair_kicker(self):
        pair_a = _evaluate_five(_cards("Ah Ad Kh 7c 3s"))
        pair_b = _evaluate_five(_cards("Ah Ad Qh 7c 3s"))
        assert pair_a > pair_b  # King kicker beats Queen kicker

    def test_equal_hands(self):
        a = _evaluate_five(_cards("Ah Ad Kh 7c 3s"))
        b = _evaluate_five(_cards("As Ac Ks 7d 3h"))
        assert a == b

    def test_le_ge(self):
        low = _evaluate_five(_cards("2h 5c 7d 9s Kh"))
        high = _evaluate_five(_cards("Ah Ad Kh 7c 3s"))
        assert low <= high
        assert high >= low
        assert low <= low

    def test_name_property(self):
        r = _evaluate_five(_cards("Ah Ad Kh 7c 3s"))
        assert r.name == "One Pair"

    def test_repr(self):
        r = _evaluate_five(_cards("Ah Ad Kh 7c 3s"))
        assert "One Pair" in repr(r)


# ── Seven-card evaluation (Hold'em style) ────────────────────────────

class TestEvaluateSeven:
    def test_best_five_from_seven(self):
        # Hole: Ah Kh, Board: Qh Jh Th 3c 2d → Royal Flush
        cards = _cards("Ah Kh Qh Jh Th 3c 2d")
        r = evaluate(cards)
        assert r.category == HandCategory.ROYAL_FLUSH

    def test_full_house_from_seven(self):
        cards = _cards("Ah Ad Ac Kh Kd 3c 2d")
        r = evaluate(cards)
        assert r.category == HandCategory.FULL_HOUSE
        assert r.tiebreakers[0] == Rank.ACE

    def test_two_pair_from_seven(self):
        cards = _cards("Ah Ad Kh Kd 3c 7s 2d")
        r = evaluate(cards)
        assert r.category == HandCategory.TWO_PAIR

    def test_straight_from_seven(self):
        cards = _cards("3h 4d 5c 6s 7h Kd 2c")
        r = evaluate(cards)
        assert r.category == HandCategory.STRAIGHT
        assert r.tiebreakers == (7,)

    def test_too_few_cards_raises(self):
        with pytest.raises(ValueError, match="Need at least 5"):
            evaluate(_cards("Ah Kh Qh"))

    def test_exactly_five_cards(self):
        cards = _cards("Ah Kh Qh Jh 9c")
        r = evaluate(cards)
        assert r.category == HandCategory.HIGH_CARD

    def test_six_cards(self):
        cards = _cards("Ah Ad 3c 7s 2d Kh")
        r = evaluate(cards)
        assert r.category == HandCategory.ONE_PAIR


# ── determine_winners ────────────────────────────────────────────────

class TestDetermineWinners:
    def test_single_winner(self):
        hands = {
            "alice": evaluate(_cards("Ah Ad Kh Qd Ts 3c 2d")),
            "bob": evaluate(_cards("Kh Kd 3c 7s 2d 9h 4c")),
        }
        winners = determine_winners(hands)
        assert winners == ["alice"]

    def test_tie(self):
        # Both have Ace-high flush
        hands = {
            "alice": evaluate(_cards("Ah 2h 5h 8h Kh Jd 3c")),
            "bob": evaluate(_cards("As 2s 5s 8s Ks Jd 3c")),
        }
        winners = determine_winners(hands)
        assert set(winners) == {"alice", "bob"}

    def test_empty(self):
        assert determine_winners({}) == []

    def test_three_way_with_one_winner(self):
        hands = {
            "alice": evaluate(_cards("Ah Ad Kh Qd Ts 3c 2d")),
            "bob": evaluate(_cards("Kh Kd 3c 7s 2d 9h 4c")),
            "carol": evaluate(_cards("2h 5c 7d 9s Kh 3d 4h")),
        }
        winners = determine_winners(hands)
        assert winners == ["alice"]


# ── Hand names table ─────────────────────────────────────────────────

class TestHandNames:
    def test_all_categories_named(self):
        for cat in HandCategory:
            assert cat in HAND_NAMES
            assert isinstance(HAND_NAMES[cat], str)
