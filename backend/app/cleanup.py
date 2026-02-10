"""Stale game cleanup — background task that removes abandoned games from Redis.

A game is considered stale when:
  1. No activity (actions, deals, joins) for STALE_THRESHOLD seconds (default 24 h).
  2. The game has NOT been conclusively won (only one player with chips remaining).

Games that were legitimately completed (a single winner) are preserved so players
can review results.  They will be cleaned up after COMPLETED_THRESHOLD (default 72 h).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app import redis_client
from app import metrics
from app.engine import GameEngine

logger = logging.getLogger(__name__)

# How often the cleanup loop runs (seconds).  Default: every 30 minutes.
CLEANUP_INTERVAL: float = 30 * 60

# Inactivity threshold before an *incomplete* game is deleted (seconds).
STALE_THRESHOLD: float = 24 * 60 * 60  # 24 hours

# Inactivity threshold before a *completed* (won) game is deleted (seconds).
COMPLETED_THRESHOLD: float = 72 * 60 * 60  # 72 hours


def _is_game_won(engine_data: dict[str, Any] | None) -> bool:
    """Return True if the game has a single winner (only one player with chips)."""
    if engine_data is None:
        return False

    seats = engine_data.get("seats", [])
    players_with_chips = [
        s for s in seats if s.get("chips", 0) > 0 and not s.get("is_sitting_out")
    ]
    return len(players_with_chips) <= 1 and len(seats) >= 2


async def cleanup_stale_games() -> dict[str, list[str]]:
    """Scan all games in Redis and delete stale ones.

    Returns a dict with 'deleted' (list of codes removed) and
    'kept' (list of codes that were checked but retained).
    """
    now = time.time()
    codes = await redis_client.list_all_game_codes()
    deleted: list[str] = []
    kept: list[str] = []

    for code in codes:
        try:
            last_activity = await redis_client.get_last_activity(code)

            # If there's no last_activity timestamp at all, treat creation time as
            # unknown — use a generous fallback: mark activity now so it gets a
            # full window before next check.
            if last_activity is None:
                await redis_client.touch_activity(code)
                kept.append(code)
                continue

            age = now - last_activity

            engine_data = await redis_client.load_engine(code)
            won = _is_game_won(engine_data)

            threshold = COMPLETED_THRESHOLD if won else STALE_THRESHOLD

            if age >= threshold:
                # Record metric before deleting
                game_data = await redis_client.load_game(code)
                players = await redis_client.load_all_players(code)
                final_status = (
                    game_data.get("status", "unknown") if game_data else "unknown"
                )
                await metrics.record_game_cleaned(
                    code=code,
                    final_status=final_status,
                    was_completed=won,
                    player_count=len(players),
                )

                await redis_client.delete_game(code)
                logger.info(
                    "Cleaned up game %s (age=%.1fh, won=%s)",
                    code,
                    age / 3600,
                    won,
                )
                deleted.append(code)
            else:
                kept.append(code)
        except Exception:
            logger.exception("Error checking game %s for cleanup", code)
            kept.append(code)

    return {"deleted": deleted, "kept": kept}


async def _prune_metrics() -> None:
    """Prune old metrics entries (called after each cleanup pass)."""
    try:
        await metrics.prune_old_metrics()
    except Exception:
        logger.exception("Failed to prune old metrics")


class GameCleaner:
    """Background asyncio task that periodically removes stale games."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("Game cleaner started (interval=%ds)", int(CLEANUP_INTERVAL))

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Game cleaner stopped")

    async def _loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(CLEANUP_INTERVAL)
                try:
                    result = await cleanup_stale_games()
                    await _prune_metrics()
                    if result["deleted"]:
                        logger.info(
                            "Cleanup pass: deleted %d game(s): %s",
                            len(result["deleted"]),
                            ", ".join(result["deleted"]),
                        )
                    else:
                        logger.debug("Cleanup pass: nothing to delete")
                except Exception:
                    logger.exception("Cleanup pass failed")
        except asyncio.CancelledError:
            pass


# Singleton
game_cleaner = GameCleaner()
