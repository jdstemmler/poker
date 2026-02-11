"""Tests for the GameEngine — hand lifecycle, dealing, blinds, dealer rotation."""

import time
import pytest
from unittest.mock import patch

from app.cards import Card, Deck, Rank, Suit
from app.engine import GameEngine, PlayerState, Street, HandHistory, _round_blind, _nice_blind


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
        assert "wins the game!" in state["message"]
        assert len(state["final_standings"]) > 0


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

    def test_heads_up_dealer_rotates_after_fold(self):
        """Dealer must rotate after the non-dealer folds."""
        e = _make_engine(2, small_blind=5, big_blind=10)
        _deal_and_get(e)
        dealer_hand1 = e.dealer_idx
        # Dealer (SB) acts first in heads-up; non-dealer is the other seat
        non_dealer_idx = 1 - dealer_hand1
        # Dealer folds
        e.process_action(e.seats[dealer_hand1].player_id, "fold")
        assert not e.hand_active
        # Deal next hand — dealer should rotate to the other player
        e.start_new_hand()
        assert e.dealer_idx == non_dealer_idx

    def test_heads_up_dealer_rotates_after_non_dealer_folds(self):
        """Dealer must rotate even when non-dealer folds (the reported bug)."""
        e = _make_engine(2, small_blind=5, big_blind=10)
        _deal_and_get(e)
        dealer_hand1 = e.dealer_idx
        non_dealer_idx = 1 - dealer_hand1
        # Dealer calls BB
        e.process_action(e.seats[e.action_on_idx].player_id, "call")
        # Non-dealer (BB) folds on flop
        e.process_action(e.seats[e.action_on_idx].player_id, "fold")
        assert not e.hand_active
        # Deal next hand — dealer must rotate
        e.start_new_hand()
        assert e.dealer_idx == non_dealer_idx


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

class TestRoundBlind:
    def test_small_values(self):
        assert _round_blind(1) == 1
        assert _round_blind(3) == 3
        assert _round_blind(0.4) == 1  # min 1

    def test_round_to_nearest_5(self):
        assert _round_blind(12) == 10
        assert _round_blind(13) == 15
        assert _round_blind(22.5) == 20  # round(22.5)=22, nearest 5=20
        assert _round_blind(47) == 45

    def test_round_to_nearest_10(self):
        assert _round_blind(105) == 100  # round(105/10)*10 = 100
        assert _round_blind(150) == 150
        assert _round_blind(234) == 230
        assert _round_blind(999) == 1000


