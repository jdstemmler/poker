"""Core game engine for No-Limit Texas Hold'em.

Manages the authoritative game state: dealing, betting rounds,
pot management, showdown, dealer rotation, and hand lifecycle.
"""

from __future__ import annotations

import bisect
import time
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
        self.last_action: str = ""
        self.rebuy_count: int = 0
        self.rebuy_queued: bool = False

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
        self.last_action = ""
        self.rebuy_queued = False

    def reset_for_new_round(self) -> None:
        self.bet_this_round = 0
        self.has_acted = False
        # Keep last_action for folded/all-in players; clear for active ones
        if not self.folded and not self.all_in:
            self.last_action = ""

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
            "last_action": self.last_action,
            "rebuy_count": self.rebuy_count,
            "rebuy_queued": self.rebuy_queued,
        }
        if reveal_cards and self.hole_cards:
            d["hole_cards"] = [c.to_dict() for c in self.hole_cards]
        return d


def _round_blind(value: float) -> int:
    """Round a blind value to a clean number (legacy helper)."""
    v = int(round(value))
    if v >= 100:
        return round(v / 10) * 10  # round to nearest 10
    if v >= 10:
        return round(v / 5) * 5  # round to nearest 5
    return max(1, v)


# Standard tournament blind values: factors [1,1.5,2,2.5,3,4,5,6,8] × decade
_STANDARD_BLINDS: list[int] = sorted({
    round(f * d)
    for d in (1, 10, 100, 1_000, 10_000, 100_000)
    for f in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8)
})


