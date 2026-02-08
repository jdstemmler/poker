"""Tests for the GameEngine — hand lifecycle, dealing, blinds, dealer rotation."""

import time
import pytest
from unittest.mock import patch

from app.cards import Card, Deck, Rank, Suit
from app.engine import GameEngine, PlayerState, Street, HandHistory


# ── Helpers ──────────────────────────────────────────────────────────

def _make_engine(
    n_players: int = 3,
    starting_chips: int = 1000,
    small_blind: int = 10,
    big_blind: int = 20,
    **kwargs,
) -> GameEngine:
    """Create a GameEngine with n_players seated."""
    players = [
        {"id": f"p{i}", "name": f"Player{i}"}
        for i in range(n_players)
    ]
    return GameEngine(
        game_code="TEST01",
        players=players,
        starting_chips=starting_chips,
        small_blind=small_blind,
        big_blind=big_blind,
        **kwargs,
    )


def _deal_and_get(engine: GameEngine) -> dict:
    """Start a new hand and return the state dict."""
    return engine.start_new_hand()


# ── PlayerState ──────────────────────────────────────────────────────

class TestPlayerState:
    def test_initial_state(self):
        ps = PlayerState("id1", "Alice", 500)
        assert ps.player_id == "id1"
        assert ps.name == "Alice"
        assert ps.chips == 500
        assert ps.is_active
        assert not ps.folded
        assert not ps.all_in
        assert ps.last_action == ""

    def test_reset_for_new_hand(self):
        ps = PlayerState("id1", "Alice", 500)
        ps.folded = True
        ps.all_in = True
        ps.last_action = "Fold"
        ps.bet_this_round = 50
        ps.bet_this_hand = 100
        ps.has_acted = True
        ps.reset_for_new_hand()
        assert not ps.folded
        assert not ps.all_in
        assert ps.last_action == ""
        assert ps.bet_this_round == 0
        assert ps.bet_this_hand == 0
        assert not ps.has_acted

    def test_reset_for_new_round_clears_active_player(self):
        ps = PlayerState("id1", "Alice", 500)
        ps.last_action = "Check"
        ps.bet_this_round = 20
        ps.has_acted = True
        ps.reset_for_new_round()
        assert ps.bet_this_round == 0
        assert not ps.has_acted
        assert ps.last_action == ""  # cleared for active player

    def test_reset_for_new_round_keeps_folded_action(self):
        ps = PlayerState("id1", "Alice", 500)
        ps.folded = True
        ps.last_action = "Fold"
        ps.reset_for_new_round()
        assert ps.last_action == "Fold"

    def test_reset_for_new_round_keeps_allin_action(self):
        ps = PlayerState("id1", "Alice", 0)
        ps.all_in = True
        ps.last_action = "All-In 500"
        ps.reset_for_new_round()
        assert ps.last_action == "All-In 500"

    def test_is_active_false_when_folded(self):
        ps = PlayerState("id1", "Alice", 500)
        ps.folded = True
        assert not ps.is_active

    def test_is_active_false_when_all_in(self):
        ps = PlayerState("id1", "Alice", 0)
        ps.all_in = True
        assert not ps.is_active

    def test_to_dict_no_cards(self):
        ps = PlayerState("id1", "Alice", 500)
        d = ps.to_dict()
        assert d["player_id"] == "id1"
        assert d["chips"] == 500
        assert "hole_cards" not in d

    def test_to_dict_with_cards(self):
        ps = PlayerState("id1", "Alice", 500)
        ps.hole_cards = [Card(Rank.ACE, Suit.SPADES), Card(Rank.KING, Suit.HEARTS)]
        d = ps.to_dict(reveal_cards=True)
        assert "hole_cards" in d
        assert len(d["hole_cards"]) == 2


# ── Engine creation ──────────────────────────────────────────────────