class TestBlindSchedule:
    def test_no_schedule_when_target_zero(self):
        """target_game_time=0 means fixed blinds — no schedule."""
        e = _make_engine(3, starting_chips=5000, target_game_time=0)
        assert e.blind_schedule == []

    def test_blinds_derived_from_chips(self):
        """When no explicit blinds, BB = chips/100, SB = BB/2."""
        e = _make_engine(3, starting_chips=5000, small_blind=0, big_blind=0)
        assert e.big_blind == 50  # 5000/100 = 50
        assert e.small_blind == 25

    def test_blinds_derived_small_chips(self):
        """Small chip amounts still produce valid blinds."""
        e = _make_engine(3, starting_chips=100, small_blind=0, big_blind=0)
        assert e.big_blind == 2  # max(2, 100/100) → 2 is closest standard value
        assert e.small_blind == 1

    def test_nice_blind_snaps_to_standard(self):
        """_nice_blind should snap to standard tournament values."""
        assert _nice_blind(50) == 50
        assert _nice_blind(73) == 80  # snaps to nearest standard (80)
        assert _nice_blind(110) == 100  # 100 is closer than 150
        assert _nice_blind(125) == 100  # 100 or 150 — equidistant, picks lower
        assert _nice_blind(130) == 150  # 150 is closer
        assert _nice_blind(450) == 400  # 400 vs 500 — equidistant, picks lower
        assert _nice_blind(460) == 500  # 500 is closer
        assert _nice_blind(1) == 1

    def test_schedule_built_for_target(self):
        """Schedule should be built when target_game_time > 0."""
        e = _make_engine(3, starting_chips=5000, blind_level_duration=20, target_game_time=4)
        assert len(e.blind_schedule) > 0
        # First level should match derived initial blinds
        assert e.blind_schedule[0] == (e.small_blind, e.big_blind)

    def test_schedule_values_are_standard(self):
        """All schedule values should be standard tournament blind amounts."""
        from app.engine import _STANDARD_BLINDS
        e = _make_engine(3, starting_chips=5000, blind_level_duration=20, target_game_time=4)
        for sb, bb in e.blind_schedule:
            assert bb in _STANDARD_BLINDS, f"BB={bb} not in standard blinds"

    def test_schedule_starts_linear(self):
        """First few levels should grow by initial BB (linear)."""
        e = _make_engine(3, starting_chips=5000, blind_level_duration=20, target_game_time=4)
        # BB should go 50, 100, 150, 200, 250, 300 in early levels
        assert e.blind_schedule[0][1] == 50
        assert e.blind_schedule[1][1] == 100
        assert e.blind_schedule[2][1] == 150

    def test_schedule_levels_increase(self):
        """Each level's BB should be >= the previous level's BB."""
        e = _make_engine(3, starting_chips=5000, blind_level_duration=20, target_game_time=4)
        for i in range(1, len(e.blind_schedule)):
            assert e.blind_schedule[i][1] >= e.blind_schedule[i - 1][1]

    def test_schedule_reaches_all_in_level(self):
        """The schedule should reach or exceed starting_chips as BB."""
        e = _make_engine(3, starting_chips=5000, blind_level_duration=20, target_game_time=4)
        max_bb = max(bb for _, bb in e.blind_schedule)
        assert max_bb >= e.starting_chips

    def test_schedule_no_duplicate_consecutive_levels(self):
        """No two consecutive levels should be identical (deduplication)."""
        e = _make_engine(3, starting_chips=5000, blind_level_duration=20, target_game_time=4)
        for i in range(1, len(e.blind_schedule)):
            assert e.blind_schedule[i] != e.blind_schedule[i - 1]

    def test_schedule_sb_less_than_bb(self):
        """SB should always be less than BB at every level."""
        e = _make_engine(3, starting_chips=5000, blind_level_duration=10, target_game_time=2)
        for sb, bb in e.blind_schedule:
            assert sb < bb, f"SB={sb} >= BB={bb}"

    def test_target_game_time_preserved_in_serialization(self):
        """target_game_time should survive to_dict/from_dict round-trip."""
        e = _make_engine(3, starting_chips=5000, blind_level_duration=20, target_game_time=3)
        d = e.to_dict()
        assert d["target_game_time"] == 3
        e2 = GameEngine.from_dict(d)
        assert e2.target_game_time == 3
        assert e2.blind_schedule == e.blind_schedule

    def test_custom_schedule(self):
        custom = [(5, 10), (10, 20), (25, 50)]
        e = _make_engine(3, blind_schedule=custom, blind_level_duration=10)
        assert e.blind_schedule == custom

    def test_blind_level_advances(self):
        e = _make_engine(3, starting_chips=5000, blind_level_duration=1, target_game_time=1)
        # Fake: game started 2 minutes ago
        _deal_and_get(e)
        e.game_started_at = time.time() - 120  # 2 minutes ago
        e.total_paused_seconds = 0
        e._maybe_advance_blind_level()
        assert e.blind_level >= 1

    def test_next_blind_change_none_when_fixed(self):
        """Fixed blinds (no schedule) should return None for next change."""
        e = _make_engine(3, starting_chips=5000, target_game_time=0)
        assert e.get_next_blind_change_at() is None

    def test_next_blind_change_none_when_paused(self):
        e = _make_engine(3, starting_chips=5000, blind_level_duration=15, target_game_time=2)
        _deal_and_get(e)
        # End the hand so we can pause
        for _ in range(10):
            if not e.hand_active:
                break
            pid = e.seats[e.action_on_idx].player_id
            e.process_action(pid, "fold")
        e.pause()
        assert e.get_next_blind_change_at() is None

    def test_various_chip_levels(self):
        """Schedule works for a variety of chip/time combos."""
        for chips, hours in [(1000, 2), (5000, 4), (10000, 3), (50000, 6)]:
            e = _make_engine(3, starting_chips=chips, blind_level_duration=15, target_game_time=hours)
            assert len(e.blind_schedule) >= 3, f"chips={chips}, hours={hours}"
            assert e.blind_schedule[0] == (e.small_blind, e.big_blind)

    def test_overtime_levels_reach_3x_chips(self):
        """Pre-built schedule should extend until BB >= 3× starting chips."""
        e = _make_engine(3, starting_chips=5000, blind_level_duration=20, target_game_time=4)
        max_bb = max(bb for _, bb in e.blind_schedule)
        assert max_bb >= 5000 * 3

    def test_dynamic_extension_beyond_schedule(self):
        """Clock past the last level should grow the schedule dynamically."""
        e = _make_engine(3, starting_chips=5000, blind_level_duration=1, target_game_time=1)
        _deal_and_get(e)
        original_len = len(e.blind_schedule)
        # Simulate enough time to far exceed the built schedule
        e.game_started_at = time.time() - (original_len + 5) * 60
        e.total_paused_seconds = 0
        e._maybe_advance_blind_level()
        # Schedule should have been extended dynamically
        assert len(e.blind_schedule) > original_len
        # Blinds should be higher than the last pre-built level
        assert e.big_blind > e.blind_schedule[original_len - 1][1]

    def test_dynamic_extension_always_increases(self):
        """Each dynamically added level should have a higher BB."""
        e = _make_engine(3, starting_chips=1000, blind_level_duration=1, target_game_time=1)
        _deal_and_get(e)
        original_len = len(e.blind_schedule)
        e.game_started_at = time.time() - (original_len + 10) * 60
        e.total_paused_seconds = 0
        e._maybe_advance_blind_level()
        for i in range(1, len(e.blind_schedule)):
            assert e.blind_schedule[i][1] >= e.blind_schedule[i - 1][1]

    def test_next_blind_change_always_available(self):
        """get_next_blind_change_at should always return a value (dynamic)."""
        e = _make_engine(3, starting_chips=5000, blind_level_duration=1, target_game_time=1)
        _deal_and_get(e)
        original_last = len(e.blind_schedule) - 1
        # Set level to what was the last pre-built level
        e.blind_level = original_last
        # Should still return a next change time (not None)
        assert e.get_next_blind_change_at() is not None


