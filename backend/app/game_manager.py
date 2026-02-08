"""Game manager — business logic for lobby and gameplay operations."""

from __future__ import annotations

import hashlib
import random
import string
import uuid
from typing import Any, Optional

from app import redis_client
from app.engine import GameEngine
from app.models import (
    CreateGameRequest,
    GameSettings,
    GameState,
    GameStatus,
    JoinGameRequest,
    PlayerInfo,
)


def _generate_code(length: int = 6) -> str:
    """Generate a short uppercase game code."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def _hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


def _verify_pin(pin: str, pin_hash: str) -> bool:
    return _hash_pin(pin) == pin_hash


async def create_game(req: CreateGameRequest) -> tuple[str, str, GameState]:
    """Create a new game and return (code, player_id, game_state)."""
    code = _generate_code()

    # Ensure uniqueness (simple retry)
    while await redis_client.load_game(code) is not None:
        code = _generate_code()

    player_id = str(uuid.uuid4())

    game_data = {
        "code": code,
        "status": GameStatus.LOBBY.value,
        "creator_id": player_id,
        "settings": {
            "starting_chips": req.starting_chips,
            "small_blind": req.small_blind,
            "big_blind": req.big_blind,
            "max_players": req.max_players,
            "allow_rebuys": req.allow_rebuys,
            "turn_timeout": req.turn_timeout,
        },
    }

    player_data = {
        "id": player_id,
        "name": req.creator_name,
        "pin_hash": _hash_pin(req.creator_pin),
        "ready": False,
        "connected": False,
        "is_creator": True,
    }

    await redis_client.store_game(code, game_data)
    await redis_client.store_player(code, player_id, player_data)

    state = await _build_game_state(code, game_data)
    return code, player_id, state


async def join_game(code: str, req: JoinGameRequest) -> tuple[str, GameState]:
    """Join an existing game. Returns (player_id, game_state)."""
    game_data = await redis_client.load_game(code)
    if game_data is None:
        raise ValueError("Game not found")

    if game_data["status"] != GameStatus.LOBBY.value:
        raise ValueError("Game is not in lobby state")

    players = await redis_client.load_all_players(code)

    # Check if player name already taken
    for p in players:
        if p["name"].lower() == req.player_name.lower():
            # Allow reconnect if PIN matches
            if _verify_pin(req.player_pin, p["pin_hash"]):
                state = await _build_game_state(code, game_data)
                return p["id"], state
            else:
                raise ValueError("Name already taken (wrong PIN)")

    if len(players) >= game_data["settings"]["max_players"]:
        raise ValueError("Game is full")

    player_id = str(uuid.uuid4())

    player_data = {
        "id": player_id,
        "name": req.player_name,
        "pin_hash": _hash_pin(req.player_pin),
        "ready": False,
        "connected": False,
        "is_creator": False,
    }

    await redis_client.store_player(code, player_id, player_data)

    state = await _build_game_state(code, game_data)
    return player_id, state


async def toggle_ready(code: str, player_id: str, pin: str) -> GameState:
    """Toggle a player's ready status."""
    game_data = await redis_client.load_game(code)
    if game_data is None:
        raise ValueError("Game not found")
    if game_data["status"] != GameStatus.LOBBY.value:
        raise ValueError("Game is not in lobby state")

    player_data = await redis_client.load_player(code, player_id)
    if player_data is None:
        raise ValueError("Player not found")
    if not _verify_pin(pin, player_data["pin_hash"]):
        raise ValueError("Invalid PIN")

    player_data["ready"] = not player_data["ready"]
    await redis_client.store_player(code, player_id, player_data)

    return await _build_game_state(code, game_data)


