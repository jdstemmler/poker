"""FastAPI application — REST + WebSocket endpoints for poker."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import game_manager, redis_client
from app.models import (
    CreateGameRequest,
    CreateGameResponse,
    ErrorResponse,
    JoinGameRequest,
    JoinGameResponse,
    ReadyRequest,
    StartGameRequest,
)
from app.ws_manager import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await redis_client.close()


app = FastAPI(title="Poker Game API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- REST endpoints ----------


@app.post("/api/games", response_model=CreateGameResponse)
async def create_game(req: CreateGameRequest):
    code, player_id, state = await game_manager.create_game(req)
    return CreateGameResponse(code=code, player_id=player_id, game=state)


@app.post("/api/games/{code}/join", response_model=JoinGameResponse)
async def join_game(code: str, req: JoinGameRequest):
    try:
        player_id, state = await game_manager.join_game(code.upper(), req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JoinGameResponse(player_id=player_id, game=state)


@app.get("/api/games/{code}")
async def get_game(code: str):
    state = await game_manager.get_game_state(code.upper())
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return state


@app.post("/api/games/{code}/ready")
async def toggle_ready(code: str, req: ReadyRequest):
    try:
        state = await game_manager.toggle_ready(code.upper(), req.player_id, req.pin)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Broadcast updated state to all WebSocket clients
    await _broadcast(code.upper(), state)
    return state


@app.post("/api/games/{code}/start")
async def start_game(code: str, req: StartGameRequest):
    try:
        state = await game_manager.start_game(code.upper(), req.player_id, req.pin)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Broadcast lobby state update, then send engine state to each player
    await _broadcast(code.upper(), state)
    await _broadcast_engine_state(code.upper())
    return state


# ---------- Game Engine Endpoints (Phase 2) ----------


class GameActionRequest(BaseModel):
    player_id: str
    pin: str = Field(..., pattern=r"^\d{4}$")
    action: str  # fold, check, call, raise, all_in
    amount: int = 0


class DealHandRequest(BaseModel):
    player_id: str
    pin: str = Field(..., pattern=r"^\d{4}$")


class RebuyRequest(BaseModel):
    player_id: str
    pin: str = Field(..., pattern=r"^\d{4}$")


@app.get("/api/games/{code}/state/{player_id}")
async def get_engine_state(code: str, player_id: str):
    """Get the game engine state for a specific player (their view)."""
    try:
        return await game_manager.get_engine_state(code.upper(), player_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/games/{code}/action")
async def game_action(code: str, req: GameActionRequest):
    """Process a player's game action (fold, check, call, raise, all_in)."""
    try:
        result = await game_manager.process_action(
            code.upper(), req.player_id, req.pin, req.action, req.amount
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Broadcast per-player views via WebSocket
    await _broadcast_engine_state(code.upper())
    return {"ok": True}


@app.post("/api/games/{code}/deal")
async def deal_next_hand(code: str, req: DealHandRequest):
    """Deal the next hand (creator only)."""
    try:
        result = await game_manager.deal_next_hand(
            code.upper(), req.player_id, req.pin
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await _broadcast_engine_state(code.upper())
    return {"ok": True}


@app.post("/api/games/{code}/rebuy")
async def rebuy(code: str, req: RebuyRequest):
    """Request a rebuy."""
    try:
        result = await game_manager.request_rebuy(
            code.upper(), req.player_id, req.pin
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await _broadcast_engine_state(code.upper())
    return {"ok": True}


# ---------- WebSocket ----------


@app.websocket("/ws/{code}/{player_id}")
async def websocket_endpoint(ws: WebSocket, code: str, player_id: str):
    code = code.upper()

    # Validate game and player exist
    state = await game_manager.get_game_state(code)
    if state is None:
        await ws.close(code=4004, reason="Game not found")
        return

    player_ids = {p.id for p in state.players}
    if player_id not in player_ids:
        await ws.close(code=4003, reason="Player not in game")
        return

    await manager.connect(code, player_id, ws)
    await game_manager.set_player_connected(code, player_id, True)

    # Broadcast updated state (player now connected)
    state = await game_manager.get_game_state(code)
    if state:
        await _broadcast(code, state)

    try:
        while True:
            # Keep connection alive; lobby doesn't need client→server messages
            # but we consume them to detect disconnects
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(code, player_id)
        await game_manager.set_player_connected(code, player_id, False)
        state = await game_manager.get_game_state(code)
        if state:
            await _broadcast(code, state)


# ---------- Helpers ----------


async def _broadcast(code: str, state):
    """Broadcast lobby state to all connected clients."""
    await manager.broadcast_game_state(code, state.model_dump_json())


async def _broadcast_engine_state(code: str) -> None:
    """Send per-player game engine view to each connected WebSocket client."""
    connected_ids = manager.get_connected_player_ids(code)
    for pid in connected_ids:
        try:
            view = await game_manager.get_engine_state(code, pid)
            msg = json.dumps({"type": "game_state", "data": view})
            await manager.send_to_player(code, pid, msg)
        except Exception:
            pass  # player may have disconnected