class TestEngineCreation:
    def test_basic_setup(self):
        e = _make_engine(3)
        assert e.game_code == "TEST01"
        assert len(e.seats) == 3
        assert e.hand_number == 0
        assert not e.hand_active

    def test_player_starting_chips(self):
        e = _make_engine(4, starting_chips=500)
        for p in e.seats:
            assert p.chips == 500

    def test_blind_values(self):
        e = _make_engine(3, small_blind=5, big_blind=10)
        assert e.small_blind == 5
        assert e.big_blind == 10


# ── Dealing ──────────────────────────────────────────────────────────

class TestDealing:
    def test_deal_sets_hand_active(self):
        e = _make_engine(3)
        _deal_and_get(e)
        assert e.hand_active
        assert e.hand_number == 1

    def test_deal_gives_each_player_two_cards(self):
        e = _make_engine(4)
        _deal_and_get(e)
        for p in e.seats:
            assert len(p.hole_cards) == 2

    def test_deal_posts_blinds(self):
        e = _make_engine(3, small_blind=10, big_blind=20)
        _deal_and_get(e)
        # With 3 players: dealer=0, SB=1, BB=2
        assert e.pot == 30  # 10 + 20

    def test_deal_rotates_dealer(self):
        e = _make_engine(3)
        _deal_and_get(e)
        assert e.dealer_idx == 0
        # Complete the hand (everyone folds)
        action_player = e.seats[e.action_on_idx].player_id
        e.process_action(action_player, "fold")
        remaining = [p for p in e.seats if not p.folded and not p.is_sitting_out]
        if len(remaining) > 1:
            next_player = e.seats[e.action_on_idx].player_id
            e.process_action(next_player, "fold")
        # Deal second hand — dealer rotates using _next_seat which skips
        # folded players from the previous hand (not yet reset).
        _deal_and_get(e)
        assert e.dealer_idx != 0  # dealer has rotated

    def test_deal_resets_community_cards(self):
        e = _make_engine(2)
        _deal_and_get(e)
        assert e.community_cards == []

    def test_deal_creates_fresh_deck(self):
        e = _make_engine(2)
        _deal_and_get(e)
        assert e.deck is not None
        # 52 - 4 (2 players * 2 cards) = 48
        assert e.deck.remaining == 48

    def test_game_started_at_set_on_first_hand(self):
        e = _make_engine(2)
        assert e.game_started_at is None
        _deal_and_get(e)
        assert e.game_started_at is not None

    def test_insufficient_players(self):
        e = _make_engine(2)
        # Sit one player out
        e.seats[0].is_sitting_out = True
        state = _deal_and_get(e)
        assert state["game_over"] is True
        assert "Not enough" in state["message"]


# ── Heads-up dealing ─────────────────────────────────────────────────

class TestHeadsUpDealing:
    def test_heads_up_dealer_posts_small_blind(self):
        e = _make_engine(2, small_blind=5, big_blind=10)
        _deal_and_get(e)
        # Heads-up: dealer posts SB
        dealer = e.seats[e.dealer_idx]
        assert dealer.bet_this_round == 5

    def test_heads_up_action_starts_with_dealer(self):
        """In heads-up preflop, dealer (SB) acts first."""
        e = _make_engine(2, small_blind=5, big_blind=10)
        _deal_and_get(e)
        # Action should be on the dealer (SB position in heads-up)
        assert e.action_on_idx == e.dealer_idx


# ── State output ─────────────────────────────────────────────────────

class TestBuildState:
    def test_state_has_required_keys(self):
        e = _make_engine(3)
        state = _deal_and_get(e)
        required_keys = [
            "game_code", "hand_number", "street", "pot",
            "community_cards", "dealer_idx", "action_on",
            "current_bet", "hand_active", "players",
            "small_blind", "big_blind",
        ]
        for key in required_keys:
            assert key in state, f"Missing key: {key}"

    def test_state_street_is_preflop(self):
        e = _make_engine(3)
        state = _deal_and_get(e)
        assert state["street"] == "preflop"

    def test_player_count_in_state(self):
        e = _make_engine(5)
        state = _deal_and_get(e)
        assert len(state["players"]) == 5

    def test_state_includes_blinds_info(self):
        e = _make_engine(3, small_blind=25, big_blind=50)
        state = _deal_and_get(e)
        assert state["small_blind"] == 25
        assert state["big_blind"] == 50

    def test_state_includes_pause_fields(self):
        e = _make_engine(3)
        state = _deal_and_get(e)
        assert "paused" in state
        assert "total_paused_seconds" in state


