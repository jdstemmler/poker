"""Tests for GameEngine serialization (to_dict / from_dict roundtrip)."""

import pytest
from app.engine import GameEngine, Street


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
    return engine.seats[engine.action_on_idx].player_id


class TestEngineSerialization:
    def test_roundtrip_before_hand(self):
        e = _make_engine(3)
        data = e.to_dict()
        e2 = GameEngine.from_dict(data)
        assert e2.game_code == e.game_code
        assert len(e2.seats) == len(e.seats)
        assert e2.hand_number == 0

    def test_roundtrip_during_hand(self):
        e = _make_engine(3)
        e.start_new_hand()
        data = e.to_dict()
        e2 = GameEngine.from_dict(data)
        assert e2.hand_active
        assert e2.hand_number == 1
        assert e2.street == e.street
        assert e2.pot == e.pot
        assert e2.current_bet == e.current_bet

    def test_roundtrip_preserves_hole_cards(self):
        e = _make_engine(2)
        e.start_new_hand()
        data = e.to_dict()
        e2 = GameEngine.from_dict(data)
        for p_orig, p_rest in zip(e.seats, e2.seats):
            assert len(p_rest.hole_cards) == len(p_orig.hole_cards)
            for c1, c2 in zip(p_orig.hole_cards, p_rest.hole_cards):
                assert c1 == c2

    def test_roundtrip_preserves_community_cards(self):
        e = _make_engine(2)
        e.start_new_hand()
        # Play to flop
        e.process_action(_action_pid(e), "call")
        e.process_action(_action_pid(e), "check")
        assert len(e.community_cards) == 3

        data = e.to_dict()
        e2 = GameEngine.from_dict(data)
        assert len(e2.community_cards) == 3
        for c1, c2 in zip(e.community_cards, e2.community_cards):
            assert c1 == c2

    def test_roundtrip_preserves_deck(self):
        e = _make_engine(2)
        e.start_new_hand()
        data = e.to_dict()
        e2 = GameEngine.from_dict(data)
        assert e2.deck is not None
        assert e2.deck.remaining == e.deck.remaining

    def test_roundtrip_preserves_player_state(self):
        e = _make_engine(3)
        e.start_new_hand()
        pid = _action_pid(e)
        e.process_action(pid, "fold")

        data = e.to_dict()
        e2 = GameEngine.from_dict(data)

        for p_orig, p_rest in zip(e.seats, e2.seats):
            assert p_rest.chips == p_orig.chips
            assert p_rest.folded == p_orig.folded
            assert p_rest.all_in == p_orig.all_in
            assert p_rest.bet_this_round == p_orig.bet_this_round
            assert p_rest.bet_this_hand == p_orig.bet_this_hand
            assert p_rest.has_acted == p_orig.has_acted
            assert p_rest.last_action == p_orig.last_action
            assert p_rest.rebuy_count == p_orig.rebuy_count

    def test_roundtrip_preserves_blind_config(self):
        schedule = [(10, 20), (20, 40), (50, 100)]
        e = _make_engine(3, blind_level_duration=15, blind_schedule=schedule)
        e.start_new_hand()

        data = e.to_dict()
        e2 = GameEngine.from_dict(data)
        assert e2.blind_level_duration == 15
        assert e2.blind_schedule == schedule
        assert e2.blind_level == e.blind_level

    def test_roundtrip_preserves_rebuy_config(self):
        e = _make_engine(3, allow_rebuys=True, max_rebuys=3, rebuy_cutoff_minutes=45)
        data = e.to_dict()
        e2 = GameEngine.from_dict(data)
        assert e2.allow_rebuys is True
        assert e2.max_rebuys == 3
        assert e2.rebuy_cutoff_minutes == 45

    def test_roundtrip_preserves_rebuy_queued(self):
        e = _make_engine(3, allow_rebuys=True)
        e.start_new_hand()
        e.seats[0].chips = 0
        e.seats[0].folded = True
        e.rebuy("p0")
        assert e.seats[0].rebuy_queued is True

        data = e.to_dict()
        e2 = GameEngine.from_dict(data)
        assert e2.seats[0].rebuy_queued is True

    def test_roundtrip_preserves_shown_cards(self):
        e = _make_engine(3)
        e.start_new_hand()
        # End hand
        e.process_action(_action_pid(e), "fold")
        e.process_action(_action_pid(e), "fold")
        e.show_cards("p0")

        data = e.to_dict()
        e2 = GameEngine.from_dict(data)
        assert "p0" in e2.shown_cards

    def test_roundtrip_preserves_pause_state(self):
        e = _make_engine(3)
        e.start_new_hand()
        # End hand
        e.process_action(_action_pid(e), "fold")
        e.process_action(_action_pid(e), "fold")
        e.pause()

        data = e.to_dict()
        e2 = GameEngine.from_dict(data)
        assert e2.paused is True
        assert e2.paused_at is not None

    def test_restored_engine_can_process_actions(self):
        """After restoring from dict, the engine should still function."""
        e = _make_engine(3)
        e.start_new_hand()

        data = e.to_dict()
        e2 = GameEngine.from_dict(data)

        # Should be able to continue playing
        pid = _action_pid(e2)
        e2.process_action(pid, "fold")
        pid = _action_pid(e2)
        e2.process_action(pid, "fold")
        assert not e2.hand_active

    def test_restored_engine_can_deal(self):
        """After restoring from dict when hand is over, can deal a new hand."""
        e = _make_engine(3)
        e.start_new_hand()
        e.process_action(_action_pid(e), "fold")
        e.process_action(_action_pid(e), "fold")

        data = e.to_dict()
        e2 = GameEngine.from_dict(data)
        e2.start_new_hand()
        assert e2.hand_active
        assert e2.hand_number == 2

    def test_to_dict_has_all_fields(self):
        e = _make_engine(3)
        e.start_new_hand()
        data = e.to_dict()
        expected_keys = [
            "game_code", "small_blind", "big_blind", "allow_rebuys",
            "max_rebuys", "rebuy_cutoff_minutes", "starting_chips",
            "turn_timeout", "dealer_idx", "hand_number", "street",
            "pot", "current_bet", "min_raise", "hand_active",
            "action_on_idx", "last_raiser_idx", "community_cards",
            "deck", "seats", "shown_cards", "paused",
            "paused_at", "total_paused_seconds",
            "blind_level_duration", "blind_schedule", "blind_level",
        ]
        for key in expected_keys:
            assert key in data, f"Missing serialization key: {key}"
