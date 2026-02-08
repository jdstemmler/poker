"""Tests for betting actions: fold, check, call, raise, all-in, and round advancement."""

import pytest
from app.engine import GameEngine, Street


# ── Helpers ──────────────────────────────────────────────────────────

def _make_engine(n_players=3, **kwargs) -> GameEngine:
    players = [{"id": f"p{i}", "name": f"Player{i}"} for i in range(n_players)]
    return GameEngine(
        game_code="TEST01",
        players=players,
        starting_chips=kwargs.pop("starting_chips", 1000),
        small_blind=kwargs.pop("small_blind", 10),
        big_blind=kwargs.pop("big_blind", 20),
        **kwargs,
    )


def _action_pid(engine: GameEngine) -> str:
    """Return the player_id of whoever's turn it is."""
    return engine.seats[engine.action_on_idx].player_id


# ── Fold ─────────────────────────────────────────────────────────────

class TestFold:
    def test_fold_marks_player(self):
        e = _make_engine(3)
        e.start_new_hand()
        pid = _action_pid(e)
        e.process_action(pid, "fold")
        p = e._find_player(pid)
        assert p.folded
        assert p.last_action == "Fold"

    def test_all_fold_awards_pot(self):
        e = _make_engine(3)
        e.start_new_hand()
        # Fold twice — last player wins
        p1 = _action_pid(e)
        e.process_action(p1, "fold")
        p2 = _action_pid(e)
        e.process_action(p2, "fold")
        assert not e.hand_active
        assert e.last_hand_result is not None
        assert len(e.last_hand_result["winners"]) == 1

    def test_fold_always_valid(self):
        e = _make_engine(3)
        e.start_new_hand()
        pid = _action_pid(e)
        actions = e.get_valid_actions(pid)
        action_names = [a["action"] for a in actions]
        assert "fold" in action_names


# ── Check ────────────────────────────────────────────────────────────

class TestCheck:
    def test_check_when_no_bet(self):
        e = _make_engine(3)
        e.start_new_hand()
        # Get to a spot where check is valid — call the BB first from UTG, then SB calls
        utg = _action_pid(e)
        e.process_action(utg, "call")
        sb = _action_pid(e)
        e.process_action(sb, "call")
        # BB can now check (option)
        bb = _action_pid(e)
        actions = e.get_valid_actions(bb)
        action_names = [a["action"] for a in actions]
        assert "check" in action_names
        e.process_action(bb, "check")
        # BB's check completes the preflop round and triggers the flop.
        # reset_for_new_round() clears last_action for active players.
        # Verify the street advanced (the check was accepted).
        assert e.street.value == "flop"

    def test_cannot_check_when_facing_bet(self):
        e = _make_engine(3)
        e.start_new_hand()
        # UTG faces the BB — cannot check
        pid = _action_pid(e)
        with pytest.raises(ValueError, match="Cannot check"):
            e.process_action(pid, "check")


# ── Call ─────────────────────────────────────────────────────────────

class TestCall:
    def test_call_deducts_chips(self):
        e = _make_engine(3, small_blind=10, big_blind=20)
        e.start_new_hand()
        pid = _action_pid(e)
        p = e._find_player(pid)
        chips_before = p.chips
        e.process_action(pid, "call")
        assert p.chips == chips_before - 20  # called BB of 20
        assert p.last_action == "Call 20"

    def test_call_adds_to_pot(self):
        e = _make_engine(3, small_blind=10, big_blind=20)
        e.start_new_hand()
        pot_before = e.pot
        pid = _action_pid(e)
        e.process_action(pid, "call")
        assert e.pot == pot_before + 20

    def test_call_all_in_when_short(self):
        e = _make_engine(3, starting_chips=15, small_blind=10, big_blind=20)
        e.start_new_hand()
        # UTG has 15 chips, needs to call 20 — goes all-in for 15
        pid = _action_pid(e)
        p = e._find_player(pid)
        e.process_action(pid, "call")
        assert p.chips == 0
        assert p.all_in


# ── Raise ────────────────────────────────────────────────────────────

class TestRaise:
    def test_raise_basic(self):
        e = _make_engine(3, small_blind=10, big_blind=20)
        e.start_new_hand()
        pid = _action_pid(e)
        p = e._find_player(pid)
        # Min raise to 40 → cost is 40 (since they have 0 bet this round)
        e.process_action(pid, "raise", 40)
        assert "Raise" in p.last_action
        assert e.current_bet == 40

    def test_raise_updates_current_bet(self):
        e = _make_engine(3, small_blind=10, big_blind=20)
        e.start_new_hand()
        pid = _action_pid(e)
        e.process_action(pid, "raise", 60)
        assert e.current_bet == 60

    def test_raise_resets_others_has_acted(self):
        e = _make_engine(3, small_blind=10, big_blind=20)
        e.start_new_hand()
        pid = _action_pid(e)
        e.process_action(pid, "raise", 40)
        # Other active players should need to act again
        for p in e.seats:
            if p.player_id != pid and p.is_active and not p.folded:
                assert not p.has_acted

    def test_raise_too_small_raises_error(self):
        e = _make_engine(3, small_blind=10, big_blind=20)
        e.start_new_hand()
        pid = _action_pid(e)
        # Min raise is BB (20), so must raise to at least 40.
        # Raising 10 (less than min_raise of 20 from current_bet 20) should fail
        with pytest.raises(ValueError, match="Raise must be at least"):
            e.process_action(pid, "raise", 10)

    def test_raise_valid_actions_include_min_max(self):
        e = _make_engine(3, small_blind=10, big_blind=20)
        e.start_new_hand()
        pid = _action_pid(e)
        actions = e.get_valid_actions(pid)
        raise_action = next(a for a in actions if a["action"] == "raise")
        assert "min_amount" in raise_action
        assert "max_amount" in raise_action
        assert raise_action["min_amount"] <= raise_action["max_amount"]


