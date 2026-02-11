"""Tests for FastAPI REST endpoints with mocked game_manager."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch, MagicMock

# Disable rate limiting before importing the app module
os.environ.setdefault("RATE_LIMIT_ENABLED", "0")

import pytest
from httpx import ASGITransport, AsyncClient

from app.models import GameState, GameStatus, GameSettings, PlayerInfo

# We need to patch the lifespan so it doesn't start background tasks or Redis
import contextlib


@contextlib.asynccontextmanager
async def _noop_lifespan(app):
    yield


# Patch lifespan BEFORE importing app
with patch("app.main.lifespan", _noop_lifespan):
    from app.main import app as fastapi_app


PATCH_GM = "app.main.game_manager"


def _sample_game_state(code="ABC123") -> GameState:
    return GameState(
        code=code,
        status=GameStatus.LOBBY,
        settings=GameSettings(
            starting_chips=1000,
            small_blind=10,
            big_blind=20,
            max_players=9,
            allow_rebuys=True,
            max_rebuys=1,
            rebuy_cutoff_minutes=60,
            turn_timeout=0,
            blind_level_duration=0,
        ),
        players=[
            PlayerInfo(id="p1", name="Alice", ready=True, connected=False, is_creator=True),
        ],
        creator_id="p1",
    )


def _active_game_state(code="ABC123") -> GameState:
    gs = _sample_game_state(code)
    gs.status = GameStatus.ACTIVE
    gs.players.append(
        PlayerInfo(id="p2", name="Bob", ready=True, connected=False, is_creator=False),
    )
    return gs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreateGameEndpoint:
    @pytest.fixture(autouse=True)
    def _mock(self):
        with patch(f"{PATCH_GM}.create_game", new_callable=AsyncMock) as m:
            self.create_game = m
            yield

    async def test_create_game_success(self):
        state = _sample_game_state()
        self.create_game.return_value = ("ABC123", "p1", state)

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/games",
                json={"creator_name": "Alice", "creator_pin": "1234"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == "ABC123"
        assert body["player_id"] == "p1"
        assert body["game"]["status"] == "lobby"

    async def test_create_game_validation_error(self):
        """Missing required fields should return 422."""
        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/games", json={})
        assert resp.status_code == 422


class TestJoinGameEndpoint:
    @pytest.fixture(autouse=True)
    def _mock(self):
        with patch(f"{PATCH_GM}.join_game", new_callable=AsyncMock) as m1, \
             patch("app.main._broadcast", new_callable=AsyncMock) as m2:
            self.join_game = m1
            self.broadcast = m2
            yield

    async def test_join_game_success(self):
        state = _sample_game_state()
        self.join_game.return_value = ("p2", state)

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/games/abc123/join",
                json={"player_name": "Bob", "player_pin": "5678"},
            )

        assert resp.status_code == 200
        assert resp.json()["player_id"] == "p2"

    async def test_join_game_not_found(self):
        self.join_game.side_effect = ValueError("Game not found")

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/games/NOPE/join",
                json={"player_name": "Bob", "player_pin": "5678"},
            )

        assert resp.status_code == 400
        assert "Game not found" in resp.json()["detail"]


class TestGetGameEndpoint:
    @pytest.fixture(autouse=True)
    def _mock(self):
        with patch(f"{PATCH_GM}.get_game_state", new_callable=AsyncMock) as m:
            self.get_game_state = m
            yield

    async def test_get_game_success(self):
        self.get_game_state.return_value = _sample_game_state()

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/games/ABC123")

        assert resp.status_code == 200
        assert resp.json()["code"] == "ABC123"

    async def test_get_game_not_found(self):
        self.get_game_state.return_value = None

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/games/NOPE")

        assert resp.status_code == 404


class TestReadyEndpoint:
    @pytest.fixture(autouse=True)
    def _mock(self):
        with patch(f"{PATCH_GM}.toggle_ready", new_callable=AsyncMock) as m1, \
             patch("app.main._broadcast", new_callable=AsyncMock) as m2:
            self.toggle_ready = m1
            self.broadcast = m2
            yield

    async def test_toggle_ready(self):
        self.toggle_ready.return_value = _sample_game_state()

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/games/ABC123/ready",
                json={"player_id": "p1", "pin": "1234"},
            )

        assert resp.status_code == 200

    async def test_toggle_ready_error(self):
        self.toggle_ready.side_effect = ValueError("Game is not in lobby state")

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/games/ABC123/ready",
                json={"player_id": "p1", "pin": "1234"},
            )

        assert resp.status_code == 400


class TestStartGameEndpoint:
    @pytest.fixture(autouse=True)
    def _mock(self):
        with patch(f"{PATCH_GM}.start_game", new_callable=AsyncMock) as m1, \
             patch("app.main._broadcast", new_callable=AsyncMock) as m2, \
             patch("app.main._broadcast_engine_state", new_callable=AsyncMock) as m3, \
             patch("app.main._sync_timer", new_callable=AsyncMock) as m4:
            self.start_game = m1
            yield

    async def test_start_game_success(self):
        self.start_game.return_value = _active_game_state()

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/games/ABC123/start",
                json={"player_id": "p1", "pin": "1234"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "active"


class TestLeaveGameEndpoint:
    @pytest.fixture(autouse=True)
    def _mock(self):
        with patch(f"{PATCH_GM}.leave_game", new_callable=AsyncMock) as m1, \
             patch("app.main._broadcast", new_callable=AsyncMock) as m2:
            self.leave_game = m1
            self.broadcast = m2
            yield

    async def test_leave_game_success(self):
        self.leave_game.return_value = _sample_game_state()

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/games/ABC123/leave",
                json={"player_id": "p2", "pin": "5678"},
            )

        assert resp.status_code == 200
        self.broadcast.assert_called_once()

    async def test_leave_game_error(self):
        self.leave_game.side_effect = ValueError("The game creator cannot leave the lobby")

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/games/ABC123/leave",
                json={"player_id": "p1", "pin": "1234"},
            )

        assert resp.status_code == 400
        assert "creator" in resp.json()["detail"]


class TestActionEndpoint:
    @pytest.fixture(autouse=True)
    def _mock(self):
        with patch(f"{PATCH_GM}.process_action", new_callable=AsyncMock) as m1, \
             patch("app.main._broadcast_engine_state", new_callable=AsyncMock) as m2, \
             patch("app.main._sync_timer", new_callable=AsyncMock) as m3:
            self.process_action = m1
            yield

    async def test_fold(self):
        self.process_action.return_value = {"hand_active": False}

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/games/ABC123/action",
                json={
                    "player_id": "p1",
                    "pin": "1234",
                    "action": "fold",
                    "amount": 0,
                },
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    async def test_action_error(self):
        self.process_action.side_effect = ValueError("Not your turn")

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/games/ABC123/action",
                json={
                    "player_id": "p1",
                    "pin": "1234",
                    "action": "fold",
                    "amount": 0,
                },
            )

        assert resp.status_code == 400


class TestDealEndpoint:
    @pytest.fixture(autouse=True)
    def _mock(self):
        with patch(f"{PATCH_GM}.deal_next_hand", new_callable=AsyncMock) as m1, \
             patch("app.main._broadcast_engine_state", new_callable=AsyncMock) as m2, \
             patch("app.main._sync_timer", new_callable=AsyncMock) as m3:
            self.deal_next_hand = m1
            yield

    async def test_deal_success(self):
        self.deal_next_hand.return_value = {"hand_number": 2}

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/games/ABC123/deal",
                json={"player_id": "p1", "pin": "1234"},
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestRebuyEndpoint:
    @pytest.fixture(autouse=True)
    def _mock(self):
        with patch(f"{PATCH_GM}.request_rebuy", new_callable=AsyncMock) as m1, \
             patch("app.main._broadcast_engine_state", new_callable=AsyncMock) as m2:
            self.request_rebuy = m1
            yield

    async def test_rebuy_success(self):
        self.request_rebuy.return_value = {"chips": 1000}

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/games/ABC123/rebuy",
                json={"player_id": "p1", "pin": "1234"},
            )

        assert resp.status_code == 200


class TestShowCardsEndpoint:
    @pytest.fixture(autouse=True)
    def _mock(self):
        with patch(f"{PATCH_GM}.show_cards", new_callable=AsyncMock) as m1, \
             patch("app.main._broadcast_engine_state", new_callable=AsyncMock) as m2:
            self.show_cards = m1
            yield

    async def test_show_cards_success(self):
        self.show_cards.return_value = {"shown_cards": {"p1": [{"rank": 14, "suit": "s"}]}}

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/games/ABC123/show_cards",
                json={"player_id": "p1", "pin": "1234"},
            )

        assert resp.status_code == 200


class TestPauseEndpoint:
    @pytest.fixture(autouse=True)
    def _mock(self):
        with patch(f"{PATCH_GM}.toggle_pause", new_callable=AsyncMock) as m1, \
             patch("app.main._broadcast_engine_state", new_callable=AsyncMock) as m2, \
             patch("app.main._sync_timer", new_callable=AsyncMock) as m3:
            self.toggle_pause = m1
            yield

    async def test_pause_success(self):
        self.toggle_pause.return_value = {"paused": True}

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/games/ABC123/pause",
                json={"player_id": "p1", "pin": "1234"},
            )

        assert resp.status_code == 200

    async def test_pause_error(self):
        self.toggle_pause.side_effect = ValueError("Only the creator")

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/games/ABC123/pause",
                json={"player_id": "p1", "pin": "1234"},
            )

        assert resp.status_code == 400


class TestGetEngineStateEndpoint:
    @pytest.fixture(autouse=True)
    def _mock(self):
        with patch(f"{PATCH_GM}.get_engine_state", new_callable=AsyncMock) as m:
            self.get_engine_state = m
            yield

    async def test_get_engine_state(self):
        self.get_engine_state.return_value = {"hand_number": 1, "street": "preflop"}

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/games/ABC123/state/p1")

        assert resp.status_code == 200
        assert resp.json()["hand_number"] == 1

    async def test_get_engine_state_error(self):
        self.get_engine_state.side_effect = ValueError("Game engine not found")

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/games/ABC123/state/p1")

        assert resp.status_code == 400
