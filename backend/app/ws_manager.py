"""WebSocket connection manager with heartbeat, reconnection, and spectator support."""

from __future__ import annotations

import json
import logging
import time
from enum import Enum
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ClientRole(str, Enum):
    PLAYER = "player"
    SPECTATOR = "spectator"


class ClientConnection:
    """Wraps a single WebSocket connection with metadata."""

    __slots__ = ("ws", "player_id", "role", "connected_at", "last_pong")

    def __init__(self, ws: WebSocket, player_id: str, role: ClientRole) -> None:
        self.ws = ws
        self.player_id = player_id
        self.role = role
        self.connected_at = time.time()
        self.last_pong = time.time()

    async def send(self, text: str) -> bool:
        """Send text, returning False on failure."""
        try:
            await self.ws.send_text(text)
            return True
        except Exception:
            return False


class ConnectionManager:
    """Manages WebSocket connections per game room with heartbeat support."""

    # Heartbeat interval (seconds) — client should ping within this window
    HEARTBEAT_TIMEOUT = 30

    def __init__(self) -> None:
        # game_code -> {player_id -> ClientConnection}
        self._players: dict[str, dict[str, ClientConnection]] = {}
        # game_code -> [ClientConnection]  (spectators have no player_id key)
        self._spectators: dict[str, list[ClientConnection]] = {}

    # ------------------------------------------------------------------
    # Player connections
    # ------------------------------------------------------------------

    async def connect(
        self,
        code: str,
        player_id: str,
        ws: WebSocket,
        role: ClientRole = ClientRole.PLAYER,
    ) -> ClientConnection:
        await ws.accept()
        conn = ClientConnection(ws, player_id, role)

        if role == ClientRole.PLAYER:
            if code not in self._players:
                self._players[code] = {}
            # Close previous connection for this player (stale tab)
            old = self._players[code].get(player_id)
            if old is not None:
                try:
                    await old.ws.close(code=4001, reason="Replaced by new connection")
                except Exception:
                    pass
            self._players[code][player_id] = conn
        else:
            if code not in self._spectators:
                self._spectators[code] = []
            self._spectators[code].append(conn)

        logger.info("WS connect: game=%s player=%s role=%s", code, player_id, role.value)
        return conn

    def disconnect(self, code: str, player_id: str, conn: Optional[ClientConnection] = None) -> None:
        """Remove a player connection. If conn is given, only remove if it matches (avoids removing a newer connection)."""
        if code in self._players:
            existing = self._players[code].get(player_id)
            if existing is not None and (conn is None or existing is conn):
                del self._players[code][player_id]
                if not self._players[code]:
                    del self._players[code]
                logger.info("WS disconnect: game=%s player=%s", code, player_id)

    def disconnect_spectator(self, code: str, conn: ClientConnection) -> None:
        if code in self._spectators:
            try:
                self._spectators[code].remove(conn)
            except ValueError:
                pass
            if not self._spectators[code]:
                del self._spectators[code]

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    def record_pong(self, code: str, player_id: str) -> None:
        """Record that a client responded to a heartbeat."""
        conn = self._get_player_conn(code, player_id)
        if conn:
            conn.last_pong = time.time()

    def is_stale(self, conn: ClientConnection) -> bool:
        return (time.time() - conn.last_pong) > self.HEARTBEAT_TIMEOUT

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    async def broadcast_game_state(self, code: str, state_json: str) -> None:
        """Send game state JSON to all connected players + spectators."""
        stale: list[str] = []

        for player_id, conn in list(self._players.get(code, {}).items()):
            if not await conn.send(state_json):
                stale.append(player_id)

        for pid in stale:
            self.disconnect(code, pid)

        # Spectators
        dead_specs: list[ClientConnection] = []
        for conn in list(self._spectators.get(code, [])):
            if not await conn.send(state_json):
                dead_specs.append(conn)
        for c in dead_specs:
            self.disconnect_spectator(code, c)

    async def send_to_player(self, code: str, player_id: str, message: str) -> None:
        """Send a message to a specific player."""
        conn = self._get_player_conn(code, player_id)
        if conn:
            if not await conn.send(message):
                self.disconnect(code, player_id, conn)

    async def broadcast_to_all(self, code: str, message: str) -> None:
        """Send an arbitrary message to all players + spectators in a game."""
        stale: list[str] = []
        for pid, conn in list(self._players.get(code, {}).items()):
            if not await conn.send(message):
                stale.append(pid)
        for pid in stale:
            self.disconnect(code, pid)

        dead_specs: list[ClientConnection] = []
        for conn in list(self._spectators.get(code, [])):
            if not await conn.send(message):
                dead_specs.append(conn)
        for c in dead_specs:
            self.disconnect_spectator(code, c)

    async def send_ping(self, code: str) -> None:
        """Send a ping message to all connections in a game."""
        ping_msg = json.dumps({"type": "ping", "ts": time.time()})
        await self.broadcast_to_all(code, ping_msg)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_connected_player_ids(self, code: str) -> set[str]:
        if code not in self._players:
            return set()
        return set(self._players[code].keys())

    def get_spectator_count(self, code: str) -> int:
        return len(self._spectators.get(code, []))

    def get_connection_info(self, code: str) -> dict:
        """Return connection info for broadcasting to clients."""
        return {
            "type": "connection_info",
            "connected_players": list(self.get_connected_player_ids(code)),
            "spectator_count": self.get_spectator_count(code),
        }

    def _get_player_conn(self, code: str, player_id: str) -> Optional[ClientConnection]:
        return self._players.get(code, {}).get(player_id)


manager = ConnectionManager()