# ── Player view ──────────────────────────────────────────────────────

class TestPlayerView:
    def test_player_sees_own_cards(self):
        e = _make_engine(3)
        _deal_and_get(e)
        view = e.get_player_view("p0")
        assert len(view["my_cards"]) == 2

    def test_player_does_not_see_others_cards(self):
        e = _make_engine(3)
        _deal_and_get(e)
        view = e.get_player_view("p0")
        for p_data in view["players"]:
            if p_data["player_id"] != "p0":
                assert "hole_cards" not in p_data

    def test_valid_actions_included(self):
        e = _make_engine(3)
        _deal_and_get(e)
        active_pid = e.seats[e.action_on_idx].player_id
        view = e.get_player_view(active_pid)
        assert len(view["valid_actions"]) > 0

    def test_non_active_player_has_no_actions(self):
        e = _make_engine(3)
        _deal_and_get(e)
        active_pid = e.seats[e.action_on_idx].player_id
        other_pid = [p.player_id for p in e.seats if p.player_id != active_pid][0]
        view = e.get_player_view(other_pid)
        assert view["valid_actions"] == []


# ── HandHistory ──────────────────────────────────────────────────────

class TestHandHistory:
    def test_record_action(self):
        hh = HandHistory(1)
        from app.engine import PlayerAction
        hh.record_action("p0", PlayerAction.FOLD, 0, Street.PREFLOP)
        assert len(hh.actions) == 1
        assert hh.actions[0]["action"] == "fold"

    def test_record_community(self):
        hh = HandHistory(1)
        cards = [Card(Rank.ACE, Suit.SPADES), Card(Rank.KING, Suit.HEARTS), Card(Rank.QUEEN, Suit.DIAMONDS)]
        hh.record_community(cards)
        assert len(hh.community_cards) == 1
        assert len(hh.community_cards[0]) == 3

    def test_to_dict(self):
        hh = HandHistory(5)
        d = hh.to_dict()
        assert d["hand_number"] == 5
        assert d["actions"] == []
        assert d["winners"] == []


# ── Blind schedule ───────────────────────────────────────────────────

class TestBlindSchedule:
    def test_no_schedule_when_duration_zero(self):
        e = _make_engine(3, blind_level_duration=0)
        assert e.blind_schedule == []

    def test_schedule_built_when_duration_set(self):
        e = _make_engine(3, small_blind=10, big_blind=20, blind_level_duration=15)
        assert len(e.blind_schedule) > 0
        assert e.blind_schedule[0] == (10, 20)

    def test_custom_schedule(self):
        custom = [(5, 10), (10, 20), (25, 50)]
        e = _make_engine(3, blind_schedule=custom, blind_level_duration=10)
        assert e.blind_schedule == custom

    def test_blind_level_advances(self):
        e = _make_engine(3, small_blind=10, big_blind=20, blind_level_duration=1)
        # Fake: game started 2 minutes ago
        _deal_and_get(e)
        e.game_started_at = time.time() - 120  # 2 minutes ago
        e.total_paused_seconds = 0
        e._maybe_advance_blind_level()
        assert e.blind_level >= 1

    def test_next_blind_change_none_when_disabled(self):
        e = _make_engine(3, blind_level_duration=0)
        assert e.get_next_blind_change_at() is None

    def test_next_blind_change_none_when_paused(self):
        e = _make_engine(3, small_blind=10, big_blind=20, blind_level_duration=15)
        _deal_and_get(e)
        # End the hand so we can pause
        for _ in range(10):
            if not e.hand_active:
                break
            pid = e.seats[e.action_on_idx].player_id
            e.process_action(pid, "fold")
        e.pause()
        assert e.get_next_blind_change_at() is None


# ── Pause / Unpause ─────────────────────────────────────────────────

