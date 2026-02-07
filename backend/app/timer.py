"""Action timer — background task that auto-folds players who exceed their turn timeout."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING

from app import redis_client
from app.engine import GameEngine

if TYPE_CHECKING:
    from app.ws_manager import ConnectionManager

logger = logging.getLogger(__name__)

# How often the timer loop checks for expired deadlines (seconds)
TICK_INTERVAL = 1.0


class ActionTimer:
    """Manages per-game action timers using a single asyncio background loop."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        # game_code -> deadline (Unix timestamp)
        self._deadlines: dict[str, float] = {}
        self._manager: ConnectionManager | None = None

    def set_manager(self, manager: "ConnectionManager") -> None:
        """Inject the WebSocket connection manager (avoids circular import)."""
        self._manager = manager

    def start(self) -> None:
        """Start the background timer loop."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("Action timer started")

    def stop(self) -> None:
        """Stop the background timer loop."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Action timer stopped")

    def set_deadline(self, code: str, deadline: float | None) -> None:
        """Register (or clear) the action deadline for a game."""
        if deadline is None or deadline <= 0:
            self._deadlines.pop(code, None)
        else:
            self._deadlines[code] = deadline

    def clear(self, code: str) -> None:
        self._deadlines.pop(code, None)

    async def _loop(self) -> None:
        """Main timer loop — checks all tracked deadlines each tick."""
        try:
            while True:
                await asyncio.sleep(TICK_INTERVAL)
                now = time.time()

                # Snapshot keys to avoid mutation during iteration
                expired = [
                    (code, dl)
                    for code, dl in list(self._deadlines.items())
                    if now >= dl
                ]

                for code, _dl in expired:
                    self._deadlines.pop(code, None)
                    try:
                        await self._handle_timeout(code)
                    except Exception:
                        logger.exception("Timer error for game %s", code)
        except asyncio.CancelledError:
            pass

    async def _handle_timeout(self, code: str) -> None:
        """Auto-fold the current player whose turn expired."""
        engine_data = await redis_client.load_engine(code)
        if engine_data is None:
            return

        engine = GameEngine.from_dict(engine_data)

        if not engine.hand_active:
            return

        # Verify deadline still matches (another action may have already happened)
        if engine.action_deadline is None:
            return
        if time.time() < engine.action_deadline:
            # Deadline was reset (player acted in time) — re-register
            self._deadlines[code] = engine.action_deadline
            return

        # Find the player who timed out
        action_player = engine.seats[engine.action_on_idx]
        if not action_player.is_active:
            return

        logger.info(
            "Auto-fold: game=%s player=%s (%s) timed out",
            code,
            action_player.player_id,
            action_player.name,
        )

        # Determine auto-action: check if possible, otherwise fold
        to_call = engine.current_bet - action_player.bet_this_round
        if to_call == 0:
            # Can check — auto-check is friendlier
            engine.process_action(action_player.player_id, "check")
        else:
            engine.process_action(action_player.player_id, "fold")

        await redis_client.store_engine(code, engine.to_dict())

        # Register next deadline if hand is still active
        if engine.hand_active and engine.action_deadline:
            self._deadlines[code] = engine.action_deadline

        # Broadcast updated state to all players
        await self._broadcast_engine_state(code, engine)

    async def _broadcast_engine_state(self, code: str, engine: GameEngine) -> None:
        """Send per-player views after auto-action."""
        if self._manager is None:
            return

        connected_ids = self._manager.get_connected_player_ids(code)
        for pid in connected_ids:
            try:
                view = engine.get_player_view(pid)
                msg = json.dumps({"type": "game_state", "data": view})
                await self._manager.send_to_player(code, pid, msg)
            except Exception:
                pass

        # Spectators
        spectator_count = self._manager.get_spectator_count(code)
        if spectator_count > 0:
            try:
                spec_view = engine.get_player_view("__spectator__")
                spec_msg = json.dumps({"type": "game_state", "data": spec_view})
                for conn in list(self._manager._spectators.get(code, [])):
                    await conn.send(spec_msg)
            except Exception:
                pass


# Singleton
action_timer = ActionTimer()