# ── Auto-deal toggle ────────────────────────────────────────────────

class TestAutoDealToggle:
    def test_auto_deal_enabled_by_default(self):
        e = _make_engine(3)
        assert e.auto_deal_delay == 10

    def test_auto_deal_disabled(self):
        e = _make_engine(3, auto_deal_enabled=False)
        assert e.auto_deal_delay == 0

    def test_auto_deal_disabled_no_deadline(self):
        """When auto-deal is disabled, no deadline should be set after hand ends."""
        e = _make_engine(3, auto_deal_enabled=False)
        _deal_and_get(e)
        # End the hand by folding everyone
        for _ in range(20):
            if not e.hand_active:
                break
            pid = e.seats[e.action_on_idx].player_id
            e.process_action(pid, "fold")
        assert e.auto_deal_deadline is None

    def test_auto_deal_enabled_sets_deadline(self):
        """When auto-deal is enabled, a deadline should be set after hand ends."""
        e = _make_engine(3, auto_deal_enabled=True)
        _deal_and_get(e)
        for _ in range(20):
            if not e.hand_active:
                break
            pid = e.seats[e.action_on_idx].player_id
            e.process_action(pid, "fold")
        assert e.auto_deal_deadline is not None

    def test_auto_deal_preserved_in_serialization(self):
        """auto_deal_delay should survive to_dict/from_dict round-trip."""
        e = _make_engine(3, auto_deal_enabled=False)
        d = e.to_dict()
        assert d["auto_deal_delay"] == 0
        e2 = GameEngine.from_dict(d)
        assert e2.auto_deal_delay == 0


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

    def test_busted_player_eliminated_after_cutoff_expires(self):
        """When rebuy cutoff expires, busted players should be eliminated on next hand."""
        e = _make_engine(2, starting_chips=100, allow_rebuys=True, rebuy_cutoff_minutes=1)
        _deal_and_get(e)
        self._end_hand(e)
        # Bust p0
        e.seats[0].chips = 0
        # Simulate cutoff expired (2 minutes past)
        e.game_started_at = time.time() - 120
        # Start new hand — should trigger game over
        state = e.start_new_hand()
        assert state["game_over"] is True
        assert e.seats[0].is_sitting_out is True

    def test_busted_player_eliminated_after_max_rebuys(self):
        """When max rebuys reached, busted player should be eliminated on next hand."""
        e = _make_engine(2, starting_chips=100, allow_rebuys=True, max_rebuys=1)
        _deal_and_get(e)
        self._end_hand(e)
        e.seats[0].chips = 0
        e.rebuy("p0")
        e.start_new_hand()
        self._end_hand(e)
        e.seats[0].chips = 0
        # At max rebuys, start_new_hand should eliminate p0
        state = e.start_new_hand()
        assert state["game_over"] is True
        assert e.seats[0].is_sitting_out is True

    def test_can_rebuy_field_in_state(self):
        """State broadcast should include can_rebuy per player."""
        e = _make_engine(3, starting_chips=100, allow_rebuys=True, rebuy_cutoff_minutes=60)
        _deal_and_get(e)
        self._end_hand(e)
        e.seats[0].chips = 0
        state = e._build_state()
        p0_state = [p for p in state["players"] if p["player_id"] == "p0"][0]
        assert p0_state["can_rebuy"] is True

    def test_can_rebuy_false_after_cutoff(self):
        """can_rebuy should be False after cutoff expires."""
        e = _make_engine(2, starting_chips=100, allow_rebuys=True, rebuy_cutoff_minutes=1)
        _deal_and_get(e)
        self._end_hand(e)
        e.seats[0].chips = 0
        e.game_started_at = time.time() - 120
        state = e._build_state()
        p0_state = [p for p in state["players"] if p["player_id"] == "p0"][0]
        assert p0_state["can_rebuy"] is False

    def test_rebuy_disabled_heads_up(self):
        """When only 2 players are active, busting should end the game (no rebuy)."""
        e = _make_engine(2, starting_chips=100, allow_rebuys=True)
        _deal_and_get(e)
        self._end_hand(e)
        e.seats[0].chips = 0
        # _can_rebuy should return False in heads-up
        assert e._can_rebuy(e.seats[0]) is False
        # Starting a new hand should trigger game over
        state = e.start_new_hand()
        assert state["game_over"] is True

    def test_rebuy_allowed_with_three_players(self):
        """With 3+ active players, rebuy should still be allowed for busted player."""
        e = _make_engine(3, starting_chips=100, allow_rebuys=True)
        _deal_and_get(e)
        self._end_hand(e)
        e.seats[0].chips = 0
        assert e._can_rebuy(e.seats[0]) is True

    def test_bust_adds_to_elimination_order(self):
        """Busting adds player to elimination_order immediately (even if rebuy-eligible)."""
        e = _make_engine(3, starting_chips=100, allow_rebuys=True)
        _deal_and_get(e)
        self._end_hand(e)
        # Simulate p0 lost all chips during the hand
        e.seats[0].chips = 0
        e._check_game_over()  # as would fire at end of hand
        assert any(entry["player_id"] == "p0" for entry in e.elimination_order)
        assert e.seats[0].is_sitting_out is True
        # p0 can still rebuy (would bring count back to 3)
        assert e._can_rebuy(e.seats[0]) is True

    def test_rebuy_removes_from_elimination_order(self):
        """Rebuying removes the player from elimination_order."""
        e = _make_engine(3, starting_chips=100, allow_rebuys=True)
        _deal_and_get(e)
        self._end_hand(e)
        e.seats[0].chips = 0
        e._check_game_over()
        assert any(entry["player_id"] == "p0" for entry in e.elimination_order)
        # Rebuy between hands — should remove from elimination_order
        e.rebuy("p0")
        assert not any(entry["player_id"] == "p0" for entry in e.elimination_order)
        assert e.seats[0].chips == 100
        assert e.seats[0].is_sitting_out is False

    def test_queued_rebuy_removes_from_elimination_order(self):
        """Queued rebuy removes from elimination_order when processed at start_new_hand."""
        e = _make_engine(3, starting_chips=100, allow_rebuys=True)
        _deal_and_get(e)
        self._end_hand(e)
        # Bust p0, get them into elimination_order
        e.seats[0].chips = 0
        e._check_game_over()
        assert any(entry["player_id"] == "p0" for entry in e.elimination_order)
        # Start hand 2 (p0 sitting out, in elimination_order)
        e.start_new_hand()
        # p0 queues a rebuy during the active hand
        e.rebuy("p0")  # queued since hand is active
        assert e.seats[0].rebuy_queued is True
        self._end_hand(e)
        # start_new_hand processes the rebuy and removes from elimination_order
        e.start_new_hand()
        assert not any(entry["player_id"] == "p0" for entry in e.elimination_order)
        assert e.seats[0].chips > 0
        assert e.seats[0].is_sitting_out is False

    def test_second_bust_before_rebuy_ends_game_with_full_standings(self):
        """P3 busts, then P2 busts before P3 rebuys — game over with complete standings."""
        e = _make_engine(3, starting_chips=100, allow_rebuys=True)
        _deal_and_get(e)
        self._end_hand(e)  # hand 1 ends
        # Simulate p2 lost all chips in hand 1
        e.seats[2].chips = 0
        # start_new_hand adds p2 to elimination_order, sits them out
        e.start_new_hand()  # hand 2 (p0 vs p1)
        assert any(entry["player_id"] == "p2" for entry in e.elimination_order)
        self._end_hand(e)  # hand 2 ends
        # Simulate p1 lost all chips in hand 2
        e.seats[1].chips = 0
        # start_new_hand adds p1 to elimination_order → game over
        state = e.start_new_hand()
        assert state["game_over"] is True
        assert len(e.final_standings) == 3
        # p0 is winner (1st), p1 last eliminated (2nd), p2 first eliminated (3rd)
        assert e.final_standings[0]["player_id"] == "p0"
        assert e.final_standings[0]["place"] == 1
        assert e.final_standings[1]["player_id"] == "p1"
        assert e.final_standings[1]["place"] == 2
        assert e.final_standings[2]["player_id"] == "p2"
        assert e.final_standings[2]["place"] == 3

    def test_rebuy_then_bust_creates_correct_order(self):
        """Player busts, rebuys, then busts again — single entry in elimination_order."""
        e = _make_engine(3, starting_chips=100, allow_rebuys=True)
        _deal_and_get(e)
        self._end_hand(e)
        # Bust p0, add to elimination_order
        e.seats[0].chips = 0
        e._check_game_over()
        assert any(entry["player_id"] == "p0" for entry in e.elimination_order)
        # Rebuy — removed from elimination_order
        e.rebuy("p0")
        assert not any(entry["player_id"] == "p0" for entry in e.elimination_order)
        # Play another hand, bust again
        e.start_new_hand()
        self._end_hand(e)
        e.seats[0].chips = 0
        e._check_game_over()
        # Should be back in elimination_order with exactly one entry
        p0_entries = [entry for entry in e.elimination_order if entry["player_id"] == "p0"]
        assert len(p0_entries) == 1


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


