"""FastAPI application — REST + WebSocket endpoints for poker."""

import hmac
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app import game_manager, metrics, redis_client
from app.models import (
    CreateGameRequest,
    CreateGameResponse,
    ErrorResponse,
    JoinGameRequest,
    JoinGameResponse,
    ReadyRequest,
    StartGameRequest,
)
from app.ws_manager import ClientRole, manager
from app.timer import action_timer
from app.cleanup import game_cleaner, cleanup_stale_games

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start action timer background task and inject WS manager
    action_timer.set_manager(manager)
    action_timer.start()
    # Start stale-game cleanup background task
    game_cleaner.start()
    yield
    game_cleaner.stop()
    action_timer.stop()
    await redis_client.close()


app = FastAPI(title="Poker Game API", lifespan=lifespan)

# ---------- Rate Limiting ----------

_rate_limit_enabled = os.getenv("RATE_LIMIT_ENABLED", "1") != "0"

limiter = Limiter(
    key_func=get_remote_address,
    enabled=_rate_limit_enabled,
)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please slow down."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Admin Auth ----------

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


async def verify_admin(authorization: str | None = Header(None)):
    """Validate the admin password from the Authorization header."""
    if not ADMIN_PASSWORD:
        raise HTTPException(
            status_code=503,
            detail="Admin not configured. Set ADMIN_PASSWORD env var.",
        )
    expected = f"Bearer {ADMIN_PASSWORD}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Invalid admin password")


# ---------- REST endpoints ----------


@app.post("/api/games", response_model=CreateGameResponse)
@limiter.limit("5/minute")
async def create_game(request: Request, req: CreateGameRequest):
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        creator_ip = forwarded.split(",")[0].strip()
    else:
        creator_ip = request.client.host if request.client else "unknown"
    code, player_id, state = await game_manager.create_game(
        req, creator_ip=creator_ip
    )
    return CreateGameResponse(code=code, player_id=player_id, game=state)