class TestPause:
    def _end_hand(self, engine: GameEngine):
        """Force-end a hand by having players fold."""
        for _ in range(20):
            if not engine.hand_active:
                return
            pid = engine.seats[engine.action_on_idx].player_id
            engine.process_action(pid, "fold")

    def test_pause_between_hands(self):
        e = _make_engine(3)
        _deal_and_get(e)
        self._end_hand(e)
        state = e.pause()
        assert state["paused"] is True
        assert e.paused

    def test_cannot_pause_during_hand(self):
        e = _make_engine(3)
        _deal_and_get(e)
        with pytest.raises(ValueError, match="Cannot pause during"):
            e.pause()

    def test_cannot_double_pause(self):
        e = _make_engine(3)
        _deal_and_get(e)
        self._end_hand(e)
        e.pause()
        with pytest.raises(ValueError, match="already paused"):
            e.pause()

    def test_unpause(self):
        e = _make_engine(3)
        _deal_and_get(e)
        self._end_hand(e)
        e.pause()
        state = e.unpause()
        assert state["paused"] is False
        assert not e.paused

    def test_cannot_unpause_when_not_paused(self):
        e = _make_engine(3)
        _deal_and_get(e)
        self._end_hand(e)
        with pytest.raises(ValueError, match="not paused"):
            e.unpause()

    def test_pause_accumulates_time(self):
        e = _make_engine(3)
        _deal_and_get(e)
        self._end_hand(e)
        e.pause()
        # Fake 5 seconds of pause
        e.paused_at = time.time() - 5
        e.unpause()
        assert e.total_paused_seconds >= 4.5


# ── Rebuy ────────────────────────────────────────────────────────────

