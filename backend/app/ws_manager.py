"""WebSocket connection manager for lobby updates."""

from __future__ import annotations

from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections per game room."""

    def __init__(self) -> None:
        # game_code -> {player_id -> WebSocket}
        self._connections: dict[str, dict[str, WebSocket]] = {}

    async def connect(self, code: str, player_id: str, ws: WebSocket) -> None:
        await ws.accept()
        if code not in self._connections:
            self._connections[code] = {}
        self._connections[code][player_id] = ws

    def disconnect(self, code: str, player_id: str) -> None:
        if code in self._connections:
            self._connections[code].pop(player_id, None)
            if not self._connections[code]:
                del self._connections[code]

    async def broadcast_game_state(self, code: str, state_json: str) -> None:
        """Send game state JSON to all connected clients in a game."""
        if code not in self._connections:
            return

        stale: list[str] = []
        for player_id, ws in self._connections[code].items():
            try:
                await ws.send_text(state_json)
            except Exception:
                stale.append(player_id)

        for pid in stale:
            self.disconnect(code, pid)

    def get_connected_player_ids(self, code: str) -> set[str]:
        if code not in self._connections:
            return set()
        return set(self._connections[code].keys())


manager = ConnectionManager()
