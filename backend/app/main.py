"""FastAPI application — REST + WebSocket endpoints for the poker lobby."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

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

    await _broadcast(code.upper(), state)
    return state


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
    await manager.broadcast_game_state(code, state.model_dump_json())
