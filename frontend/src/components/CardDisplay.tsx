/** Card display helper. */

import type { CardData } from "../types";

const RANK_MAP: Record<number, string> = {
  2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9",
  10: "T", 11: "J", 12: "Q", 13: "K", 14: "A",
};

const SUIT_MAP: Record<string, { symbol: string; color: string }> = {
  h: { symbol: "♥", color: "#e74c3c" },
  d: { symbol: "♦", color: "#3498db" },
  c: { symbol: "♣", color: "#2ecc71" },
  s: { symbol: "♠", color: "#ecf0f1" },
};

export function CardDisplay({ card }: { card: CardData }) {
  const rank = RANK_MAP[card.rank] ?? "?";
  const suit = SUIT_MAP[card.suit] ?? { symbol: "?", color: "#888" };

  return (
    <span className="card-display" style={{ color: suit.color }}>
      {rank}{suit.symbol}
    </span>
  );
}

export function CardBack() {
  return <span className="card-display card-back">🂠</span>;
}

export function CardList({ cards }: { cards: CardData[] }) {
  return (
    <span className="card-list">
      {cards.map((c, i) => (
        <CardDisplay key={i} card={c} />
      ))}
    </span>
  );
}
