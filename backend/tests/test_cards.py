"""Tests for Card, Deck, and related helpers."""

import pytest
from app.cards import Card, Deck, Rank, Suit, RANK_SYMBOLS, SUIT_SYMBOLS


# ── Card basics ──────────────────────────────────────────────────────

class TestCard:
    def test_creation(self):
        c = Card(Rank.ACE, Suit.SPADES)
        assert c.rank == Rank.ACE
        assert c.suit == Suit.SPADES

    def test_repr(self):
        assert repr(Card(Rank.ACE, Suit.HEARTS)) == "Ah"
        assert repr(Card(Rank.TEN, Suit.CLUBS)) == "Tc"
        assert repr(Card(Rank.TWO, Suit.DIAMONDS)) == "2d"

    def test_equality(self):
        a = Card(Rank.KING, Suit.SPADES)
        b = Card(Rank.KING, Suit.SPADES)
        assert a == b

    def test_inequality(self):
        a = Card(Rank.KING, Suit.SPADES)
        b = Card(Rank.KING, Suit.HEARTS)
        assert a != b

    def test_hash_consistency(self):
        a = Card(Rank.QUEEN, Suit.DIAMONDS)
        b = Card(Rank.QUEEN, Suit.DIAMONDS)
        assert hash(a) == hash(b)
        s = {a, b}
        assert len(s) == 1

    def test_eq_with_non_card(self):
        c = Card(Rank.ACE, Suit.SPADES)
        assert c != "As"
        assert c.__eq__("As") is NotImplemented

    def test_to_dict(self):
        c = Card(Rank.JACK, Suit.HEARTS)
        d = c.to_dict()
        assert d == {"rank": 11, "suit": "h"}

    def test_from_dict(self):
        c = Card.from_dict({"rank": 14, "suit": "s"})
        assert c.rank == Rank.ACE
        assert c.suit == Suit.SPADES

    def test_roundtrip_dict(self):
        original = Card(Rank.SEVEN, Suit.CLUBS)
        restored = Card.from_dict(original.to_dict())
        assert original == restored

    def test_from_str(self):
        assert Card.from_str("Ah") == Card(Rank.ACE, Suit.HEARTS)
        assert Card.from_str("Ts") == Card(Rank.TEN, Suit.SPADES)
        assert Card.from_str("2c") == Card(Rank.TWO, Suit.CLUBS)
        assert Card.from_str("Kd") == Card(Rank.KING, Suit.DIAMONDS)

    def test_from_str_case_insensitive(self):
        assert Card.from_str("ah") == Card.from_str("Ah")


# ── Rank / Suit enums ───────────────────────────────────────────────

class TestEnums:
    def test_rank_values(self):
        assert Rank.TWO == 2
        assert Rank.ACE == 14
        assert len(Rank) == 13

    def test_suit_values(self):
        assert Suit.HEARTS.value == "h"
        assert len(Suit) == 4

    def test_rank_symbols_complete(self):
        assert len(RANK_SYMBOLS) == 13
        for r in Rank:
            assert r in RANK_SYMBOLS

    def test_suit_symbols_complete(self):
        assert len(SUIT_SYMBOLS) == 4
        for s in Suit:
            assert s in SUIT_SYMBOLS


# ── Deck ─────────────────────────────────────────────────────────────

class TestDeck:
    def test_deck_has_52_cards(self):
        d = Deck()
        assert d.remaining == 52

    def test_deck_all_unique(self):
        d = Deck()
        cards = d.deal(52)
        assert len(set(cards)) == 52

    def test_deck_has_4_of_each_rank(self):
        d = Deck()
        cards = d.deal(52)
        from collections import Counter
        rank_counts = Counter(c.rank for c in cards)
        for r in Rank:
            assert rank_counts[r] == 4

    def test_deck_has_13_of_each_suit(self):
        d = Deck()
        cards = d.deal(52)
        from collections import Counter
        suit_counts = Counter(c.suit for c in cards)
        for s in Suit:
            assert suit_counts[s] == 13

    def test_deal_reduces_remaining(self):
        d = Deck()
        d.deal(5)
        assert d.remaining == 47

    def test_deal_one(self):
        d = Deck()
        c = d.deal_one()
        assert isinstance(c, Card)
        assert d.remaining == 51

    def test_deal_too_many_raises(self):
        d = Deck()
        d.deal(50)
        with pytest.raises(ValueError, match="Not enough cards"):
            d.deal(5)

    def test_shuffle_changes_order(self):
        """Shuffling should (almost certainly) change the deck order."""
        d1 = Deck()
        d1._cards = [Card(r, s) for s in Suit for r in Rank]  # fixed order
        order_before = [repr(c) for c in d1._cards]
        d1.shuffle()
        order_after = [repr(c) for c in d1._cards]
        # Extremely unlikely to be the same
        assert order_before != order_after

    def test_to_dict_from_dict_roundtrip(self):
        d = Deck()
        original_cards = [repr(c) for c in d._cards]
        data = d.to_dict()
        d2 = Deck.from_dict(data)
        restored_cards = [repr(c) for c in d2._cards]
        assert original_cards == restored_cards

    def test_from_dict_preserves_order(self):
        """from_dict should NOT re-shuffle — preserves serialized order."""
        d = Deck()
        # Deal a few cards so it's a partial deck
        d.deal(10)
        data = d.to_dict()
        d2 = Deck.from_dict(data)
        assert d.remaining == d2.remaining
        for c1, c2 in zip(d._cards, d2._cards):
            assert c1 == c2
