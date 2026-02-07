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


async def delete_game(code: str) -> None:
    """Clean up all keys for a game (for future use)."""
    r = await get_redis()
    player_ids = await r.smembers(_players_key(code))
    keys = [_game_key(code), _players_key(code)]
    for pid in player_ids:
        keys.append(_player_key(code, pid))
    if keys:
        await r.delete(*keys)


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
