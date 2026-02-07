"""Core game engine for No-Limit Texas Hold'em.

Manages the authoritative game state: dealing, betting rounds,
pot management, showdown, dealer rotation, and hand lifecycle.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from app.cards import Card, Deck
from app.evaluator import HandCategory, evaluate, determine_winners


class Street(str, Enum):
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"


class PlayerAction(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    RAISE = "raise"
    ALL_IN = "all_in"


class PlayerState:
    """Per-hand state for a single player."""

    def __init__(self, player_id: str, name: str, chips: int) -> None:
        self.player_id = player_id
        self.name = name
        self.chips = chips
        self.hole_cards: list[Card] = []
        self.bet_this_round: int = 0
        self.bet_this_hand: int = 0
        self.folded: bool = False
        self.all_in: bool = False
        self.has_acted: bool = False
        self.is_sitting_out: bool = False

    @property
    def is_active(self) -> bool:
        """Still in the hand and can act."""
        return not self.folded and not self.all_in and self.chips > 0

    def reset_for_new_hand(self) -> None:
        self.hole_cards = []
        self.bet_this_round = 0
        self.bet_this_hand = 0
        self.folded = False
        self.all_in = False
        self.has_acted = False

    def reset_for_new_round(self) -> None:
        self.bet_this_round = 0
        self.has_acted = False

    def to_dict(self, reveal_cards: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "player_id": self.player_id,
            "name": self.name,
            "chips": self.chips,
            "bet_this_round": self.bet_this_round,
            "bet_this_hand": self.bet_this_hand,
            "folded": self.folded,
            "all_in": self.all_in,
            "is_sitting_out": self.is_sitting_out,
        }
        if reveal_cards and self.hole_cards:
            d["hole_cards"] = [c.to_dict() for c in self.hole_cards]
        return d


class HandHistory:
    """Records actions for a single hand."""

    def __init__(self, hand_number: int) -> None:
        self.hand_number = hand_number
        self.actions: list[dict[str, Any]] = []
        self.community_cards: list[list[dict]] = []
        self.winners: list[dict[str, Any]] = []

    def record_action(
        self, player_id: str, action: PlayerAction, amount: int, street: Street
    ) -> None:
        self.actions.append(
            {
                "player_id": player_id,
                "action": action.value,
                "amount": amount,
                "street": street.value,
            }
        )

    def record_community(self, cards: list[Card]) -> None:
        self.community_cards.append([c.to_dict() for c in cards])

    def record_winners(self, winners: list[dict[str, Any]]) -> None:
        self.winners = winners

    def to_dict(self) -> dict[str, Any]:
        return {
            "hand_number": self.hand_number,
            "actions": self.actions,
            "community_cards": self.community_cards,
            "winners": self.winners,
        }


class GameEngine:
    """Manages a single poker table/game."""

    def __init__(
        self,
        game_code: str,
        players: list[dict[str, Any]],
        starting_chips: int,
        small_blind: int,
        big_blind: int,
        allow_rebuys: bool = True,
    ) -> None:
        self.game_code = game_code
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.allow_rebuys = allow_rebuys
        self.starting_chips = starting_chips

        # Seat players in order
        self.seats: list[PlayerState] = []
        for p in players:
            ps = PlayerState(p["id"], p["name"], starting_chips)
            self.seats.append(ps)

        # Dealer button position (index into self.seats)
        self.dealer_idx: int = 0
        self.hand_number: int = 0

        # Current hand state
        self.deck: Optional[Deck] = None
        self.community_cards: list[Card] = []
        self.street: Street = Street.PREFLOP
        self.pot: int = 0
        self.current_bet: int = 0
        self.action_on_idx: int = 0
        self.min_raise: int = big_blind
        self.hand_active: bool = False
        self.last_raiser_idx: Optional[int] = None

        # History
        self.hand_histories: list[HandHistory] = []
        self.current_history: Optional[HandHistory] = None

        # Results of the last completed hand (for UI display)
        self.last_hand_result: Optional[dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def _active_players(self) -> list[int]:
        """Indices of players still in the hand (not folded, not all-in with 0 chips)."""
        return [
            i
            for i, p in enumerate(self.seats)
            if not p.folded and not p.is_sitting_out
        ]

    def _players_who_can_act(self) -> list[int]:
        """Indices of players who can still take actions."""
        return [
            i
            for i, p in enumerate(self.seats)
            if p.is_active and not p.is_sitting_out
        ]

    def _players_in_hand(self) -> list[int]:
        """Indices of non-folded players."""
        return [
            i
            for i, p in enumerate(self.seats)
            if not p.folded and not p.is_sitting_out
        ]

    def _next_seat(self, idx: int, only_active: bool = False) -> int:
        """Find next occupied seat after idx, wrapping around."""
        n = len(self.seats)
        for offset in range(1, n + 1):
            i = (idx + offset) % n
            p = self.seats[i]
            if p.is_sitting_out:
                continue
            if only_active and not p.is_active:
                continue
            if not p.folded:
                return i
        return idx  # shouldn't happen

    # ------------------------------------------------------------------
    # Hand Lifecycle
    # ------------------------------------------------------------------

    def start_new_hand(self) -> dict[str, Any]:
        """Deal a new hand. Returns game state snapshot."""
        # Eliminate busted players (chips == 0 and no rebuys)
        for p in self.seats:
            if p.chips <= 0 and not self.allow_rebuys:
                p.is_sitting_out = True

        live_players = [i for i, p in enumerate(self.seats) if not p.is_sitting_out]
        if len(live_players) < 2:
            return self._build_state(
                message="Not enough players to continue",
                game_over=True,
            )

        self.hand_number += 1
        self.last_hand_result = None

        # Rotate dealer
        if self.hand_number > 1:
            self.dealer_idx = self._next_seat(self.dealer_idx)

        # Reset per-hand state
        for p in self.seats:
            if not p.is_sitting_out:
                p.reset_for_new_hand()

        self.deck = Deck()
        self.community_cards = []
        self.street = Street.PREFLOP
        self.pot = 0
        self.current_bet = 0
        self.min_raise = self.big_blind
        self.last_raiser_idx = None

        self.current_history = HandHistory(self.hand_number)
        self.hand_active = True

        # Deal hole cards
        for p in self.seats:
            if not p.is_sitting_out:
                p.hole_cards = self.deck.deal(2)

        # Post blinds
        self._post_blinds()

        return self._build_state()

    def _post_blinds(self) -> None:
        """Post small and big blinds."""
        live = [i for i, p in enumerate(self.seats) if not p.is_sitting_out]

        if len(live) == 2:
            # Heads-up: dealer posts small blind
            sb_idx = self.dealer_idx
            bb_idx = self._next_seat(self.dealer_idx)
        else:
            sb_idx = self._next_seat(self.dealer_idx)
            bb_idx = self._next_seat(sb_idx)

        self._force_bet(sb_idx, self.small_blind)
        self._force_bet(bb_idx, self.big_blind)

        self.current_bet = self.big_blind
        self.min_raise = self.big_blind  # min raise size = one big blind

        # Action starts after big blind
        self.action_on_idx = self._next_seat(bb_idx)

        # In preflop, the big blind acts last (gets option to raise)
        self.last_raiser_idx = bb_idx

    def _force_bet(self, idx: int, amount: int) -> int:
        """Force a player to bet (blinds/antes). Returns actual amount posted."""
        p = self.seats[idx]
        actual = min(amount, p.chips)
        p.chips -= actual
        p.bet_this_round += actual
        p.bet_this_hand += actual
        self.pot += actual
        if p.chips == 0:
            p.all_in = True
        return actual

    # ------------------------------------------------------------------
    # Action Processing
    # ------------------------------------------------------------------

    def get_valid_actions(self, player_id: str) -> list[dict[str, Any]]:
        """Return list of valid actions for the given player."""
        idx = self._find_player_idx(player_id)
        if idx is None or idx != self.action_on_idx or not self.hand_active:
            return []

        p = self.seats[idx]
        if not p.is_active:
            return []

        actions: list[dict[str, Any]] = []
        to_call = self.current_bet - p.bet_this_round

        # Fold is always available if there's a bet to call
        if to_call > 0:
            actions.append({"action": "fold"})

        # Check (only if nothing to call)
        if to_call == 0:
            actions.append({"action": "check"})

        # Call
        if to_call > 0:
            call_amount = min(to_call, p.chips)
            actions.append({"action": "call", "amount": call_amount})

        # Raise / All-in
        min_raise_to = self.current_bet + self.min_raise
        max_raise_to = p.bet_this_round + p.chips  # all-in

        if max_raise_to > self.current_bet:
            if p.chips <= to_call:
                # Can only go all-in (for a call or less)
                pass  # already covered by call
            elif max_raise_to < min_raise_to:
                # Can only all-in for less than min raise
                actions.append(
                    {"action": "all_in", "amount": p.chips}
                )
            else:
                actions.append(
                    {
                        "action": "raise",
                        "min_amount": min_raise_to - p.bet_this_round,
                        "max_amount": p.chips,
                    }
                )

        return actions

    def process_action(
        self, player_id: str, action: str, amount: int = 0
    ) -> dict[str, Any]:
        """Process a player action. Returns updated game state."""
        idx = self._find_player_idx(player_id)
        if idx is None:
            raise ValueError("Player not found")
        if idx != self.action_on_idx:
            raise ValueError("Not your turn")
        if not self.hand_active:
            raise ValueError("No active hand")

        p = self.seats[idx]
        if not p.is_active:
            raise ValueError("Player cannot act")

        to_call = self.current_bet - p.bet_this_round

        if action == PlayerAction.FOLD.value or action == "fold":
            self._do_fold(idx)
        elif action == PlayerAction.CHECK.value or action == "check":
            if to_call > 0:
                raise ValueError("Cannot check, must call or fold")
            self._do_check(idx)
        elif action == PlayerAction.CALL.value or action == "call":
            self._do_call(idx)
        elif action == PlayerAction.RAISE.value or action == "raise":
            self._do_raise(idx, amount)
        elif action == PlayerAction.ALL_IN.value or action == "all_in":
            self._do_all_in(idx)
        else:
            raise ValueError(f"Unknown action: {action}")

        # Check if hand is over (only one player left)
        in_hand = self._players_in_hand()
        if len(in_hand) == 1:
            return self._award_pot_to_last_player(in_hand[0])

        # Check if betting round is complete
        if self._is_round_complete():
            return self._advance_street()

        # Move to next player
        self.action_on_idx = self._next_seat(idx, only_active=True)
        return self._build_state()

    def _do_fold(self, idx: int) -> None:
        p = self.seats[idx]
        p.folded = True
        p.has_acted = True
        if self.current_history:
            self.current_history.record_action(
                p.player_id, PlayerAction.FOLD, 0, self.street
            )

    def _do_check(self, idx: int) -> None:
        p = self.seats[idx]
        p.has_acted = True
        if self.current_history:
            self.current_history.record_action(
                p.player_id, PlayerAction.CHECK, 0, self.street
            )

    def _do_call(self, idx: int) -> None:
        p = self.seats[idx]
        to_call = self.current_bet - p.bet_this_round
        actual = min(to_call, p.chips)
        p.chips -= actual
        p.bet_this_round += actual
        p.bet_this_hand += actual
        self.pot += actual
        p.has_acted = True
        if p.chips == 0:
            p.all_in = True
        if self.current_history:
            self.current_history.record_action(
                p.player_id, PlayerAction.CALL, actual, self.street
            )

    def _do_raise(self, idx: int, total_bet_amount: int) -> None:
        """Raise to total_bet_amount (the total amount the player puts in this round)."""
        p = self.seats[idx]
        to_call = self.current_bet - p.bet_this_round
        min_raise_to = self.current_bet + self.min_raise

        # total_bet_amount is how much the player wants to put in total this round
        if total_bet_amount < min_raise_to - p.bet_this_round and total_bet_amount < p.chips:
            raise ValueError(
                f"Raise must be at least {min_raise_to - p.bet_this_round}"
            )

        actual = min(total_bet_amount, p.chips)
        raise_size = (p.bet_this_round + actual) - self.current_bet

        p.chips -= actual
        p.bet_this_round += actual
        p.bet_this_hand += actual
        self.pot += actual

        if raise_size > 0:
            self.min_raise = max(self.min_raise, raise_size)

        self.current_bet = p.bet_this_round
        self.last_raiser_idx = idx
        p.has_acted = True

        if p.chips == 0:
            p.all_in = True

        # Reset has_acted for other active players (they need to respond)
        for i, other in enumerate(self.seats):
            if i != idx and other.is_active and not other.folded:
                other.has_acted = False

        if self.current_history:
            self.current_history.record_action(
                p.player_id, PlayerAction.RAISE, actual, self.street
            )

    def _do_all_in(self, idx: int) -> None:
        """Go all-in."""
        p = self.seats[idx]
        amount = p.chips
        new_total = p.bet_this_round + amount

        if new_total > self.current_bet:
            # This is effectively a raise
            raise_size = new_total - self.current_bet
            if raise_size >= self.min_raise:
                self.min_raise = raise_size
            self.current_bet = new_total
            self.last_raiser_idx = idx
            # Reset has_acted for others
            for i, other in enumerate(self.seats):
                if i != idx and other.is_active and not other.folded:
                    other.has_acted = False

        p.chips = 0
        p.bet_this_round = new_total
        p.bet_this_hand += amount
        self.pot += amount
        p.all_in = True
        p.has_acted = True

        if self.current_history:
            self.current_history.record_action(
                p.player_id, PlayerAction.ALL_IN, amount, self.street
            )

    # ------------------------------------------------------------------
    # Round / Street Management
    # ------------------------------------------------------------------

    def _is_round_complete(self) -> bool:
        """Check if the current betting round is complete."""
        actors = self._players_who_can_act()
        if not actors:
            return True

        for i in actors:
            p = self.seats[i]
            if not p.has_acted:
                return False
            if p.bet_this_round < self.current_bet and not p.all_in:
                return False

        return True

    def _advance_street(self) -> dict[str, Any]:
        """Move to the next street or showdown."""
        # Reset round state
        for p in self.seats:
            p.reset_for_new_round()

        self.current_bet = 0
        self.min_raise = self.big_blind
        self.last_raiser_idx = None

        # If only one (or zero) players can act, run out the board
        can_act = self._players_who_can_act()

        if self.street == Street.PREFLOP:
            self.street = Street.FLOP
            assert self.deck is not None
            self.deck.deal_one()  # burn
            flop = self.deck.deal(3)
            self.community_cards.extend(flop)
            if self.current_history:
                self.current_history.record_community(flop)
        elif self.street == Street.FLOP:
            self.street = Street.TURN
            assert self.deck is not None
            self.deck.deal_one()  # burn
            turn = self.deck.deal(1)
            self.community_cards.extend(turn)
            if self.current_history:
                self.current_history.record_community(turn)
        elif self.street == Street.TURN:
            self.street = Street.RIVER
            assert self.deck is not None
            self.deck.deal_one()  # burn
            river = self.deck.deal(1)
            self.community_cards.extend(river)
            if self.current_history:
                self.current_history.record_community(river)
        elif self.street == Street.RIVER:
            return self._showdown()

        # If fewer than 2 players can act, run out remaining streets
        if len(can_act) < 2:
            return self._advance_street()

        # Set action to first active player after dealer
        live = [i for i, p in enumerate(self.seats) if not p.is_sitting_out]
        if len(live) == 2:
            # Heads-up: dealer acts first post-flop
            self.action_on_idx = self.dealer_idx
            if not self.seats[self.action_on_idx].is_active:
                self.action_on_idx = self._next_seat(
                    self.dealer_idx, only_active=True
                )
        else:
            self.action_on_idx = self._next_seat(
                self.dealer_idx, only_active=True
            )

        return self._build_state()

    # ------------------------------------------------------------------
    # Showdown & Pot Award
    # ------------------------------------------------------------------

    def _showdown(self) -> dict[str, Any]:
        """Evaluate hands, determine winners, award pot."""
        self.street = Street.SHOWDOWN

        in_hand = self._players_in_hand()
        player_hands: dict[str, Any] = {}

        for i in in_hand:
            p = self.seats[i]
            all_cards = p.hole_cards + self.community_cards
            if len(all_cards) >= 5:
                hand_rank = evaluate(all_cards)
                player_hands[p.player_id] = hand_rank

        winner_ids = determine_winners(player_hands)
        share = self.pot // len(winner_ids) if winner_ids else 0
        remainder = self.pot - (share * len(winner_ids)) if winner_ids else 0

        result_winners = []
        for i, pid in enumerate(winner_ids):
            winnings = share + (1 if i < remainder else 0)
            player = self._find_player(pid)
            if player:
                player.chips += winnings
                result_winners.append(
                    {
                        "player_id": pid,
                        "name": player.name,
                        "winnings": winnings,
                        "hand": player_hands[pid].name
                        if pid in player_hands
                        else "Unknown",
                    }
                )

        self.last_hand_result = {
            "winners": result_winners,
            "pot": self.pot,
            "community_cards": [c.to_dict() for c in self.community_cards],
            "player_hands": {
                self.seats[i].player_id: {
                    "cards": [c.to_dict() for c in self.seats[i].hole_cards],
                    "hand_name": player_hands[self.seats[i].player_id].name
                    if self.seats[i].player_id in player_hands
                    else None,
                }
                for i in in_hand
            },
        }

        if self.current_history:
            self.current_history.record_winners(result_winners)
            self.hand_histories.append(self.current_history)
            self.current_history = None

        self.pot = 0
        self.hand_active = False

        return self._build_state(showdown=True)

    def _award_pot_to_last_player(self, winner_idx: int) -> dict[str, Any]:
        """Everyone else folded — award pot without showdown."""
        winner = self.seats[winner_idx]
        winner.chips += self.pot

        self.last_hand_result = {
            "winners": [
                {
                    "player_id": winner.player_id,
                    "name": winner.name,
                    "winnings": self.pot,
                    "hand": "Last player standing",
                }
            ],
            "pot": self.pot,
            "community_cards": [c.to_dict() for c in self.community_cards],
            "player_hands": {},
        }

        if self.current_history:
            self.current_history.record_winners(self.last_hand_result["winners"])
            self.hand_histories.append(self.current_history)
            self.current_history = None

        self.pot = 0
        self.hand_active = False

        return self._build_state(showdown=False)

    # ------------------------------------------------------------------
    # Rebuy
    # ------------------------------------------------------------------

    def rebuy(self, player_id: str) -> dict[str, Any]:
        """Allow a busted player to rebuy (if enabled)."""
        if not self.allow_rebuys:
            raise ValueError("Rebuys are not allowed")
        if self.hand_active:
            raise ValueError("Cannot rebuy during a hand")

        p = self._find_player(player_id)
        if p is None:
            raise ValueError("Player not found")
        if p.chips > 0:
            raise ValueError("Player still has chips")

        p.chips = self.starting_chips
        p.is_sitting_out = False
        return self._build_state()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_player_idx(self, player_id: str) -> Optional[int]:
        for i, p in enumerate(self.seats):
            if p.player_id == player_id:
                return i
        return None

    def _find_player(self, player_id: str) -> Optional[PlayerState]:
        idx = self._find_player_idx(player_id)
        return self.seats[idx] if idx is not None else None

    def _build_state(
        self,
        message: str = "",
        game_over: bool = False,
        showdown: bool = False,
    ) -> dict[str, Any]:
        """Build the full game state dict for broadcasting."""
        action_on_player_id = None
        if self.hand_active and self.action_on_idx is not None:
            p = self.seats[self.action_on_idx]
            if p.is_active:
                action_on_player_id = p.player_id

        return {
            "game_code": self.game_code,
            "hand_number": self.hand_number,
            "street": self.street.value,
            "pot": self.pot,
            "community_cards": [c.to_dict() for c in self.community_cards],
            "dealer_idx": self.dealer_idx,
            "dealer_player_id": self.seats[self.dealer_idx].player_id,
            "action_on": action_on_player_id,
            "current_bet": self.current_bet,
            "min_raise": self.min_raise,
            "hand_active": self.hand_active,
            "game_over": game_over,
            "message": message,
            "last_hand_result": self.last_hand_result,
            "players": [
                p.to_dict(reveal_cards=showdown) for p in self.seats
            ],
            # Showdown reveals all non-folded cards
            "showdown": showdown,
        }

    def get_player_view(self, player_id: str) -> dict[str, Any]:
        """Build a state view for a specific player (shows their own hole cards)."""
        state = self._build_state(
            showdown=(self.street == Street.SHOWDOWN),
        )

        # Add this player's hole cards
        player = self._find_player(player_id)
        if player and player.hole_cards:
            state["my_cards"] = [c.to_dict() for c in player.hole_cards]
        else:
            state["my_cards"] = []

        # Hide other players' cards (unless showdown)
        if self.street != Street.SHOWDOWN:
            for p_data in state["players"]:
                p_data.pop("hole_cards", None)

        # Add valid actions for this player
        state["valid_actions"] = self.get_valid_actions(player_id)

        return state

    # ------------------------------------------------------------------
    # Serialization (for Redis persistence)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize full engine state for Redis storage."""
        return {
            "game_code": self.game_code,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "allow_rebuys": self.allow_rebuys,
            "starting_chips": self.starting_chips,
            "dealer_idx": self.dealer_idx,
            "hand_number": self.hand_number,
            "street": self.street.value,
            "pot": self.pot,
            "current_bet": self.current_bet,
            "min_raise": self.min_raise,
            "hand_active": self.hand_active,
            "action_on_idx": self.action_on_idx,
            "last_raiser_idx": self.last_raiser_idx,
            "community_cards": [c.to_dict() for c in self.community_cards],
            "last_hand_result": self.last_hand_result,
            "seats": [
                {
                    "player_id": p.player_id,
                    "name": p.name,
                    "chips": p.chips,
                    "hole_cards": [c.to_dict() for c in p.hole_cards],
                    "bet_this_round": p.bet_this_round,
                    "bet_this_hand": p.bet_this_hand,
                    "folded": p.folded,
                    "all_in": p.all_in,
                    "has_acted": p.has_acted,
                    "is_sitting_out": p.is_sitting_out,
                }
                for p in self.seats
            ],
            "hand_histories": [h.to_dict() for h in self.hand_histories],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameEngine:
        """Restore engine state from Redis."""
        engine = cls.__new__(cls)
        engine.game_code = data["game_code"]
        engine.small_blind = data["small_blind"]
        engine.big_blind = data["big_blind"]
        engine.allow_rebuys = data["allow_rebuys"]
        engine.starting_chips = data["starting_chips"]
        engine.dealer_idx = data["dealer_idx"]
        engine.hand_number = data["hand_number"]
        engine.street = Street(data["street"])
        engine.pot = data["pot"]
        engine.current_bet = data["current_bet"]
        engine.min_raise = data["min_raise"]
        engine.hand_active = data["hand_active"]
        engine.action_on_idx = data["action_on_idx"]
        engine.last_raiser_idx = data["last_raiser_idx"]
        engine.community_cards = [Card.from_dict(c) for c in data["community_cards"]]
        engine.last_hand_result = data.get("last_hand_result")
        engine.deck = None  # Deck is not persisted (new one each hand)
        engine.current_history = None

        engine.seats = []
        for s in data["seats"]:
            ps = PlayerState(s["player_id"], s["name"], s["chips"])
            ps.hole_cards = [Card.from_dict(c) for c in s["hole_cards"]]
            ps.bet_this_round = s["bet_this_round"]
            ps.bet_this_hand = s["bet_this_hand"]
            ps.folded = s["folded"]
            ps.all_in = s["all_in"]
            ps.has_acted = s["has_acted"]
            ps.is_sitting_out = s["is_sitting_out"]
            engine.seats.append(ps)

        engine.hand_histories = []
        for h in data.get("hand_histories", []):
            hh = HandHistory(h["hand_number"])
            hh.actions = h["actions"]
            hh.community_cards = h["community_cards"]
            hh.winners = h["winners"]
            engine.hand_histories.append(hh)

        return engine
