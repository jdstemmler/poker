"""Card, Deck, and hand representation."""

from __future__ import annotations

import random
from enum import IntEnum, Enum
from typing import Optional


class Suit(str, Enum):
    HEARTS = "h"
    DIAMONDS = "d"
    CLUBS = "c"
    SPADES = "s"


class Rank(IntEnum):
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14


RANK_SYMBOLS = {
    Rank.TWO: "2",
    Rank.THREE: "3",
    Rank.FOUR: "4",
    Rank.FIVE: "5",
    Rank.SIX: "6",
    Rank.SEVEN: "7",
    Rank.EIGHT: "8",
    Rank.NINE: "9",
    Rank.TEN: "T",
    Rank.JACK: "J",
    Rank.QUEEN: "Q",
    Rank.KING: "K",
    Rank.ACE: "A",
}

SUIT_SYMBOLS = {
    Suit.HEARTS: "♥",
    Suit.DIAMONDS: "♦",
    Suit.CLUBS: "♣",
    Suit.SPADES: "♠",
}


class Card:
    __slots__ = ("rank", "suit")

    def __init__(self, rank: Rank, suit: Suit) -> None:
        self.rank = rank
        self.suit = suit

    def __repr__(self) -> str:
        return f"{RANK_SYMBOLS[self.rank]}{self.suit.value}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Card):
            return NotImplemented
        return self.rank == other.rank and self.suit == other.suit

    def __hash__(self) -> int:
        return hash((self.rank, self.suit))

    def to_dict(self) -> dict:
        return {"rank": self.rank.value, "suit": self.suit.value}

    @classmethod
    def from_dict(cls, data: dict) -> Card:
        return cls(Rank(data["rank"]), Suit(data["suit"]))

    @classmethod
    def from_str(cls, s: str) -> Card:
        """Parse 'Ah', 'Ts', '2c' etc."""
        rank_char = s[0].upper()
        suit_char = s[1].lower()
        rank_map = {v: k for k, v in RANK_SYMBOLS.items()}
        return cls(rank_map[rank_char], Suit(suit_char))


class Deck:
    """Standard 52-card deck with shuffle and deal."""

    def __init__(self) -> None:
        self._cards: list[Card] = [
            Card(rank, suit) for suit in Suit for rank in Rank
        ]
        self.shuffle()

    def shuffle(self) -> None:
        random.shuffle(self._cards)

    def deal(self, n: int = 1) -> list[Card]:
        if n > len(self._cards):
            raise ValueError("Not enough cards in deck")
        dealt = self._cards[:n]
        self._cards = self._cards[n:]
        return dealt

    def deal_one(self) -> Card:
        return self.deal(1)[0]

    @property
    def remaining(self) -> int:
        return len(self._cards)