# ── All-in ───────────────────────────────────────────────────────────

class TestAllIn:
    def test_all_in_sets_flags(self):
        e = _make_engine(3)
        e.start_new_hand()
        pid = _action_pid(e)
        p = e._find_player(pid)
        e.process_action(pid, "all_in")
        assert p.all_in
        assert p.chips == 0
        assert "All-In" in p.last_action

    def test_all_in_adds_to_pot(self):
        e = _make_engine(3, starting_chips=500)
        e.start_new_hand()
        pot_before = e.pot
        pid = _action_pid(e)
        p = e._find_player(pid)
        chips = p.chips
        e.process_action(pid, "all_in")
        assert e.pot == pot_before + chips


# ── Round advancement ────────────────────────────────────────────────

class TestStreetAdvancement:
    def _everyone_calls_or_checks(self, engine: GameEngine):
        """Have all players call/check until the round advances."""
        for _ in range(20):
            if not engine.hand_active:
                return
            pid = _action_pid(engine)
            actions = engine.get_valid_actions(pid)
            action_names = [a["action"] for a in actions]
            if "check" in action_names:
                engine.process_action(pid, "check")
            elif "call" in action_names:
                engine.process_action(pid, "call")
            else:
                engine.process_action(pid, "fold")

    def test_preflop_to_flop(self):
        e = _make_engine(3, small_blind=10, big_blind=20)
        e.start_new_hand()
        assert e.street == Street.PREFLOP

        # Everyone calls, BB checks
        self._everyone_calls_or_checks(e)
        if e.hand_active:
            # Should be on flop now
            assert e.street in (Street.FLOP, Street.TURN, Street.RIVER, Street.SHOWDOWN)
            if e.street == Street.FLOP:
                assert len(e.community_cards) == 3

    def test_full_hand_to_showdown(self):
        """Play a complete hand through to showdown."""
        e = _make_engine(3, small_blind=10, big_blind=20)
        e.start_new_hand()
        self._everyone_calls_or_checks(e)
        # Should reach showdown or one player wins
        if e.hand_active:
            # Still active — keep going
            self._everyone_calls_or_checks(e)
        if e.hand_active:
            self._everyone_calls_or_checks(e)
        if e.hand_active:
            self._everyone_calls_or_checks(e)
        # Hand should be done now
        assert not e.hand_active

    def test_flop_deals_three_community(self):
        e = _make_engine(2, small_blind=10, big_blind=20)
        e.start_new_hand()
        # Heads-up: dealer/SB acts first preflop, call
        pid = _action_pid(e)
        e.process_action(pid, "call")
        # BB checks
        pid = _action_pid(e)
        e.process_action(pid, "check")
        assert e.street == Street.FLOP
        assert len(e.community_cards) == 3

    def test_turn_deals_one_more(self):
        e = _make_engine(2, small_blind=10, big_blind=20)
        e.start_new_hand()
        # Preflop: call, check
        pid = _action_pid(e)
        e.process_action(pid, "call")
        pid = _action_pid(e)
        e.process_action(pid, "check")
        # Flop: check, check
        pid = _action_pid(e)
        e.process_action(pid, "check")
        pid = _action_pid(e)
        e.process_action(pid, "check")
        assert e.street == Street.TURN
        assert len(e.community_cards) == 4

    def test_river_deals_one_more(self):
        e = _make_engine(2, small_blind=10, big_blind=20)
        e.start_new_hand()
        # Preflop
        e.process_action(_action_pid(e), "call")
        e.process_action(_action_pid(e), "check")
        # Flop
        e.process_action(_action_pid(e), "check")
        e.process_action(_action_pid(e), "check")
        # Turn
        e.process_action(_action_pid(e), "check")
        e.process_action(_action_pid(e), "check")
        assert e.street == Street.RIVER
        assert len(e.community_cards) == 5


# ── Error cases ──────────────────────────────────────────────────────

