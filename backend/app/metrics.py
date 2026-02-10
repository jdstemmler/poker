"""Admin metrics — Redis-backed tracking of game lifecycle events.

Stores game creation and cleanup events in Redis sorted sets (scored by
timestamp) so the admin dashboard can show historical trends without
needing an external database.  Entries older than METRICS_RETENTION_DAYS
are pruned during cleanup cycles.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app import redis_client

METRICS_CREATED_KEY = "metrics:game_created"
METRICS_CLEANED_KEY = "metrics:game_cleaned"
METRICS_RETENTION_DAYS = 90


# ------------------------------------------------------------------
# Recording
# ------------------------------------------------------------------


async def record_game_created(code: str, ip: str) -> None:
    """Record that a new game was created."""
    r = await redis_client.get_redis()
    now = time.time()
    entry = json.dumps({"code": code, "ip": ip, "created_at": now})
    await r.zadd(METRICS_CREATED_KEY, {entry: now})


async def record_game_cleaned(
    code: str,
    final_status: str,
    was_completed: bool,
    player_count: int,
) -> None:
    """Record that a game was cleaned up / deleted."""
    r = await redis_client.get_redis()
    now = time.time()
    entry = json.dumps(
        {
            "code": code,
            "cleaned_at": now,
            "final_status": final_status,
            "was_completed": was_completed,
            "player_count": player_count,
        }
    )
    await r.zadd(METRICS_CLEANED_KEY, {entry: now})


async def prune_old_metrics() -> None:
    """Remove metric entries older than METRICS_RETENTION_DAYS."""
    r = await redis_client.get_redis()
    cutoff = time.time() - (METRICS_RETENTION_DAYS * 86400)
    await r.zremrangebyscore(METRICS_CREATED_KEY, "-inf", cutoff)
    await r.zremrangebyscore(METRICS_CLEANED_KEY, "-inf", cutoff)


# ------------------------------------------------------------------
# Queries
# ------------------------------------------------------------------


async def get_summary() -> dict[str, Any]:
    """Summary view: created/cleaned in 24 h, active game count."""
    r = await redis_client.get_redis()
    since_24h = time.time() - 86400

    created_24h = await r.zcount(METRICS_CREATED_KEY, since_24h, "+inf")
    cleaned_24h = await r.zcount(METRICS_CLEANED_KEY, since_24h, "+inf")

    # Active games = game keys currently in Redis
    codes = await redis_client.list_all_game_codes()
    active_count = 0
    for code in codes:
        game_data = await redis_client.load_game(code)
        if game_data is not None:
            active_count += 1

    return {
        "games_created_24h": created_24h,
        "games_cleaned_24h": cleaned_24h,
        "active_games_count": active_count,
    }


async def get_daily_stats(days: int = 30) -> dict[str, Any]:
    """Daily creation counts + completion/abandonment breakdown."""
    r = await redis_client.get_redis()
    now = time.time()
    since = now - (days * 86400)

    # --- created entries ---
    created_raw = await r.zrangebyscore(METRICS_CREATED_KEY, since, "+inf")
    created_entries = [json.loads(e) for e in created_raw]

    # --- cleaned entries ---
    cleaned_raw = await r.zrangebyscore(METRICS_CLEANED_KEY, since, "+inf")
    cleaned_entries = [json.loads(e) for e in cleaned_raw]

    # Build a date → count map for every day in the window
    daily: dict[str, int] = {}
    for i in range(days):
        d = datetime.now(timezone.utc) - timedelta(days=days - 1 - i)
        daily[d.strftime("%Y-%m-%d")] = 0

    for entry in created_entries:
        dt = datetime.fromtimestamp(entry["created_at"], tz=timezone.utc)
        key = dt.strftime("%Y-%m-%d")
        if key in daily:
            daily[key] += 1

    daily_creation = [{"date": k, "count": v} for k, v in daily.items()]

    # Completion breakdown
    completed = 0
    abandoned = 0
    never_started = 0
    for entry in cleaned_entries:
        if entry.get("final_status") == "lobby":
            never_started += 1
        elif entry.get("was_completed"):
            completed += 1
        else:
            abandoned += 1

    return {
        "daily_creation": daily_creation,
        "completion_stats": {
            "completed": completed,
            "abandoned": abandoned,
            "never_started": never_started,
            "total_cleaned": completed + abandoned + never_started,
        },
    }


async def get_active_games_detail() -> list[dict[str, Any]]:
    """Detailed info about every game currently in Redis.

    Deliberately excludes all card data — this is an admin monitoring
    view, not a gameplay view.
    """
    codes = await redis_client.list_all_game_codes()
    games: list[dict[str, Any]] = []
    now = time.time()

    for code in codes:
        game_data = await redis_client.load_game(code)
        if game_data is None:
            continue

        players = await redis_client.load_all_players(code)
        last_activity = await redis_client.get_last_activity(code)

        games.append(
            {
                "code": code,
                "status": game_data.get("status", "unknown"),
                "creator_ip": game_data.get("creator_ip", "unknown"),
                "created_at": game_data.get("created_at"),
                "player_count": len(players),
                "player_names": [p.get("name", "?") for p in players],
                "last_activity": last_activity,
                "seconds_since_activity": (
                    round(now - last_activity, 1) if last_activity else None
                ),
            }
        )

    # Most-recently-active first
    games.sort(key=lambda g: g.get("last_activity") or 0, reverse=True)
    return games