async def start_game(code: str, player_id: str, pin: str) -> GameState:
    """Start the game (creator only, all must be ready, min 2 players)."""
    game_data = await redis_client.load_game(code)
    if game_data is None:
        raise ValueError("Game not found")
    if game_data["status"] != GameStatus.LOBBY.value:
        raise ValueError("Game is not in lobby state")
    if game_data["creator_id"] != player_id:
        raise ValueError("Only the creator can start the game")

    player_data = await redis_client.load_player(code, player_id)
    if player_data is None:
        raise ValueError("Player not found")
    if not _verify_pin(pin, player_data["pin_hash"]):
        raise ValueError("Invalid PIN")

    players = await redis_client.load_all_players(code)
    if len(players) < 2:
        raise ValueError("Need at least 2 players to start")

    not_ready = [p["name"] for p in players if not p["ready"]]
    if not_ready:
        raise ValueError(f"Players not ready: {', '.join(not_ready)}")

    game_data["status"] = GameStatus.ACTIVE.value
    await redis_client.store_game(code, game_data)

    # Create and persist the game engine
    engine = GameEngine(
        game_code=code,
        players=[{"id": p["id"], "name": p["name"]} for p in players],
        starting_chips=game_data["settings"]["starting_chips"],
        small_blind=game_data["settings"]["small_blind"],
        big_blind=game_data["settings"]["big_blind"],
        allow_rebuys=game_data["settings"]["allow_rebuys"],
        turn_timeout=game_data["settings"].get("turn_timeout", 0),
    )
    engine_state = engine.start_new_hand()
    await redis_client.store_engine(code, engine.to_dict())

    return await _build_game_state(code, game_data)


async def get_game_state(code: str) -> Optional[GameState]:
    """Get the current game state."""
    game_data = await redis_client.load_game(code)
    if game_data is None:
        return None
    return await _build_game_state(code, game_data)


async def set_player_connected(code: str, player_id: str, connected: bool) -> None:
    """Update player connected status."""
    player_data = await redis_client.load_player(code, player_id)
    if player_data:
        player_data["connected"] = connected
        await redis_client.store_player(code, player_id, player_data)


async def _build_game_state(
    code: str, game_data: dict
) -> GameState:
    """Construct a GameState from Redis data."""
    players_data = await redis_client.load_all_players(code)

    players = [
        PlayerInfo(
            id=p["id"],
            name=p["name"],
            ready=p["ready"],
            connected=p["connected"],
            is_creator=p.get("is_creator", False),
        )
        for p in players_data
    ]

    return GameState(
        code=code,
        status=GameStatus(game_data["status"]),
        settings=GameSettings(**game_data["settings"]),
        players=players,
        creator_id=game_data["creator_id"],
    )


# ------------------------------------------------------------------
# Engine Operations (Phase 2)
# ------------------------------------------------------------------


async def _load_engine(code: str) -> GameEngine:
    """Load game engine from Redis."""
    engine_data = await redis_client.load_engine(code)
    if engine_data is None:
        raise ValueError("Game engine not found")
    return GameEngine.from_dict(engine_data)


async def _save_engine(code: str, engine: GameEngine) -> None:
    """Persist game engine to Redis."""
    await redis_client.store_engine(code, engine.to_dict())


async def verify_player(code: str, player_id: str, pin: str) -> None:
    """Verify a player's PIN for authenticated actions."""
    player_data = await redis_client.load_player(code, player_id)
    if player_data is None:
        raise ValueError("Player not found")
    if not _verify_pin(pin, player_data["pin_hash"]):
        raise ValueError("Invalid PIN")


async def get_engine_state(code: str, player_id: str) -> dict[str, Any]:
    """Get the game engine state for a specific player."""
    engine = await _load_engine(code)
    return engine.get_player_view(player_id)


async def process_action(
    code: str, player_id: str, pin: str, action: str, amount: int = 0
) -> dict[str, Any]:
    """Process a player's game action."""
    await verify_player(code, player_id, pin)

    engine = await _load_engine(code)
    result = engine.process_action(player_id, action, amount)
    await _save_engine(code, engine)

    return result


async def deal_next_hand(code: str, player_id: str, pin: str) -> dict[str, Any]:
    """Deal the next hand (creator only, after previous hand ended)."""
    game_data = await redis_client.load_game(code)
    if game_data is None:
        raise ValueError("Game not found")
    if game_data["creator_id"] != player_id:
        raise ValueError("Only the creator can deal the next hand")

    await verify_player(code, player_id, pin)

    engine = await _load_engine(code)
    if engine.hand_active:
        raise ValueError("Current hand is still in progress")

    result = engine.start_new_hand()
    await _save_engine(code, engine)

    return result


async def request_rebuy(code: str, player_id: str, pin: str) -> dict[str, Any]:
    """Handle a rebuy request."""
    await verify_player(code, player_id, pin)

    engine = await _load_engine(code)
    result = engine.rebuy(player_id)
    await _save_engine(code, engine)

    return result


async def show_cards(code: str, player_id: str, pin: str) -> dict[str, Any]:
    """Allow a player to voluntarily show their cards after a hand."""
    await verify_player(code, player_id, pin)

    engine = await _load_engine(code)
    result = engine.show_cards(player_id)
    await _save_engine(code, engine)

    return result