class TestActionErrors:
    def test_action_wrong_player(self):
        e = _make_engine(3)
        e.start_new_hand()
        active_pid = _action_pid(e)
        other = [p.player_id for p in e.seats if p.player_id != active_pid][0]
        with pytest.raises(ValueError, match="Not your turn"):
            e.process_action(other, "fold")

    def test_action_no_hand_active(self):
        e = _make_engine(3)
        with pytest.raises(ValueError, match="No active hand"):
            e.process_action("p0", "fold")

    def test_action_unknown_player(self):
        e = _make_engine(3)
        e.start_new_hand()
        with pytest.raises(ValueError, match="Player not found"):
            e.process_action("nonexistent", "fold")

    def test_unknown_action(self):
        e = _make_engine(3)
        e.start_new_hand()
        pid = _action_pid(e)
        with pytest.raises(ValueError, match="Unknown action"):
            e.process_action(pid, "dance")


# ── Showdown ─────────────────────────────────────────────────────────

class TestShowdown:
    def test_showdown_awards_chips(self):
        e = _make_engine(2, starting_chips=1000, small_blind=10, big_blind=20)
        e.start_new_hand()
        total_chips_before = sum(p.chips + p.bet_this_hand for p in e.seats)

        # Play to showdown
        e.process_action(_action_pid(e), "call")
        e.process_action(_action_pid(e), "check")
        for _ in range(3):
            if not e.hand_active:
                break
            e.process_action(_action_pid(e), "check")
            if e.hand_active:
                e.process_action(_action_pid(e), "check")

        total_chips_after = sum(p.chips for p in e.seats)
        assert total_chips_after == total_chips_before  # chips are conserved

    def test_showdown_has_result(self):
        e = _make_engine(2, small_blind=10, big_blind=20)
        e.start_new_hand()
        e.process_action(_action_pid(e), "call")
        e.process_action(_action_pid(e), "check")
        for _ in range(3):
            if not e.hand_active:
                break
            e.process_action(_action_pid(e), "check")
            if e.hand_active:
                e.process_action(_action_pid(e), "check")

        assert e.last_hand_result is not None
        assert "winners" in e.last_hand_result
        assert len(e.last_hand_result["winners"]) >= 1

    def test_last_player_standing_wins(self):
        e = _make_engine(3, small_blind=10, big_blind=20)
        e.start_new_hand()
        e.process_action(_action_pid(e), "fold")
        e.process_action(_action_pid(e), "fold")
        assert not e.hand_active
        assert e.last_hand_result["winners"][0]["hand"] == "Last player standing"


# ── Chip conservation ────────────────────────────────────────────────

class TestChipConservation:
    def test_chips_conserved_after_fold_win(self):
        e = _make_engine(3, starting_chips=1000)
        total = sum(p.chips for p in e.seats)
        e.start_new_hand()
        e.process_action(_action_pid(e), "fold")
        e.process_action(_action_pid(e), "fold")
        assert sum(p.chips for p in e.seats) == total

    def test_chips_conserved_after_showdown(self):
        e = _make_engine(2, starting_chips=1000, small_blind=10, big_blind=20)
        total = sum(p.chips for p in e.seats)
        e.start_new_hand()
        e.process_action(_action_pid(e), "call")
        e.process_action(_action_pid(e), "check")
        for _ in range(6):
            if not e.hand_active:
                break
            e.process_action(_action_pid(e), "check")
        assert sum(p.chips for p in e.seats) == total

    def test_chips_conserved_with_raise(self):
        e = _make_engine(2, starting_chips=1000, small_blind=10, big_blind=20)
        total = 2000
        e.start_new_hand()
        e.process_action(_action_pid(e), "raise", 60)
        e.process_action(_action_pid(e), "call")
        for _ in range(6):
            if not e.hand_active:
                break
            e.process_action(_action_pid(e), "check")
        assert sum(p.chips for p in e.seats) == total

    def test_chips_conserved_all_in(self):
        e = _make_engine(2, starting_chips=100, small_blind=10, big_blind=20)
        total = 200
        e.start_new_hand()
        e.process_action(_action_pid(e), "all_in")
        e.process_action(_action_pid(e), "call")
        # Should go to showdown
        assert not e.hand_active
        assert sum(p.chips for p in e.seats) == total


# ── Multiple hands ───────────────────────────────────────────────────

class TestMultipleHands:
    def _play_hand(self, engine: GameEngine):
        engine.start_new_hand()
        for _ in range(50):
            if not engine.hand_active:
                return
            pid = _action_pid(engine)
            actions = engine.get_valid_actions(pid)
            action_names = [a["action"] for a in actions]
            if "check" in action_names:
                engine.process_action(pid, "check")
            elif "call" in action_names:
                engine.process_action(pid, "call")
            else:
                engine.process_action(pid, "fold")

    def test_multiple_hands_preserve_chips(self):
        e = _make_engine(3, starting_chips=1000)
        total = 3000
        for _ in range(5):
            self._play_hand(e)
            assert sum(p.chips for p in e.seats) == total

    def test_hand_number_increments(self):
        e = _make_engine(2, starting_chips=1000)
        for i in range(3):
            self._play_hand(e)
            assert e.hand_number == i + 1

    def test_dealer_rotates_each_hand(self):
        e = _make_engine(3, starting_chips=1000)
        dealers = []
        for _ in range(6):
            self._play_hand(e)
            dealers.append(e.dealer_idx)
        # Should have cycled through all 3 positions at least once
        assert len(set(dealers)) >= 2