# ── Side Pots ────────────────────────────────────────────────────────

class TestSidePots:
    """Test the _calculate_pots method and side pot award logic."""

    def test_equal_contributions_single_pot(self):
        """Two players bet the same amount — one main pot."""
        e = _make_engine(2, starting_chips=1000)
        e.start_new_hand()
        # Manually set up: both players bet 500
        for s in e.seats:
            s.bet_this_hand = 500
        e.pot = 1000
        pots = e._calculate_pots()
        assert len(pots) == 1
        assert pots[0][0] == 1000
        assert len(pots[0][1]) == 2

    def test_unequal_all_in_creates_two_pots(self):
        """Short-stack all-in creates main pot + side pot."""
        e = _make_engine(2, starting_chips=1000)
        e.start_new_hand()
        # p0 bet 500, p1 bet 1000
        e.seats[0].bet_this_hand = 500
        e.seats[0].all_in = True
        e.seats[1].bet_this_hand = 1000
        e.seats[1].all_in = True
        e.pot = 1500
        pots = e._calculate_pots()
        assert len(pots) == 2
        # Main pot: 500 * 2 = 1000 (both eligible)
        assert pots[0][0] == 1000
        assert len(pots[0][1]) == 2
        # Side pot: 500 (only p1 eligible)
        assert pots[1][0] == 500
        assert len(pots[1][1]) == 1

    def test_three_player_two_side_pots(self):
        """Three players with different stacks create 3 pots."""
        e = _make_engine(3, starting_chips=3000)
        e.start_new_hand()
        # p0: 100, p1: 300, p2: 500
        e.seats[0].bet_this_hand = 100
        e.seats[0].all_in = True
        e.seats[1].bet_this_hand = 300
        e.seats[1].all_in = True
        e.seats[2].bet_this_hand = 500
        e.seats[2].all_in = True
        e.pot = 900
        pots = e._calculate_pots()
        assert len(pots) == 3
        # Main: 100 * 3 = 300, all 3 eligible
        assert pots[0][0] == 300
        assert len(pots[0][1]) == 3
        # Side 1: 200 * 2 = 400, p1 and p2 eligible
        assert pots[1][0] == 400
        assert len(pots[1][1]) == 2
        # Side 2: 200 * 1 = 200, only p2
        assert pots[2][0] == 200
        assert len(pots[2][1]) == 1

    def test_folded_player_contributes_to_pot(self):
        """A folded player's bet goes into the pot but they can't win."""
        e = _make_engine(3, starting_chips=1000)
        e.start_new_hand()
        e.seats[0].bet_this_hand = 200
        e.seats[0].folded = True
        e.seats[1].bet_this_hand = 500
        e.seats[1].all_in = True
        e.seats[2].bet_this_hand = 500
        e.pot = 1200
        pots = e._calculate_pots()
        # Only p1 and p2 are in hand (p0 folded)
        # Contribution levels from in-hand: 500
        # Main pot: p0 contributes 200, p1 contributes 500, p2 contributes 500 = 1200
        assert len(pots) == 1
        assert pots[0][0] == 1200
        # Only p1 and p2 are eligible (p0 folded)
        eligible_ids = {e.seats[i].player_id for i in pots[0][1]}
        assert "p0" not in eligible_ids
        assert "p1" in eligible_ids
        assert "p2" in eligible_ids

    def test_showdown_tie_with_unequal_stacks(self):
        """The user's exact scenario: tie with unequal all-ins returns excess.

        p0: 2500 chips bet, p1: 7500 chips bet. Tie.
        Expected: p0 gets 2500, p1 gets 7500 (unchanged from starting).
        """
        e = _make_engine(2, starting_chips=5000, small_blind=0, big_blind=0)
        e.start_new_hand()

        # Set up state as if both went all-in with unequal stacks
        e.seats[0].chips = 0
        e.seats[0].bet_this_hand = 2500
        e.seats[0].all_in = True
        e.seats[1].chips = 0
        e.seats[1].bet_this_hand = 7500
        e.seats[1].all_in = True
        e.pot = 10000

        # Give them identical-ranked hands to guarantee a tie
        e.seats[0].hole_cards = [Card(Rank.ACE, Suit.HEARTS), Card(Rank.KING, Suit.HEARTS)]
        e.seats[1].hole_cards = [Card(Rank.ACE, Suit.DIAMONDS), Card(Rank.KING, Suit.DIAMONDS)]
        e.community_cards = [
            Card(Rank.TWO, Suit.CLUBS),
            Card(Rank.THREE, Suit.CLUBS),
            Card(Rank.SEVEN, Suit.SPADES),
            Card(Rank.NINE, Suit.SPADES),
            Card(Rank.JACK, Suit.CLUBS),
        ]

        # Directly invoke showdown
        e._showdown()

        assert not e.hand_active
        # p0 should have 2500 (half of main pot 5000)
        # p1 should have 7500 (half of main pot 5000 + side pot 5000)
        assert e.seats[0].chips == 2500
        assert e.seats[1].chips == 7500

    def test_chip_conservation_with_side_pots(self):
        """Total chips are conserved through a side pot showdown."""
        e = _make_engine(3, starting_chips=1000, small_blind=0, big_blind=0)
        e.start_new_hand()

        # Set unequal stacks
        e.seats[0].chips = 200
        e.seats[1].chips = 500
        e.seats[2].chips = 1000
        e.pot = 0
        e.current_bet = 0
        for s in e.seats:
            s.bet_this_round = 0
            s.bet_this_hand = 0

        total_chips = 200 + 500 + 1000

        # p2 goes all-in
        e.action_on_idx = 2
        e.process_action("p2", "all_in")
        # p0 calls all-in (200)
        e.action_on_idx = 0
        e.process_action("p0", "call")
        # p1 calls all-in (500)
        e.action_on_idx = 1
        e.process_action("p1", "call")

        # Hand should be over (all players all-in)
        assert not e.hand_active
        # Chips must be conserved
        total_after = sum(s.chips for s in e.seats)
        assert total_after == total_chips