@app.post("/api/games/{code}/join", response_model=JoinGameResponse)
@limiter.limit("10/minute")
async def join_game(request: Request, code: str, req: JoinGameRequest):
    try:
        player_id, state = await game_manager.join_game(code.upper(), req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Broadcast updated lobby state so existing players see the new joiner
    await _broadcast(code.upper(), state)
    return JoinGameResponse(player_id=player_id, game=state)


@app.get("/api/games/{code}")
@limiter.limit("30/minute")
async def get_game(request: Request, code: str):
    state = await game_manager.get_game_state(code.upper())
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return state


@app.post("/api/games/{code}/ready")
@limiter.limit("10/minute")
async def toggle_ready(request: Request, code: str, req: ReadyRequest):
    try:
        state = await game_manager.toggle_ready(code.upper(), req.player_id, req.pin)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Broadcast updated state to all WebSocket clients
    await _broadcast(code.upper(), state)
    return state


class LeaveRequest(BaseModel):
    player_id: str
    pin: str = Field(..., pattern=r"^\d{4}$")


@app.post("/api/games/{code}/leave")
@limiter.limit("10/minute")
async def leave_game(request: Request, code: str, req: LeaveRequest):
    """Leave the lobby (non-creator only, before game starts)."""
    try:
        state = await game_manager.leave_game(code.upper(), req.player_id, req.pin)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await _broadcast(code.upper(), state)
    return state


@app.post("/api/games/{code}/start")
@limiter.limit("5/minute")
async def start_game(request: Request, code: str, req: StartGameRequest):
    try:
        state = await game_manager.start_game(code.upper(), req.player_id, req.pin)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Broadcast lobby state update, then send engine state to each player
    await _broadcast(code.upper(), state)
    await _broadcast_engine_state(code.upper())
    await _sync_timer(code.upper())
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
@limiter.limit("30/minute")
async def get_engine_state(request: Request, code: str, player_id: str):
    """Get the game engine state for a specific player (their view)."""
    try:
        return await game_manager.get_engine_state(code.upper(), player_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/games/{code}/action")
@limiter.limit("30/minute")
async def game_action(request: Request, code: str, req: GameActionRequest):
    """Process a player's game action (fold, check, call, raise, all_in)."""
    try:
        result = await game_manager.process_action(
            code.upper(), req.player_id, req.pin, req.action, req.amount
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Broadcast per-player views via WebSocket
    await _broadcast_engine_state(code.upper())
    await _sync_timer(code.upper())
    return {"ok": True}


@app.post("/api/games/{code}/deal")
@limiter.limit("30/minute")
async def deal_next_hand(request: Request, code: str, req: DealHandRequest):
    """Deal the next hand (any player can trigger)."""
    try:
        result = await game_manager.deal_next_hand(
            code.upper(), req.player_id, req.pin
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await _broadcast_engine_state(code.upper())
    await _sync_timer(code.upper())
    return {"ok": True}


@app.post("/api/games/{code}/rebuy")
@limiter.limit("10/minute")
async def rebuy(request: Request, code: str, req: RebuyRequest):
    """Request a rebuy."""
    try:
        result = await game_manager.request_rebuy(
            code.upper(), req.player_id, req.pin
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await _broadcast_engine_state(code.upper())
    return {"ok": True}


@app.post("/api/games/{code}/cancel_rebuy")
@limiter.limit("10/minute")
async def cancel_rebuy(request: Request, code: str, req: RebuyRequest):
    """Cancel a queued rebuy."""
    try:
        result = await game_manager.cancel_rebuy(
            code.upper(), req.player_id, req.pin
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await _broadcast_engine_state(code.upper())
    return {"ok": True}


class ShowCardsRequest(BaseModel):
    player_id: str
    pin: str = Field(..., pattern=r"^\d{4}$")


@app.post("/api/games/{code}/show_cards")
@limiter.limit("10/minute")
async def show_cards(request: Request, code: str, req: ShowCardsRequest):
    """Voluntarily reveal cards after a hand."""
    try:
        result = await game_manager.show_cards(
            code.upper(), req.player_id, req.pin
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await _broadcast_engine_state(code.upper())
    return {"ok": True}


class PauseRequest(BaseModel):
    player_id: str
    pin: str = Field(..., pattern=r"^\d{4}$")


@app.post("/api/games/{code}/pause")
@limiter.limit("10/minute")
async def toggle_pause(request: Request, code: str, req: PauseRequest):
    """Toggle pause state (creator only)."""
    try:
        result = await game_manager.toggle_pause(
            code.upper(), req.player_id, req.pin
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await _broadcast_engine_state(code.upper())
    await _sync_timer(code.upper())
    return {"ok": True}


@app.post("/api/admin/cleanup")
@limiter.limit("10/minute")
async def admin_cleanup(request: Request, _=Depends(verify_admin)):
    """Manually trigger stale-game cleanup. Returns deleted and kept game codes."""
    result = await cleanup_stale_games()
    return result


@app.get("/api/admin/summary")
@limiter.limit("10/minute")
async def admin_summary(request: Request, _=Depends(verify_admin)):
    """Summary stats: games created/cleaned in last 24 h, active count."""
    return await metrics.get_summary()


@app.get("/api/admin/daily-stats")
@limiter.limit("10/minute")
async def admin_daily_stats(request: Request, _=Depends(verify_admin)):
    """Daily creation counts + completion/abandonment breakdown (30 days)."""
    return await metrics.get_daily_stats()


@app.get("/api/admin/active-games")
@limiter.limit("10/minute")
async def admin_active_games(request: Request, _=Depends(verify_admin)):
    """Detailed list of all active games. No card data."""
    games = await metrics.get_active_games_detail()
    return {"games": games}


# ---------- WebSocket ----------


@app.websocket("/ws/{code}/{player_id}")
async def websocket_endpoint(ws: WebSocket, code: str, player_id: str):
    code = code.upper()

    # Validate game exists
    state = await game_manager.get_game_state(code)
    if state is None:
        await ws.close(code=4004, reason="Game not found")
        return

    # Determine role: player or spectator
    player_ids = {p.id for p in state.players}
    if player_id in player_ids:
        role = ClientRole.PLAYER
    else:
        role = ClientRole.SPECTATOR

    conn = await manager.connect(code, player_id, ws, role)

    if role == ClientRole.PLAYER:
        await game_manager.set_player_connected(code, player_id, True)

    # Send current state immediately on connect (reconnect support)
    try:
        # Lobby state
        fresh_state = await game_manager.get_game_state(code)
        if fresh_state:
            await conn.send(fresh_state.model_dump_json())

        # Engine state (if game is active)
        if fresh_state and fresh_state.status == "active":
            try:
                view = await game_manager.get_engine_state(code, player_id)
                await conn.send(json.dumps({"type": "game_state", "data": view}))
            except ValueError:
                pass  # engine may not exist yet

        # Broadcast connection info to all
        await _broadcast_connection_info(code)
    except Exception:
        logger.debug("Error sending initial state to %s in %s", player_id, code, exc_info=True)

    try:
        while True:
            raw = await ws.receive_text()
            # Handle client messages
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "pong":
                    manager.record_pong(code, player_id)
                # Future: could handle other client-to-server messages here
            except (json.JSONDecodeError, AttributeError):
                pass  # ignore malformed messages
    except WebSocketDisconnect:
        pass
    finally:
        if role == ClientRole.PLAYER:
            manager.disconnect(code, player_id, conn)
            await game_manager.set_player_connected(code, player_id, False)
        else:
            manager.disconnect_spectator(code, conn)

        # Broadcast updated connection info & lobby state
        try:
            fresh_state = await game_manager.get_game_state(code)
            if fresh_state:
                await _broadcast(code, fresh_state)
            await _broadcast_connection_info(code)
        except Exception:
            logger.debug("Error broadcasting disconnect for %s in %s", player_id, code, exc_info=True)


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
            logger.debug("Failed to send engine state to %s in %s", pid, code, exc_info=True)

    # Also send a spectator-safe view to spectators (no hole cards)
    try:
        # Use a dummy spectator ID to get a view with no personal cards
        spectator_count = manager.get_spectator_count(code)
        if spectator_count > 0:
            # Build a spectator view — load engine, get generic state
            engine_data = await redis_client.load_engine(code)
            if engine_data:
                from app.engine import GameEngine
                engine = GameEngine.from_dict(engine_data)
                spec_view = engine.get_player_view("__spectator__")
                spec_msg = json.dumps({"type": "game_state", "data": spec_view})
                # Send to all spectator connections
                for conn in list(manager._spectators.get(code, [])):
                    await conn.send(spec_msg)
    except Exception:
        logger.debug("Failed to send spectator state for %s", code, exc_info=True)


async def _broadcast_connection_info(code: str) -> None:
    """Send connection info (who's online) to all clients."""
    info = manager.get_connection_info(code)
    await manager.broadcast_to_all(code, json.dumps(info))


async def _sync_timer(code: str) -> None:
    """Update the action timer with the current engine's deadline."""
    try:
        engine_data = await redis_client.load_engine(code)
        if engine_data and engine_data.get("action_deadline"):
            action_timer.set_deadline(code, engine_data["action_deadline"])
        else:
            action_timer.clear(code)

        # Sync auto-deal deadline
        if engine_data and engine_data.get("auto_deal_deadline"):
            action_timer.set_auto_deal_deadline(code, engine_data["auto_deal_deadline"])
        else:
            action_timer.clear_auto_deal(code)
    except Exception:
        logger.warning("Failed to sync timer for game %s", code, exc_info=True)
