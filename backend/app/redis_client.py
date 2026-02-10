"""Redis client wrapper for game state persistence."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_pool: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.from_url(REDIS_URL, decode_responses=True)
    return _pool


def _game_key(code: str) -> str:
    return f"game:{code}"


def _players_key(code: str) -> str:
    return f"game:{code}:players"


def _player_key(code: str, player_id: str) -> str:
    return f"game:{code}:player:{player_id}"


async def store_game(code: str, data: dict[str, Any]) -> None:
    r = await get_redis()
    await r.set(_game_key(code), json.dumps(data))


async def load_game(code: str) -> Optional[dict[str, Any]]:
    r = await get_redis()
    raw = await r.get(_game_key(code))
    if raw is None:
        return None
    return json.loads(raw)


async def store_player(code: str, player_id: str, data: dict[str, Any]) -> None:
    r = await get_redis()
    await r.set(_player_key(code, player_id), json.dumps(data))
    await r.sadd(_players_key(code), player_id)


async def load_player(code: str, player_id: str) -> Optional[dict[str, Any]]:
    r = await get_redis()
    raw = await r.get(_player_key(code, player_id))
    if raw is None:
        return None
    return json.loads(raw)


async def load_all_players(code: str) -> list[dict[str, Any]]:
    r = await get_redis()
    player_ids = await r.smembers(_players_key(code))
    players = []
    for pid in player_ids:
        data = await load_player(code, pid)
        if data:
            players.append(data)
    return players


async def remove_player(code: str, player_id: str) -> None:
    """Remove a player from a game."""
    r = await get_redis()
    await r.delete(_player_key(code, player_id))
    await r.srem(_players_key(code), player_id)


def _engine_key(code: str) -> str:
    return f"game:{code}:engine"


async def store_engine(code: str, data: dict[str, Any]) -> None:
    r = await get_redis()
    await r.set(_engine_key(code), json.dumps(data))


async def load_engine(code: str) -> Optional[dict[str, Any]]:
    r = await get_redis()
    raw = await r.get(_engine_key(code))
    if raw is None:
        return None
    return json.loads(raw)


def _activity_key(code: str) -> str:
    return f"game:{code}:last_activity"


async def touch_activity(code: str) -> None:
    """Update the last-activity timestamp for a game (Unix epoch seconds)."""
    import time

    r = await get_redis()
    await r.set(_activity_key(code), str(time.time()))


async def get_last_activity(code: str) -> float | None:
    """Return the last-activity timestamp for a game, or None."""
    r = await get_redis()
    raw = await r.get(_activity_key(code))
    if raw is None:
        return None
    return float(raw)


async def list_all_game_codes() -> list[str]:
    """Return all game codes currently stored in Redis."""
    r = await get_redis()
    codes: set[str] = set()
    async for key in r.scan_iter(match="game:*", count=200):
        # Keys look like game:ABCD12, game:ABCD12:players, etc.
        parts = key.split(":")
        if len(parts) >= 2:
            codes.add(parts[1])
    return list(codes)


async def delete_game(code: str) -> None:
    """Clean up all keys for a game."""
    r = await get_redis()
    player_ids = await r.smembers(_players_key(code))
    keys = [
        _game_key(code),
        _players_key(code),
        _engine_key(code),
        _activity_key(code),
    ]
    for pid in player_ids:
        keys.append(_player_key(code, pid))
    if keys:
        await r.delete(*keys)


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
