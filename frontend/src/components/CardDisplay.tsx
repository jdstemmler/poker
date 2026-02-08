/** Card display — visual playing card components. */

import type { CardData } from "../types";

const RANK_MAP: Record<number, string> = {
  2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9",
  10: "10", 11: "J", 12: "Q", 13: "K", 14: "A",
};

const SUIT_MAP: Record<string, { symbol: string; cls: string }> = {
  h: { symbol: "♥", cls: "suit-red" },
  d: { symbol: "♦", cls: "suit-red" },
  c: { symbol: "♣", cls: "suit-dark" },
  s: { symbol: "♠", cls: "suit-dark" },
};

export function CardDisplay({ card, size = "md" }: { card: CardData; size?: "sm" | "md" | "lg" }) {
  const rank = RANK_MAP[card.rank] ?? "?";
  const suit = SUIT_MAP[card.suit] ?? { symbol: "?", cls: "suit-dark" };

  return (
    <span className={`card-display card-${size} ${suit.cls}`}>
      <span className="card-rank">{rank}</span>
      <span className="card-suit">{suit.symbol}</span>
    </span>
  );
}

export function CardBack({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  return (
    <span className={`card-display card-back card-${size}`}>
      <span className="card-back-pattern" />
    </span>
  );
}

export function CardList({ cards, size = "md" }: { cards: CardData[]; size?: "sm" | "md" | "lg" }) {
  return (
    <span className="card-list">
      {cards.map((c, i) => (
        <CardDisplay key={i} card={c} size={size} />
      ))}
    </span>
  );
}
