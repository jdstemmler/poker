"""Tests for game_manager — business logic with mocked Redis."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from app.game_manager import (
    create_game,
    join_game,
    leave_game,
    toggle_ready,
    start_game,
    get_game_state,
    set_player_connected,
    verify_player,
    process_action,
    deal_next_hand,
    request_rebuy,
    show_cards,
    toggle_pause,
    _hash_pin,
    _verify_pin,
)
from app.models import CreateGameRequest, JoinGameRequest, GameStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PATCH_BASE = "app.game_manager.redis_client"


def _pin_hash(pin: str = "1234") -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


def _make_player_data(
    pid: str = "p1",
    name: str = "Alice",
    pin: str = "1234",
    *,
    is_creator: bool = False,
):
    return {
        "id": pid,
        "name": name,
        "pin_hash": _pin_hash(pin),
        "ready": True,
        "connected": False,
        "is_creator": is_creator,
    }


def _make_game_data(
    code: str = "ABC123",
    status: str = "lobby",
    creator_id: str = "p1",
) -> dict:
    return {
        "code": code,
        "status": status,
        "creator_id": creator_id,
        "settings": {
            "starting_chips": 1000,
            "small_blind": 10,
            "big_blind": 20,
            "max_players": 9,
            "allow_rebuys": True,
            "max_rebuys": 1,
            "rebuy_cutoff_minutes": 60,
            "turn_timeout": 0,
            "blind_level_duration": 0,
        },
    }


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------


class TestPinHashing:
    def test_hash_pin(self):
        h = _hash_pin("1234")
        assert h == hashlib.sha256(b"1234").hexdigest()

    def test_verify_pin_correct(self):
        assert _verify_pin("1234", _pin_hash("1234"))

    def test_verify_pin_wrong(self):
        assert not _verify_pin("0000", _pin_hash("1234"))


# ---------------------------------------------------------------------------
# create_game
# ---------------------------------------------------------------------------


class TestCreateGame:
    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        with patch(f"{PATCH_BASE}.load_game", new_callable=AsyncMock, return_value=None) as m1, \
             patch(f"{PATCH_BASE}.store_game", new_callable=AsyncMock) as m2, \
             patch(f"{PATCH_BASE}.store_player", new_callable=AsyncMock) as m3, \
             patch(f"{PATCH_BASE}.touch_activity", new_callable=AsyncMock) as m4, \
             patch(f"{PATCH_BASE}.load_all_players", new_callable=AsyncMock) as m5:
            self.load_game = m1
            self.store_game = m2
            self.store_player = m3
            self.touch_activity = m4
            self.load_all_players = m5
            yield

    async def test_returns_code_player_id_state(self):
        self.load_all_players.return_value = []
        req = CreateGameRequest(
            creator_name="Alice", creator_pin="1234",
        )

        # load_all_players called in _build_game_state
        # But store_player is called first, so _build_game_state will reload.
        # We need to make load_all_players return the created player.
        async def _return_created_player(code):
            return [_make_player_data("fake_id", "Alice", "1234", is_creator=True)]

        self.load_all_players.side_effect = _return_created_player

        code, pid, state = await create_game(req)

        assert isinstance(code, str)
        assert len(code) == 6
        assert isinstance(pid, str)
        assert state.status == GameStatus.LOBBY
        self.store_game.assert_awaited_once()
        self.store_player.assert_awaited_once()
        self.touch_activity.assert_awaited_once()

    async def test_game_data_uses_defaults(self):
        self.load_all_players.return_value = []
        req = CreateGameRequest(creator_name="Bob", creator_pin="5678")

        _, _, state = await create_game(req)
        assert state.settings.starting_chips == 1000
        assert state.settings.small_blind == 10
        assert state.settings.big_blind == 20


# ---------------------------------------------------------------------------
# join_game
# ---------------------------------------------------------------------------


class TestJoinGame:
    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        with patch(f"{PATCH_BASE}.load_game", new_callable=AsyncMock) as m1, \
             patch(f"{PATCH_BASE}.load_all_players", new_callable=AsyncMock) as m2, \
             patch(f"{PATCH_BASE}.store_player", new_callable=AsyncMock) as m3, \
             patch(f"{PATCH_BASE}.touch_activity", new_callable=AsyncMock) as m4:
            self.load_game = m1
            self.load_all_players = m2
            self.store_player = m3
            self.touch_activity = m4
            yield

    async def test_game_not_found(self):
        self.load_game.return_value = None
        with pytest.raises(ValueError, match="Game not found"):
            await join_game("NOPE", JoinGameRequest(player_name="X", player_pin="1234"))

    async def test_new_player_joins(self):
        self.load_game.return_value = _make_game_data()
        creator = _make_player_data("p1", "Alice", "1234", is_creator=True)
        # First call: looking for existing players.  Second call: _build_game_state
        self.load_all_players.side_effect = [
            [creator],
            [creator, _make_player_data("p2", "Bob", "5678")],
        ]
        req = JoinGameRequest(player_name="Bob", player_pin="5678")
        pid, state = await join_game("ABC123", req)

        assert isinstance(pid, str)
        self.store_player.assert_awaited_once()
        self.touch_activity.assert_awaited_once()

    async def test_reconnect_existing_player(self):
        self.load_game.return_value = _make_game_data(status="active")
        creator = _make_player_data("p1", "Alice", "1234", is_creator=True)
        self.load_all_players.side_effect = [
            [creator],
            [creator],
        ]
        req = JoinGameRequest(player_name="Alice", player_pin="1234")
        pid, state = await join_game("ABC123", req)

        # Should get existing player id back
        assert pid == "p1"
        self.store_player.assert_not_awaited()  # no new player saved

    async def test_reconnect_wrong_pin(self):
        self.load_game.return_value = _make_game_data()
        creator = _make_player_data("p1", "Alice", "1234", is_creator=True)
        self.load_all_players.return_value = [creator]

        with pytest.raises(ValueError, match="wrong PIN"):
            await join_game("ABC123", JoinGameRequest(player_name="Alice", player_pin="0000"))

    async def test_cannot_join_active_game_as_new_player(self):
        self.load_game.return_value = _make_game_data(status="active")
        self.load_all_players.return_value = [
            _make_player_data("p1", "Alice", "1234", is_creator=True),
        ]
        with pytest.raises(ValueError, match="not in lobby"):
            await join_game("ABC123", JoinGameRequest(player_name="Bob", player_pin="5678"))

    async def test_game_full(self):
        game_data = _make_game_data()
        game_data["settings"]["max_players"] = 2
        self.load_game.return_value = game_data
        self.load_all_players.return_value = [
            _make_player_data("p1", "Alice", "1234"),
            _make_player_data("p2", "Bob", "5678"),
        ]
        with pytest.raises(ValueError, match="full"):
            await join_game("ABC123", JoinGameRequest(player_name="Eve", player_pin="9999"))


# ---------------------------------------------------------------------------
# toggle_ready
# ---------------------------------------------------------------------------


class TestToggleReady:
    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        with patch(f"{PATCH_BASE}.load_game", new_callable=AsyncMock) as m1, \
             patch(f"{PATCH_BASE}.load_player", new_callable=AsyncMock) as m2, \
             patch(f"{PATCH_BASE}.store_player", new_callable=AsyncMock) as m3, \
             patch(f"{PATCH_BASE}.load_all_players", new_callable=AsyncMock) as m4:
            self.load_game = m1
            self.load_player = m2
            self.store_player = m3
            self.load_all_players = m4
            yield

    async def test_toggle_ready(self):
        self.load_game.return_value = _make_game_data()
        player = _make_player_data("p1", "Alice", "1234", is_creator=True)
        self.load_player.return_value = player
        self.load_all_players.return_value = [player]

        state = await toggle_ready("ABC123", "p1", "1234")
        # Check that caller stored an updated player with ready toggled
        self.store_player.assert_awaited_once()
        args = self.store_player.call_args
        assert args[0][2]["ready"] is False  # was True, now toggled

    async def test_toggle_ready_wrong_pin(self):
        self.load_game.return_value = _make_game_data()
        self.load_player.return_value = _make_player_data("p1", "Alice", "1234")

        with pytest.raises(ValueError, match="Invalid PIN"):
            await toggle_ready("ABC123", "p1", "0000")

    async def test_toggle_ready_not_lobby(self):
        self.load_game.return_value = _make_game_data(status="active")
        with pytest.raises(ValueError, match="not in lobby"):
            await toggle_ready("ABC123", "p1", "1234")


# ---------------------------------------------------------------------------
# start_game
# ---------------------------------------------------------------------------


class TestStartGame:
    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        with patch(f"{PATCH_BASE}.load_game", new_callable=AsyncMock) as m1, \
             patch(f"{PATCH_BASE}.load_player", new_callable=AsyncMock) as m2, \
             patch(f"{PATCH_BASE}.load_all_players", new_callable=AsyncMock) as m3, \
             patch(f"{PATCH_BASE}.store_game", new_callable=AsyncMock) as m4, \
             patch(f"{PATCH_BASE}.store_engine", new_callable=AsyncMock) as m5, \
             patch(f"{PATCH_BASE}.touch_activity", new_callable=AsyncMock) as m6:
            self.load_game = m1
            self.load_player = m2
            self.load_all_players = m3
            self.store_game = m4
            self.store_engine = m5
            self.touch_activity = m6
            yield

    async def test_start_game(self):
        game = _make_game_data(creator_id="p1")
        self.load_game.return_value = game
        self.load_player.return_value = _make_player_data("p1", "Alice", "1234", is_creator=True)
        players = [
            _make_player_data("p1", "Alice", "1234", is_creator=True),
            _make_player_data("p2", "Bob", "5678"),
        ]
        self.load_all_players.return_value = players

        state = await start_game("ABC123", "p1", "1234")
        assert state.status == GameStatus.ACTIVE
        self.store_engine.assert_awaited_once()

    async def test_start_not_creator(self):
        self.load_game.return_value = _make_game_data(creator_id="p1")
        self.load_player.return_value = _make_player_data("p2", "Bob", "5678")

        with pytest.raises(ValueError, match="Only the creator"):
            await start_game("ABC123", "p2", "5678")

    async def test_start_too_few_players(self):
        self.load_game.return_value = _make_game_data(creator_id="p1")
        self.load_player.return_value = _make_player_data("p1", "Alice", "1234", is_creator=True)
        self.load_all_players.return_value = [
            _make_player_data("p1", "Alice", "1234", is_creator=True),
        ]

        with pytest.raises(ValueError, match="at least 2"):
            await start_game("ABC123", "p1", "1234")


# ---------------------------------------------------------------------------
# verify_player
# ---------------------------------------------------------------------------


class TestVerifyPlayer:
    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        with patch(f"{PATCH_BASE}.load_player", new_callable=AsyncMock) as m:
            self.load_player = m
            yield

    async def test_valid(self):
        self.load_player.return_value = _make_player_data("p1", "Alice", "1234")
        await verify_player("ABC123", "p1", "1234")  # should not raise

    async def test_not_found(self):
        self.load_player.return_value = None
        with pytest.raises(ValueError, match="Player not found"):
            await verify_player("ABC123", "p1", "1234")

    async def test_invalid_pin(self):
        self.load_player.return_value = _make_player_data("p1", "Alice", "1234")
        with pytest.raises(ValueError, match="Invalid PIN"):
            await verify_player("ABC123", "p1", "0000")


# ---------------------------------------------------------------------------
# process_action
# ---------------------------------------------------------------------------


class TestProcessAction:
    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        with patch(f"{PATCH_BASE}.load_player", new_callable=AsyncMock) as m1, \
             patch(f"{PATCH_BASE}.load_engine", new_callable=AsyncMock) as m2, \
             patch(f"{PATCH_BASE}.store_engine", new_callable=AsyncMock) as m3, \
             patch(f"{PATCH_BASE}.touch_activity", new_callable=AsyncMock) as m4:
            self.load_player = m1
            self.load_engine = m2
            self.store_engine = m3
            self.touch_activity = m4
            yield

    def _make_engine_dict(self):
        """Create a real engine, start a hand, and return its serialized dict."""
        from app.engine import GameEngine

        e = GameEngine(
            game_code="ABC123",
            players=[
                {"id": "p1", "name": "Alice"},
                {"id": "p2", "name": "Bob"},
            ],
            starting_chips=1000,
            small_blind=10,
            big_blind=20,
        )
        e.start_new_hand()
        return e.to_dict()

    async def test_process_fold(self):
        self.load_player.return_value = _make_player_data("p1", "Alice", "1234")
        engine_data = self._make_engine_dict()
        self.load_engine.return_value = engine_data

        # Determine who is to act
        from app.engine import GameEngine
        e = GameEngine.from_dict(engine_data)
        actor = e.seats[e.action_on_idx].player_id

        self.load_player.return_value = _make_player_data(actor, "X", "1234")
        result = await process_action("ABC123", actor, "1234", "fold")
        self.store_engine.assert_awaited_once()
        self.touch_activity.assert_awaited_once()


# ---------------------------------------------------------------------------
# deal_next_hand
# ---------------------------------------------------------------------------


class TestDealNextHand:
    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        with patch(f"{PATCH_BASE}.load_game", new_callable=AsyncMock) as m1, \
             patch(f"{PATCH_BASE}.load_player", new_callable=AsyncMock) as m2, \
             patch(f"{PATCH_BASE}.load_engine", new_callable=AsyncMock) as m3, \
             patch(f"{PATCH_BASE}.store_engine", new_callable=AsyncMock) as m4, \
             patch(f"{PATCH_BASE}.touch_activity", new_callable=AsyncMock) as m5:
            self.load_game = m1
            self.load_player = m2
            self.load_engine = m3
            self.store_engine = m4
            self.touch_activity = m5
            yield

    def _finished_engine_dict(self):
        from app.engine import GameEngine

        e = GameEngine(
            game_code="ABC123",
            players=[
                {"id": "p1", "name": "Alice"},
                {"id": "p2", "name": "Bob"},
            ],
            starting_chips=1000,
            small_blind=10,
            big_blind=20,
        )
        e.start_new_hand()
        pid = e.seats[e.action_on_idx].player_id
        e.process_action(pid, "fold")
        return e.to_dict()

    async def test_deal_next_hand(self):
        self.load_game.return_value = _make_game_data(status="active")
        self.load_player.return_value = _make_player_data("p1", "Alice", "1234")
        self.load_engine.return_value = self._finished_engine_dict()

        result = await deal_next_hand("ABC123", "p1", "1234")
        self.store_engine.assert_awaited_once()

    async def test_deal_during_active_hand(self):
        self.load_game.return_value = _make_game_data(status="active")
        self.load_player.return_value = _make_player_data("p1", "Alice", "1234")

        from app.engine import GameEngine

        e = GameEngine(
            game_code="ABC123",
            players=[{"id": "p1", "name": "Alice"}, {"id": "p2", "name": "Bob"}],
            starting_chips=1000, small_blind=10, big_blind=20,
        )
        e.start_new_hand()
        self.load_engine.return_value = e.to_dict()

        with pytest.raises(ValueError, match="still in progress"):
            await deal_next_hand("ABC123", "p1", "1234")

    async def test_deal_while_paused(self):
        self.load_game.return_value = _make_game_data(status="active")
        self.load_player.return_value = _make_player_data("p1", "Alice", "1234")

        from app.engine import GameEngine

        e = GameEngine(
            game_code="ABC123",
            players=[{"id": "p1", "name": "Alice"}, {"id": "p2", "name": "Bob"}],
            starting_chips=1000, small_blind=10, big_blind=20,
        )
        e.start_new_hand()
        pid = e.seats[e.action_on_idx].player_id
        e.process_action(pid, "fold")
        e.pause()
        self.load_engine.return_value = e.to_dict()

        with pytest.raises(ValueError, match="paused"):
            await deal_next_hand("ABC123", "p1", "1234")


# ---------------------------------------------------------------------------
# request_rebuy
# ---------------------------------------------------------------------------


class TestRequestRebuy:
    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        with patch(f"{PATCH_BASE}.load_player", new_callable=AsyncMock) as m1, \
             patch(f"{PATCH_BASE}.load_engine", new_callable=AsyncMock) as m2, \
             patch(f"{PATCH_BASE}.store_engine", new_callable=AsyncMock) as m3, \
             patch(f"{PATCH_BASE}.touch_activity", new_callable=AsyncMock) as m4:
            self.load_player = m1
            self.load_engine = m2
            self.store_engine = m3
            self.touch_activity = m4
            yield

    async def test_rebuy(self):
        from app.engine import GameEngine

        e = GameEngine(
            game_code="ABC123",
            players=[
                {"id": "p1", "name": "Alice"},
                {"id": "p2", "name": "Bob"},
            ],
            starting_chips=1000,
            small_blind=10,
            big_blind=20,
            allow_rebuys=True,
            max_rebuys=3,
        )
        e.start_new_hand()
        # End the hand by having one player fold
        pid = e.seats[e.action_on_idx].player_id
        e.process_action(pid, "fold")
        # Zero out a player's chips (after hand, simulating they lost)
        for s in e.seats:
            if s.player_id == "p1":
                s.chips = 0
        self.load_engine.return_value = e.to_dict()

        self.load_player.return_value = _make_player_data("p1", "Alice", "1234")
        result = await request_rebuy("ABC123", "p1", "1234")

        self.store_engine.assert_awaited_once()
        self.touch_activity.assert_awaited_once()


# ---------------------------------------------------------------------------
# cancel_rebuy
# ---------------------------------------------------------------------------


class TestCancelRebuy:
    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        with patch(f"{PATCH_BASE}.load_player", new_callable=AsyncMock) as m1, \
             patch(f"{PATCH_BASE}.load_engine", new_callable=AsyncMock) as m2, \
             patch(f"{PATCH_BASE}.store_engine", new_callable=AsyncMock) as m3, \
             patch(f"{PATCH_BASE}.touch_activity", new_callable=AsyncMock) as m4:
            self.load_player = m1
            self.load_engine = m2
            self.store_engine = m3
            self.touch_activity = m4
            yield

    async def test_cancel_rebuy(self):
        from app.engine import GameEngine
        from app.game_manager import cancel_rebuy

        e = GameEngine(
            game_code="ABC123",
            players=[
                {"id": "p1", "name": "Alice"},
                {"id": "p2", "name": "Bob"},
            ],
            starting_chips=1000,
            small_blind=10,
            big_blind=20,
            allow_rebuys=True,
        )
        e.start_new_hand()
        # Bust p1 and queue a rebuy
        for s in e.seats:
            if s.player_id == "p1":
                s.chips = 0
                s.folded = True
        e.rebuy("p1")
        assert e.seats[0].rebuy_queued is True

        self.load_engine.return_value = e.to_dict()
        self.load_player.return_value = _make_player_data("p1", "Alice", "1234")
        result = await cancel_rebuy("ABC123", "p1", "1234")

        self.store_engine.assert_awaited_once()
        self.touch_activity.assert_awaited_once()


# ---------------------------------------------------------------------------
# show_cards
# ---------------------------------------------------------------------------


class TestShowCards:
    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        with patch(f"{PATCH_BASE}.load_player", new_callable=AsyncMock) as m1, \
             patch(f"{PATCH_BASE}.load_engine", new_callable=AsyncMock) as m2, \
             patch(f"{PATCH_BASE}.store_engine", new_callable=AsyncMock) as m3:
            self.load_player = m1
            self.load_engine = m2
            self.store_engine = m3
            yield

    async def test_show_cards(self):
        from app.engine import GameEngine

        e = GameEngine(
            game_code="ABC123",
            players=[
                {"id": "p1", "name": "Alice"},
                {"id": "p2", "name": "Bob"},
            ],
            starting_chips=1000,
            small_blind=10,
            big_blind=20,
        )
        e.start_new_hand()
        pid = e.seats[e.action_on_idx].player_id
        e.process_action(pid, "fold")
        self.load_engine.return_value = e.to_dict()

        self.load_player.return_value = _make_player_data("p1", "Alice", "1234")
        result = await show_cards("ABC123", "p1", "1234")

        self.store_engine.assert_awaited_once()


# ---------------------------------------------------------------------------
# toggle_pause
# ---------------------------------------------------------------------------


class TestTogglePause:
    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        with patch(f"{PATCH_BASE}.load_game", new_callable=AsyncMock) as m1, \
             patch(f"{PATCH_BASE}.load_player", new_callable=AsyncMock) as m2, \
             patch(f"{PATCH_BASE}.load_engine", new_callable=AsyncMock) as m3, \
             patch(f"{PATCH_BASE}.store_engine", new_callable=AsyncMock) as m4, \
             patch(f"{PATCH_BASE}.touch_activity", new_callable=AsyncMock) as m5:
            self.load_game = m1
            self.load_player = m2
            self.load_engine = m3
            self.store_engine = m4
            self.touch_activity = m5
            yield

    def _engine_between_hands(self):
        from app.engine import GameEngine

        e = GameEngine(
            game_code="ABC123",
            players=[
                {"id": "p1", "name": "Alice"},
                {"id": "p2", "name": "Bob"},
            ],
            starting_chips=1000,
            small_blind=10,
            big_blind=20,
        )
        e.start_new_hand()
        pid = e.seats[e.action_on_idx].player_id
        e.process_action(pid, "fold")
        return e.to_dict()

    async def test_pause(self):
        self.load_game.return_value = _make_game_data(creator_id="p1")
        self.load_player.return_value = _make_player_data("p1", "Alice", "1234", is_creator=True)
        self.load_engine.return_value = self._engine_between_hands()

        result = await toggle_pause("ABC123", "p1", "1234")
        self.store_engine.assert_awaited_once()

    async def test_pause_non_creator(self):
        self.load_game.return_value = _make_game_data(creator_id="p1")
        with pytest.raises(ValueError, match="Only the creator"):
            await toggle_pause("ABC123", "p2", "5678")


# ---------------------------------------------------------------------------
# set_player_connected
# ---------------------------------------------------------------------------


class TestSetPlayerConnected:
    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        with patch(f"{PATCH_BASE}.load_player", new_callable=AsyncMock) as m1, \
             patch(f"{PATCH_BASE}.store_player", new_callable=AsyncMock) as m2:
            self.load_player = m1
            self.store_player = m2
            yield

    async def test_set_connected(self):
        player = _make_player_data("p1", "Alice", "1234")
        self.load_player.return_value = player

        await set_player_connected("ABC123", "p1", True)
        self.store_player.assert_awaited_once()
        # The stored data should have connected=True
        args = self.store_player.call_args
        assert args[0][2]["connected"] is True

    async def test_set_connected_when_not_found(self):
        self.load_player.return_value = None
        await set_player_connected("ABC123", "p1", True)
        self.store_player.assert_not_awaited()


# ---------------------------------------------------------------------------
# leave_game
# ---------------------------------------------------------------------------


class TestLeaveGame:
    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        with patch(f"{PATCH_BASE}.load_game", new_callable=AsyncMock) as m1, \
             patch(f"{PATCH_BASE}.load_player", new_callable=AsyncMock) as m2, \
             patch(f"{PATCH_BASE}.remove_player", new_callable=AsyncMock) as m3, \
             patch(f"{PATCH_BASE}.load_all_players", new_callable=AsyncMock) as m4:
            self.load_game = m1
            self.load_player = m2
            self.remove_player = m3
            self.load_all_players = m4
            yield

    async def test_leave_game_success(self):
        self.load_game.return_value = _make_game_data(creator_id="p1")
        self.load_player.return_value = _make_player_data("p2", "Bob", "5678")
        self.load_all_players.return_value = [
            _make_player_data("p1", "Alice", "1234", is_creator=True),
        ]

        state = await leave_game("ABC123", "p2", "5678")
        self.remove_player.assert_awaited_once_with("ABC123", "p2")

    async def test_leave_game_not_found(self):
        self.load_game.return_value = None
        with pytest.raises(ValueError, match="Game not found"):
            await leave_game("ABC123", "p2", "5678")

    async def test_leave_game_active(self):
        self.load_game.return_value = _make_game_data(status="active")
        with pytest.raises(ValueError, match="Cannot leave"):
            await leave_game("ABC123", "p2", "5678")

    async def test_leave_game_creator_blocked(self):
        self.load_game.return_value = _make_game_data(creator_id="p1")
        self.load_player.return_value = _make_player_data("p1", "Alice", "1234", is_creator=True)
        with pytest.raises(ValueError, match="creator cannot leave"):
            await leave_game("ABC123", "p1", "1234")

    async def test_leave_game_wrong_pin(self):
        self.load_game.return_value = _make_game_data(creator_id="p1")
        self.load_player.return_value = _make_player_data("p2", "Bob", "5678")
        with pytest.raises(ValueError, match="Invalid PIN"):
            await leave_game("ABC123", "p2", "0000")