class TestRebuy:
    def _end_hand(self, engine):
        for _ in range(20):
            if not engine.hand_active:
                return
            pid = engine.seats[engine.action_on_idx].player_id
            engine.process_action(pid, "fold")

    def test_rebuy_restores_chips(self):
        e = _make_engine(3, starting_chips=100, allow_rebuys=True)
        _deal_and_get(e)
        self._end_hand(e)
        e.seats[0].chips = 0
        e.rebuy("p0")
        assert e.seats[0].chips == 100
        assert e.seats[0].rebuy_count == 1

    def test_rebuy_when_disabled(self):
        e = _make_engine(3, allow_rebuys=False)
        _deal_and_get(e)
        self._end_hand(e)
        e.seats[0].chips = 0
        with pytest.raises(ValueError, match="not allowed"):
            e.rebuy("p0")

    def test_rebuy_during_hand_queues(self):
        e = _make_engine(3, allow_rebuys=True)
        _deal_and_get(e)
        e.seats[0].chips = 0
        e.seats[0].folded = True
        e.rebuy("p0")
        assert e.seats[0].rebuy_queued is True
        assert e.seats[0].chips == 0  # not yet restored

    def test_queued_rebuy_processed_on_new_hand(self):
        e = _make_engine(3, starting_chips=100, allow_rebuys=True)
        _deal_and_get(e)
        # End the hand first
        self._end_hand(e)
        # Start a new hand
        e.start_new_hand()
        # Now during this hand, bust p0 and queue a rebuy
        e.seats[0].chips = 0
        e.seats[0].folded = True
        e.rebuy("p0")  # queues during hand
        assert e.seats[0].rebuy_queued is True
        # End this hand
        self._end_hand(e)
        # Now deal the next hand — queued rebuy should be processed
        e.start_new_hand()
        assert e.seats[0].chips > 0  # restored (minus any blind posted)
        assert e.seats[0].rebuy_count == 1
        assert e.seats[0].rebuy_queued is False
        assert e.seats[0].is_sitting_out is False

    def test_double_queue_rebuy_fails(self):
        e = _make_engine(3, allow_rebuys=True)
        _deal_and_get(e)
        e.seats[0].chips = 0
        e.seats[0].folded = True
        e.rebuy("p0")
        with pytest.raises(ValueError, match="already queued"):
            e.rebuy("p0")

    def test_cancel_queued_rebuy(self):
        e = _make_engine(3, allow_rebuys=True)
        _deal_and_get(e)
        e.seats[0].chips = 0
        e.seats[0].folded = True
        e.rebuy("p0")
        assert e.seats[0].rebuy_queued is True
        e.cancel_rebuy("p0")
        assert e.seats[0].rebuy_queued is False

    def test_cancel_rebuy_when_none_queued_fails(self):
        e = _make_engine(3, allow_rebuys=True)
        _deal_and_get(e)
        with pytest.raises(ValueError, match="No rebuy queued"):
            e.cancel_rebuy("p0")

    def test_queued_rebuy_respects_max_rebuys(self):
        e = _make_engine(3, starting_chips=100, allow_rebuys=True, max_rebuys=1)
        _deal_and_get(e)
        self._end_hand(e)
        e.seats[0].chips = 0
        e.rebuy("p0")  # immediate rebuy (between hands)
        assert e.seats[0].rebuy_count == 1
        # Queue during next hand should fail — already at max
        e.start_new_hand()
        e.seats[0].chips = 0
        e.seats[0].folded = True
        with pytest.raises(ValueError, match="Maximum rebuys"):
            e.rebuy("p0")

    def test_queued_rebuy_respects_cutoff(self):
        e = _make_engine(3, starting_chips=100, allow_rebuys=True, rebuy_cutoff_minutes=1)
        _deal_and_get(e)
        e.seats[0].chips = 0
        e.seats[0].folded = True
        e.game_started_at = time.time() - 120
        with pytest.raises(ValueError, match="window has closed"):
            e.rebuy("p0")

    def test_rebuy_with_chips_remaining_fails(self):
        e = _make_engine(3, allow_rebuys=True)
        _deal_and_get(e)
        self._end_hand(e)
        with pytest.raises(ValueError, match="still has chips"):
            e.rebuy("p0")

    def test_rebuy_limit(self):
        e = _make_engine(3, starting_chips=100, allow_rebuys=True, max_rebuys=1)
        _deal_and_get(e)
        self._end_hand(e)
        e.seats[0].chips = 0
        e.rebuy("p0")
        e.seats[0].chips = 0
        with pytest.raises(ValueError, match="Maximum rebuys"):
            e.rebuy("p0")

    def test_rebuy_unlimited(self):
        e = _make_engine(3, starting_chips=100, allow_rebuys=True, max_rebuys=0)
        _deal_and_get(e)
        self._end_hand(e)
        for i in range(5):
            e.seats[0].chips = 0
            e.rebuy("p0")
        assert e.seats[0].rebuy_count == 5

    def test_rebuy_cutoff(self):
        e = _make_engine(3, starting_chips=100, allow_rebuys=True, rebuy_cutoff_minutes=1)
        _deal_and_get(e)
        self._end_hand(e)
        e.seats[0].chips = 0
        # Fake: game started 2 minutes ago
        e.game_started_at = time.time() - 120
        with pytest.raises(ValueError, match="window has closed"):
            e.rebuy("p0")

    def test_rebuy_invalid_player(self):
        e = _make_engine(3, allow_rebuys=True)
        _deal_and_get(e)
        self._end_hand(e)
        with pytest.raises(ValueError, match="not found"):
            e.rebuy("nonexistent")


# ── Show cards ───────────────────────────────────────────────────────

class TestShowCards:
    def _end_hand(self, engine):
        for _ in range(20):
            if not engine.hand_active:
                return
            pid = engine.seats[engine.action_on_idx].player_id
            engine.process_action(pid, "fold")

    def test_show_cards_after_hand(self):
        e = _make_engine(3)
        _deal_and_get(e)
        self._end_hand(e)
        e.show_cards("p0")
        assert "p0" in e.shown_cards

    def test_show_cards_during_hand_fails(self):
        e = _make_engine(3)
        _deal_and_get(e)
        with pytest.raises(ValueError, match="still active"):
            e.show_cards("p0")

    def test_show_cards_invalid_player(self):
        e = _make_engine(3)
        _deal_and_get(e)
        self._end_hand(e)
        with pytest.raises(ValueError, match="not found"):
            e.show_cards("nonexistent")