def _nice_blind(value: float) -> int:
    """Snap a value to the nearest standard tournament blind amount."""
    if value <= 1:
        return 1
    v = round(value)
    idx = bisect.bisect_left(_STANDARD_BLINDS, v)
    if idx == 0:
        return _STANDARD_BLINDS[0]
    if idx >= len(_STANDARD_BLINDS):
        return _STANDARD_BLINDS[-1]
    lo = _STANDARD_BLINDS[idx - 1]
    hi = _STANDARD_BLINDS[idx]
    return lo if (value - lo) <= (hi - value) else hi


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

    # Default blind schedule: each entry is (small_blind, big_blind)
    DEFAULT_BLIND_SCHEDULE: list[tuple[int, int]] = [
        (10, 20),
        (15, 30),
        (20, 40),
        (30, 60),
        (50, 100),
        (75, 150),
        (100, 200),
        (150, 300),
        (200, 400),
        (300, 600),
        (500, 1000),
    ]

    def __init__(
        self,
        game_code: str,
        players: list[dict[str, Any]],
        starting_chips: int,
        small_blind: int = 0,
        big_blind: int = 0,
        allow_rebuys: bool = True,
        turn_timeout: int = 0,
        blind_level_duration: int = 0,
        blind_schedule: list[tuple[int, int]] | None = None,
        blind_multiplier: float = 2.0,
        max_rebuys: int = 1,
        rebuy_cutoff_minutes: int = 60,
        auto_deal_enabled: bool = True,
        target_game_time: int = 0,
    ) -> None:
        self.game_code = game_code
        self.allow_rebuys = allow_rebuys
        self.max_rebuys = max_rebuys  # 0 = unlimited
        self.rebuy_cutoff_minutes = rebuy_cutoff_minutes  # 0 = no cutoff
        self.starting_chips = starting_chips
        self.turn_timeout = turn_timeout  # 0 = no timer
        self.target_game_time: int = target_game_time  # hours, 0 = fixed blinds

        # Derive initial blinds from starting chips when using target schedule
        # or when no explicit blinds are provided
        if target_game_time > 0 or big_blind <= 0:
            self.big_blind = max(2, _nice_blind(starting_chips / 100))
            self.small_blind = max(1, self.big_blind // 2)
        else:
            self.big_blind = big_blind
            self.small_blind = small_blind if small_blind > 0 else big_blind // 2

        # Blind level scheduling
        self.blind_level_duration: int = blind_level_duration  # minutes, 0 = disabled
        self.blind_multiplier: float = blind_multiplier  # kept for serialisation compat
        if blind_schedule is not None:
            self.blind_schedule: list[tuple[int, int]] = blind_schedule
        elif blind_level_duration > 0 and target_game_time > 0:
            # New: build schedule targeting a total game time
            self.blind_schedule = self._build_schedule_for_target(
                starting_chips, blind_level_duration, target_game_time,
            )
        elif blind_level_duration > 0:
            # Legacy fallback: multiplicative/additive schedule
            self.blind_schedule = self._build_schedule_from(
                self.small_blind, self.big_blind, multiplier=blind_multiplier
            )
        else:
            self.blind_schedule = []
        self.blind_level: int = 0  # current index into blind_schedule

        # Seat players in order
        self.seats: list[PlayerState] = []
        for p in players:
            ps = PlayerState(p["id"], p["name"], starting_chips)
            self.seats.append(ps)

        # Dealer button position (index into self.seats)
        self.dealer_idx: int = 0
        self.hand_number: int = 0

        # When the game started (Unix timestamp, set on first hand)
        self.game_started_at: Optional[float] = None

        # Current hand state
        self.deck: Optional[Deck] = None
        self.community_cards: list[Card] = []
        self.street: Street = Street.PREFLOP
        self.pot: int = 0
        self.current_bet: int = 0
        self.action_on_idx: int = 0
        self.min_raise: int = self.big_blind
        self.hand_active: bool = False
        self.last_raiser_idx: Optional[int] = None
        self.action_deadline: Optional[float] = None  # Unix timestamp when turn expires
        self.auto_deal_deadline: Optional[float] = None  # Unix timestamp for auto-deal

        # Auto-deal delay in seconds (0 = disabled)
        self.auto_deal_delay: int = 10 if auto_deal_enabled else 0

        # History
        self.hand_histories: list[HandHistory] = []
        self.current_history: Optional[HandHistory] = None

        # Results of the last completed hand (for UI display)
        self.last_hand_result: Optional[dict[str, Any]] = None

        # Players who chose to reveal their cards post-hand
        self.shown_cards: set[str] = set()

        # Pause support
        self.paused: bool = False
        self.paused_at: Optional[float] = None  # timestamp when paused
        self.total_paused_seconds: float = 0  # accumulated pause time

        # Game over flag (persisted so broadcasts include it)
        self.game_over: bool = False
        self.game_over_message: str = ""

        # Player elimination tracking: list of {player_id, name, eliminated_hand}
        # Recorded in order of elimination (first entry = first player out)
        self.elimination_order: list[dict[str, Any]] = []
        self.final_standings: list[dict[str, Any]] = []

    @classmethod
    def _build_schedule_from(
        cls, start_sb: int, start_bb: int, multiplier: float = 2.0,
    ) -> list[tuple[int, int]]:
        """Build a blind schedule starting from the given initial blinds.

        Generates 10 levels.  When *multiplier* is 0 the schedule grows by
        a fixed additive increment equal to the initial blinds each level
        (e.g. 10/20 → 20/40 → 30/60 …).  Otherwise the blinds are
        multiplied by *multiplier* each level (e.g. 2.0 doubles).

        Values are rounded to the nearest 5 or 10 for clean numbers.
        """
        schedule: list[tuple[int, int]] = [(start_sb, start_bb)]
        sb, bb = float(start_sb), float(start_bb)
        additive = multiplier == 0
        for _ in range(10):
            if additive:
                sb += start_sb
                bb += start_bb
            else:
                sb *= multiplier
                bb *= multiplier
            sb_int = _round_blind(sb)
            bb_int = _round_blind(bb)
            schedule.append((sb_int, bb_int))
        return schedule

    @classmethod
    def _build_schedule_for_target(
        cls,
        starting_chips: int,
        level_duration_minutes: int,
        target_game_time_hours: int,
    ) -> list[tuple[int, int]]:
        """Build a blind schedule using linear-then-geometric growth.

        Phase 1 (~first half of levels): blinds increase linearly,
        adding the initial BB each level (e.g. 50→100→150→…).
        Phase 2 (remaining levels): geometric growth to reach
        starting_chips as BB by the target time.
        Phase 3 (overtime): continue at ~1.5× per level until BB ≥ 3× chips.

        All values are snapped to standard tournament blind amounts.
        """
        bb_initial = max(2, _nice_blind(starting_chips / 100))

        total_minutes = target_game_time_hours * 60
        n_levels = max(3, total_minutes // level_duration_minutes)

        # Phase 1: linear growth (~half of scheduled levels)
        phase1_count = max(2, round(n_levels * 0.5))
        phase2_count = (n_levels + 2) - phase1_count  # +2 buffer beyond target

        schedule_bb: list[int] = []

        # Phase 1: add bb_initial each level
        for i in range(phase1_count):
            schedule_bb.append(_nice_blind(bb_initial * (i + 1)))

        # Phase 2: geometric from last phase-1 value toward starting_chips
        last_bb = schedule_bb[-1]
        bb_target = starting_chips

        if phase2_count > 0 and last_bb < bb_target:
            ratio = (bb_target / last_bb) ** (1.0 / max(1, phase2_count - 1))
            ratio = max(ratio, 1.2)  # at least 20 % growth per level
            for i in range(1, phase2_count + 1):
                raw = last_bb * (ratio ** i)
                schedule_bb.append(_nice_blind(raw))

        # Phase 3 (overtime): continue at 1.5× until BB ≥ 3× starting chips
        overtime_cap = starting_chips * 3
        while schedule_bb[-1] < overtime_cap:
            nxt = _nice_blind(schedule_bb[-1] * 1.5)
            if nxt <= schedule_bb[-1]:
                nxt = schedule_bb[-1] + 1  # safety: guarantee forward progress
            schedule_bb.append(nxt)

        # Build (SB, BB) tuples — SB is always BB // 2
        schedule: list[tuple[int, int]] = []
        for bb in schedule_bb:
            sb = max(1, bb // 2)
            schedule.append((sb, bb))

        # Deduplicate consecutive identical levels
        deduped: list[tuple[int, int]] = [schedule[0]]
        for level in schedule[1:]:
            if level != deduped[-1]:
                deduped.append(level)

        return deduped

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
            if only_active and (not p.is_active or p.folded):
                continue
            return i
        return idx  # shouldn't happen

    def _set_action_deadline(self) -> None:
        """Set the action deadline for the current player based on turn_timeout."""
        if self.turn_timeout > 0 and self.hand_active:
            self.action_deadline = time.time() + self.turn_timeout
        else:
            self.action_deadline = None

    def _set_auto_deal_deadline(self) -> None:
        """Set the auto-deal deadline after a hand ends."""
        if self.auto_deal_delay > 0 and not self.hand_active and not self.paused:
            self.auto_deal_deadline = time.time() + self.auto_deal_delay
        else:
            self.auto_deal_deadline = None

    def _effective_elapsed(self) -> float:
        """Return elapsed game seconds excluding paused time."""
        if self.game_started_at is None:
            return 0
        now = self.paused_at if self.paused and self.paused_at else time.time()
        return (now - self.game_started_at) - self.total_paused_seconds

    def _maybe_advance_blind_level(self) -> None:
        """Check elapsed time and advance the blind level if needed.

        If the clock has passed the last pre-built level, dynamically
        extend the schedule at ~1.5× per level so blinds never stall.
        """
        if (
            self.blind_level_duration <= 0
            or not self.blind_schedule
            or self.game_started_at is None
        ):
            return

        elapsed_minutes = self._effective_elapsed() / 60.0
        target_level = int(elapsed_minutes // self.blind_level_duration)

        # Dynamically extend the schedule if we've exceeded it
        while target_level >= len(self.blind_schedule):
            last_sb, last_bb = self.blind_schedule[-1]
            new_bb = _nice_blind(last_bb * 1.5)
            if new_bb <= last_bb:
                new_bb = last_bb + 1  # guarantee forward progress
            new_sb = max(1, new_bb // 2)
            self.blind_schedule.append((new_sb, new_bb))

        if target_level > self.blind_level:
            self.blind_level = target_level
            sb, bb = self.blind_schedule[self.blind_level]
            self.small_blind = sb
            self.big_blind = bb

    def get_next_blind_change_at(self) -> Optional[float]:
        """Return the Unix timestamp when the next blind level will start, or None."""
        if (
            self.blind_level_duration <= 0
            or not self.blind_schedule
            or self.game_started_at is None
        ):
            return None
        if self.paused:
            return None  # don't show countdown while paused
        next_level = self.blind_level + 1
        return self.game_started_at + self.total_paused_seconds + (next_level * self.blind_level_duration * 60)

    # ------------------------------------------------------------------
    # Hand Lifecycle
    # ------------------------------------------------------------------

    def start_new_hand(self) -> dict[str, Any]:
        """Deal a new hand. Returns game state snapshot."""
        # If game is already over (detected at end of previous hand), return immediately
        if self.game_over:
            return self._build_state()

        # Process queued rebuys first
        for p in self.seats:
            if p.rebuy_queued:
                p.chips = self.starting_chips
                p.is_sitting_out = False
                p.rebuy_count += 1
                p.rebuy_queued = False
                # Remove from elimination order — they're back in the game
                self.elimination_order = [
                    e for e in self.elimination_order
                    if e["player_id"] != p.player_id
                ]

        # Record any remaining busted players in elimination order
        eliminated_ids = {e["player_id"] for e in self.elimination_order}
        for p in self.seats:
            if p.chips <= 0 and not p.rebuy_queued:
                if p.player_id not in eliminated_ids:
                    self.elimination_order.append({
                        "player_id": p.player_id,
                        "name": p.name,
                        "eliminated_hand": self.hand_number,
                    })
                p.is_sitting_out = True

        live_players = [i for i, p in enumerate(self.seats) if not p.is_sitting_out]
        if len(live_players) < 2:
            self.game_over = True
            self.final_standings = self._build_final_standings()
            winner_name = self.final_standings[0]["name"] if self.final_standings else "Unknown"
            self.game_over_message = f"{winner_name} wins the game!"
            return self._build_state()

        self.hand_number += 1
        self.last_hand_result = None

        # Set game start time on first hand
        if self.game_started_at is None:
            self.game_started_at = time.time()

        # Check if blinds should increase
        self._maybe_advance_blind_level()

        # Clear auto-deal deadline
        self.auto_deal_deadline = None

        # Reset shown cards for new hand
        self.shown_cards = set()

        # Rotate dealer
        if self.hand_number > 1:
            self.dealer_idx = self._next_seat(self.dealer_idx)

        # Reset per-hand state
        for p in self.seats:
            if not p.is_sitting_out:
                p.reset_for_new_hand()
            else:
                # Clear stale status from previous hand for sitting-out players
                p.folded = False
                p.all_in = False
                p.has_acted = False
                p.last_action = ""
                p.bet_this_round = 0
                p.bet_this_hand = 0
                p.hole_cards = []

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

        self._force_bet(sb_idx, self.small_blind, "SB")
        self._force_bet(bb_idx, self.big_blind, "BB")

        self.current_bet = self.big_blind
        self.min_raise = self.big_blind  # min raise size = one big blind

        # Action starts after big blind
        self.action_on_idx = self._next_seat(bb_idx)
        self._set_action_deadline()

        # In preflop, the big blind acts last (gets option to raise)
        self.last_raiser_idx = bb_idx

    def _force_bet(self, idx: int, amount: int, label: str = "") -> int:
        """Force a player to bet (blinds/antes). Returns actual amount posted."""
        p = self.seats[idx]
        actual = min(amount, p.chips)
        p.chips -= actual
        p.bet_this_round += actual
        p.bet_this_hand += actual
        self.pot += actual
        if label:
            p.last_action = f"{label} {actual}"
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

        # Fold is always available
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
                # Can't meet min raise — only all-in is possible as a raise
                actions.append(
                    {
                        "action": "raise",
                        "min_amount": p.chips,
                        "max_amount": p.chips,
                    }
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
        self._set_action_deadline()
        return self._build_state()

    def _do_fold(self, idx: int) -> None:
        p = self.seats[idx]
        p.folded = True
        p.has_acted = True
        p.last_action = "Fold"
        if self.current_history:
            self.current_history.record_action(
                p.player_id, PlayerAction.FOLD, 0, self.street
            )

    def _do_check(self, idx: int) -> None:
        p = self.seats[idx]
        p.has_acted = True
        p.last_action = "Check"
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
        p.last_action = f"Call {actual}"
        if p.chips == 0:
            p.all_in = True
            p.last_action = f"All-In {actual}"
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
        p.last_action = f"Raise {actual}"

        if p.chips == 0:
            p.all_in = True
            p.last_action = f"All-In {p.bet_this_hand}"

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
        p.last_action = f"All-In {p.bet_this_hand}"

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

        self._set_action_deadline()
        return self._build_state()

    # ------------------------------------------------------------------
    # Showdown & Pot Award
    # ------------------------------------------------------------------

    def _calculate_pots(self) -> list[tuple[int, list[int]]]:
        """Build main pot and side pots based on bet_this_hand contributions.

        Returns a list of (pot_amount, [eligible_player_indices]).
        Each pot is the portion that the eligible players contributed equally to.
        """
        in_hand = self._players_in_hand()

        # Gather unique contribution levels from non-folded players
        contribution_levels: list[int] = sorted(
            set(self.seats[i].bet_this_hand for i in in_hand)
        )

        # Also include folded players' contributions in the pool
        # (they contributed but can't win)
        all_contributions = {
            i: self.seats[i].bet_this_hand
            for i in range(len(self.seats))
            if not self.seats[i].is_sitting_out and self.seats[i].bet_this_hand > 0
        }

        pots: list[tuple[int, list[int]]] = []
        prev_level = 0

        for level in contribution_levels:
            slice_amount = level - prev_level
            if slice_amount <= 0:
                continue

            # Everyone who contributed at least this level pays into this pot
            pot_total = 0
            for idx, contrib in all_contributions.items():
                take = min(slice_amount, contrib - prev_level)
                if take > 0:
                    pot_total += take

            # Only non-folded players who contributed at least this level are eligible
            eligible = [
                i for i in in_hand if self.seats[i].bet_this_hand >= level
            ]

            if pot_total > 0 and eligible:
                pots.append((pot_total, eligible))

            prev_level = level

        return pots

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

        # Calculate side pots and award each one
        pots = self._calculate_pots()
        winnings_by_pid: dict[str, int] = {}
        refunds_by_pid: dict[str, int] = {}
        best_hand_by_pid: dict[str, str] = {}

        for pot_amount, eligible_indices in pots:
            # Build hands map for only eligible players
            eligible_hands = {
                self.seats[i].player_id: player_hands[self.seats[i].player_id]
                for i in eligible_indices
                if self.seats[i].player_id in player_hands
            }

            # Single eligible player = uncalled bet refund, not a "win"
            if len(eligible_hands) == 1:
                pid = next(iter(eligible_hands))
                player = self._find_player(pid)
                if player:
                    player.chips += pot_amount
                    refunds_by_pid[pid] = refunds_by_pid.get(pid, 0) + pot_amount
                continue

            pot_winner_ids = determine_winners(eligible_hands)
            if not pot_winner_ids:
                continue

            share = pot_amount // len(pot_winner_ids)
            remainder = pot_amount - (share * len(pot_winner_ids))

            for j, pid in enumerate(pot_winner_ids):
                w = share + (1 if j < remainder else 0)
                player = self._find_player(pid)
                if player:
                    player.chips += w
                    winnings_by_pid[pid] = winnings_by_pid.get(pid, 0) + w
                    if pid in player_hands:
                        best_hand_by_pid[pid] = player_hands[pid].name

        result_winners = [
            {
                "player_id": pid,
                "name": self._find_player(pid).name,
                "winnings": total,
                "hand": best_hand_by_pid.get(pid, "Unknown"),
            }
            for pid, total in winnings_by_pid.items()
        ]

        result_refunds = [
            {
                "player_id": pid,
                "name": self._find_player(pid).name,
                "amount": total,
            }
            for pid, total in refunds_by_pid.items()
        ]

        self.last_hand_result = {
            "winners": result_winners,
            "refunds": result_refunds,
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
        self.action_deadline = None

        # Check for game over immediately after hand ends
        if self._check_game_over():
            return self._build_state(showdown=True)

        self._set_auto_deal_deadline()

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
        self.action_deadline = None

        # Check for game over immediately after hand ends
        if self._check_game_over():
            return self._build_state(showdown=False)

        self._set_auto_deal_deadline()

        return self._build_state(showdown=False)

    # ------------------------------------------------------------------
    # Rebuy
    # ------------------------------------------------------------------

    def _check_game_over(self) -> bool:
        """Check if the game is over after a hand ends.

        Records eliminations and triggers game_over if < 2 players can continue.
        Returns True if game is now over.
        """
        # Record all newly busted players in elimination order immediately.
        # They can still rebuy (which removes them from the list).
        eliminated_ids = {e["player_id"] for e in self.elimination_order}
        for p in self.seats:
            if (
                p.chips <= 0
                and not p.rebuy_queued
                and p.player_id not in eliminated_ids
            ):
                self.elimination_order.append({
                    "player_id": p.player_id,
                    "name": p.name,
                    "eliminated_hand": self.hand_number,
                })
                p.is_sitting_out = True

        # Count players who can still play
        live_players = [p for p in self.seats if not p.is_sitting_out]
        if len(live_players) < 2:
            self.game_over = True
            self.final_standings = self._build_final_standings()
            winner_name = self.final_standings[0]["name"] if self.final_standings else "Unknown"
            self.game_over_message = f"{winner_name} wins the game!"
            self.auto_deal_deadline = None
            return True
        return False

    def _build_final_standings(self) -> list[dict[str, Any]]:
        """Build final standings: winner first, then by elimination order (last out = 2nd place)."""
        standings: list[dict[str, Any]] = []

        # Winner is the last player standing (not in elimination order)
        eliminated_ids = {e["player_id"] for e in self.elimination_order}
        live = [p for p in self.seats if p.player_id not in eliminated_ids]
        for p in live:
            standings.append({
                "player_id": p.player_id,
                "name": p.name,
                "chips": p.chips,
                "place": 1,
            })

        # Eliminated players in reverse order (last eliminated = 2nd place)
        place = len(standings) + 1
        for entry in reversed(self.elimination_order):
            p = self._find_player(entry["player_id"])
            standings.append({
                "player_id": entry["player_id"],
                "name": entry["name"],
                "chips": p.chips if p else 0,
                "place": place,
                "eliminated_hand": entry["eliminated_hand"],
            })
            place += 1

        return standings

    def _can_rebuy(self, p: PlayerState) -> bool:
        """Check if a busted player is eligible to rebuy (ignoring hand_active)."""
        if not self.allow_rebuys:
            return False
        if p.chips > 0:
            return False
        # Disable rebuys when it would result in heads-up or fewer.
        # Since busted players are now immediately in elimination_order,
        # count how many players would be in the game if this player rebuys.
        eliminated_ids = {e["player_id"] for e in self.elimination_order}
        in_game_count = sum(1 for s in self.seats if s.player_id not in eliminated_ids)
        # If this player is in elimination_order, rebuying would add them back
        would_be_in_game = in_game_count + (1 if p.player_id in eliminated_ids else 0)
        if would_be_in_game <= 2:
            return False
        if self.max_rebuys > 0 and p.rebuy_count >= self.max_rebuys:
            return False
        if (
            self.rebuy_cutoff_minutes > 0
            and self.game_started_at is not None
        ):
            elapsed = self._effective_elapsed() / 60.0
            if elapsed >= self.rebuy_cutoff_minutes:
                return False
        return True

    def rebuy(self, player_id: str) -> dict[str, Any]:
        """Allow a busted player to rebuy (if enabled).

        If the hand is currently active, the rebuy is queued and will be
        processed automatically at the start of the next hand.
        """
        if not self.allow_rebuys:
            raise ValueError("Rebuys are not allowed")

        p = self._find_player(player_id)
        if p is None:
            raise ValueError("Player not found")
        if p.chips > 0:
            raise ValueError("Player still has chips")

        # Enforce rebuy limit (0 = unlimited)
        if self.max_rebuys > 0 and p.rebuy_count >= self.max_rebuys:
            raise ValueError(
                f"Maximum rebuys ({self.max_rebuys}) reached"
            )

        # Enforce cutoff time (0 = no cutoff)
        if (
            self.rebuy_cutoff_minutes > 0
            and self.game_started_at is not None
        ):
            elapsed = self._effective_elapsed() / 60.0
            if elapsed >= self.rebuy_cutoff_minutes:
                raise ValueError(
                    f"Rebuy window has closed ({self.rebuy_cutoff_minutes} min)"
                )

        if self.hand_active:
            # Queue the rebuy — it will be processed when the next hand starts
            if p.rebuy_queued:
                raise ValueError("Rebuy already queued")
            p.rebuy_queued = True
            return self._build_state()

        p.chips = self.starting_chips
        p.is_sitting_out = False
        p.rebuy_count += 1
        # Remove from elimination order — they're back in the game
        self.elimination_order = [
            e for e in self.elimination_order
            if e["player_id"] != p.player_id
        ]
        return self._build_state()

    def cancel_rebuy(self, player_id: str) -> dict[str, Any]:
        """Cancel a queued rebuy."""
        p = self._find_player(player_id)
        if p is None:
            raise ValueError("Player not found")
        if not p.rebuy_queued:
            raise ValueError("No rebuy queued")
        p.rebuy_queued = False
        return self._build_state()

    def show_cards(self, player_id: str) -> dict[str, Any]:
        """Allow a player to voluntarily reveal their cards after a hand."""
        if self.hand_active:
            raise ValueError("Hand is still active")

        p = self._find_player(player_id)
        if p is None:
            raise ValueError("Player not found")
        if not p.hole_cards:
            raise ValueError("No cards to show")

        self.shown_cards.add(player_id)
        return self._build_state(showdown=True)

    def pause(self) -> dict[str, Any]:
        """Pause the game. Stops timers."""
        if self.paused:
            raise ValueError("Game is already paused")
        if self.hand_active:
            raise ValueError("Cannot pause during an active hand")
        self.paused = True
        self.paused_at = time.time()
        self.auto_deal_deadline = None
        return self._build_state()

    def unpause(self) -> dict[str, Any]:
        """Unpause the game. Resumes timers."""
        if not self.paused:
            raise ValueError("Game is not paused")
        if self.paused_at:
            self.total_paused_seconds += time.time() - self.paused_at
        self.paused = False
        self.paused_at = None
        self._set_auto_deal_deadline()
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
        game_over: bool | None = None,
        showdown: bool = False,
    ) -> dict[str, Any]:
        """Build the full game state dict for broadcasting."""
        # Use persisted game_over flag if not explicitly overridden
        if game_over is None:
            game_over = self.game_over
        if not message and self.game_over:
            message = self.game_over_message

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
            "final_standings": self.final_standings if game_over else [],
            "last_hand_result": self.last_hand_result,
            "players": [
                {**p.to_dict(reveal_cards=showdown or p.player_id in self.shown_cards),
                 "can_rebuy": self._can_rebuy(p)}
                for p in self.seats
            ],
            # Showdown reveals all non-folded cards
            "showdown": showdown,
            "turn_timeout": self.turn_timeout,
            "action_deadline": self.action_deadline,
            "auto_deal_deadline": self.auto_deal_deadline,
            "game_started_at": self.game_started_at,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "blind_level": self.blind_level,
            "blind_level_duration": self.blind_level_duration,
            "blind_schedule": [[sb, bb] for sb, bb in self.blind_schedule] if self.blind_schedule else [],
            "next_blind_change_at": self.get_next_blind_change_at(),
            "allow_rebuys": self.allow_rebuys,
            "max_rebuys": self.max_rebuys,
            "rebuy_cutoff_minutes": self.rebuy_cutoff_minutes,
            "paused": self.paused,
            "total_paused_seconds": self.total_paused_seconds,
        }

    def get_player_view(self, player_id: str) -> dict[str, Any]:
        """Build a state view for a specific player (shows their own hole cards)."""
        is_showdown = self.street == Street.SHOWDOWN
        state = self._build_state(showdown=is_showdown)

        # Add this player's hole cards
        player = self._find_player(player_id)
        if player and player.hole_cards:
            state["my_cards"] = [c.to_dict() for c in player.hole_cards]
        else:
            state["my_cards"] = []

        # Control card visibility per player
        for p_data in state["players"]:
            pid = p_data["player_id"]
            if pid == player_id:
                # Always strip own cards from the player list (shown via my_cards)
                p_data.pop("hole_cards", None)
            elif pid in self.shown_cards:
                # Player chose to show (or auto-revealed as winner) — keep cards
                pass
            else:
                # Hide cards
                p_data.pop("hole_cards", None)

        # Include which players have shown their cards
        state["shown_cards"] = list(self.shown_cards)

        # Filter last_hand_result.player_hands so only shown players' cards are visible
        if state.get("last_hand_result") and "player_hands" in state["last_hand_result"]:
            filtered_hands = {}
            for pid, hand_data in state["last_hand_result"]["player_hands"].items():
                if pid == player_id or pid in self.shown_cards:
                    filtered_hands[pid] = hand_data
                else:
                    # Include hand name but strip cards
                    filtered_hands[pid] = {
                        "cards": [],
                        "hand_name": hand_data.get("hand_name"),
                    }
            state["last_hand_result"] = {**state["last_hand_result"], "player_hands": filtered_hands}

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
            "max_rebuys": self.max_rebuys,
            "rebuy_cutoff_minutes": self.rebuy_cutoff_minutes,
            "starting_chips": self.starting_chips,
            "turn_timeout": self.turn_timeout,
            "dealer_idx": self.dealer_idx,
            "hand_number": self.hand_number,
            "street": self.street.value,
            "pot": self.pot,
            "current_bet": self.current_bet,
            "min_raise": self.min_raise,
            "hand_active": self.hand_active,
            "action_on_idx": self.action_on_idx,
            "last_raiser_idx": self.last_raiser_idx,
            "action_deadline": self.action_deadline,
            "auto_deal_deadline": self.auto_deal_deadline,
            "auto_deal_delay": self.auto_deal_delay,
            "game_started_at": self.game_started_at,
            "blind_level_duration": self.blind_level_duration,
            "blind_multiplier": self.blind_multiplier,
            "blind_schedule": [[sb, bb] for sb, bb in self.blind_schedule],
            "blind_level": self.blind_level,
            "target_game_time": self.target_game_time,
            "community_cards": [c.to_dict() for c in self.community_cards],
            "deck": self.deck.to_dict() if self.deck else None,
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
                    "last_action": p.last_action,
                    "rebuy_count": p.rebuy_count,
                    "rebuy_queued": p.rebuy_queued,
                }
                for p in self.seats
            ],
            "hand_histories": [h.to_dict() for h in self.hand_histories],
            "shown_cards": list(self.shown_cards),
            "paused": self.paused,
            "paused_at": self.paused_at,
            "total_paused_seconds": self.total_paused_seconds,
            "game_over": self.game_over,
            "game_over_message": self.game_over_message,
            "elimination_order": self.elimination_order,
            "final_standings": self.final_standings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameEngine:
        """Restore engine state from Redis."""
        engine = cls.__new__(cls)
        engine.game_code = data["game_code"]
        engine.small_blind = data["small_blind"]
        engine.big_blind = data["big_blind"]
        engine.allow_rebuys = data["allow_rebuys"]
        engine.max_rebuys = data.get("max_rebuys", 1)
        engine.rebuy_cutoff_minutes = data.get("rebuy_cutoff_minutes", 60)
        engine.starting_chips = data["starting_chips"]
        engine.turn_timeout = data.get("turn_timeout", 0)
        engine.dealer_idx = data["dealer_idx"]
        engine.hand_number = data["hand_number"]
        engine.street = Street(data["street"])
        engine.pot = data["pot"]
        engine.current_bet = data["current_bet"]
        engine.min_raise = data["min_raise"]
        engine.hand_active = data["hand_active"]
        engine.action_on_idx = data["action_on_idx"]
        engine.last_raiser_idx = data["last_raiser_idx"]
        engine.action_deadline = data.get("action_deadline")
        engine.auto_deal_deadline = data.get("auto_deal_deadline")
        engine.auto_deal_delay = data.get("auto_deal_delay", 10)
        engine.game_started_at = data.get("game_started_at")
        engine.blind_level_duration = data.get("blind_level_duration", 0)
        engine.blind_multiplier = data.get("blind_multiplier", 2.0)
        engine.target_game_time = data.get("target_game_time", 0)
        raw_schedule = data.get("blind_schedule", [])
        engine.blind_schedule = [(s[0], s[1]) for s in raw_schedule]
        engine.blind_level = data.get("blind_level", 0)
        engine.community_cards = [Card.from_dict(c) for c in data["community_cards"]]
        engine.last_hand_result = data.get("last_hand_result")
        deck_data = data.get("deck")
        engine.deck = Deck.from_dict(deck_data) if deck_data else None
        engine.current_history = None
        engine.shown_cards = set(data.get("shown_cards", []))
        engine.paused = data.get("paused", False)
        engine.paused_at = data.get("paused_at")
        engine.total_paused_seconds = data.get("total_paused_seconds", 0)
        engine.game_over = data.get("game_over", False)
        engine.game_over_message = data.get("game_over_message", "")
        engine.elimination_order = data.get("elimination_order", [])
        engine.final_standings = data.get("final_standings", [])

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
            ps.last_action = s.get("last_action", "")
            ps.rebuy_count = s.get("rebuy_count", 0)
            ps.rebuy_queued = s.get("rebuy_queued", False)
            engine.seats.append(ps)

        engine.hand_histories = []
        for h in data.get("hand_histories", []):
            hh = HandHistory(h["hand_number"])
            hh.actions = h["actions"]
            hh.community_cards = h["community_cards"]
            hh.winners = h["winners"]
            engine.hand_histories.append(hh)

        return engine
