# Backend — Poker Game Engine & API

Python/FastAPI backend that runs the authoritative No-Limit Texas Hold'em game engine, exposes REST + WebSocket endpoints, and persists state in Redis.

## Tech Stack

| Component | Version |
|-----------|---------|
| Python | 3.12 |
| FastAPI | 0.115.6 |
| Uvicorn | 0.34.0 |
| Redis (async, hiredis) | 5.2.1 |
| Pydantic | 2.10.4 |
| pytest | 9.0.2 |

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI app, REST + WebSocket endpoints, broadcasting
│   ├── engine.py          # Core game engine (1,380 lines)
│   ├── cards.py           # Card, Deck, Rank, Suit classes
│   ├── evaluator.py       # Hand evaluation (7→5 card, winner determination)
│   ├── game_manager.py    # Business logic between routes and engine
│   ├── ws_manager.py      # WebSocket connection manager + spectators
│   ├── timer.py           # Background action timer (auto-fold, auto-deal)
│   ├── cleanup.py         # Background stale-game cleanup (24h inactive)
│   ├── models.py          # Pydantic request/response models
│   └── redis_client.py    # Async Redis persistence layer
├── tests/
│   ├── test_engine.py     # Engine tests (237 tests total across all files)
│   ├── test_actions.py    # Betting action tests
│   ├── test_api.py        # HTTP endpoint tests
│   ├── test_cards.py      # Card/Deck tests
│   ├── test_evaluator.py  # Hand evaluation tests
│   ├── test_game_manager.py # Business logic tests
│   └── test_serialization.py # Engine serialization round-trip tests
├── Dockerfile
├── requirements.txt
└── pytest.ini
```

## Modules

### `engine.py` — Game Engine

The core of the application. Manages the complete lifecycle of a No-Limit Texas Hold'em game:

- **Hand lifecycle** — `start_new_hand()`, `process_action()`, street progression, showdown
- **Betting** — Fold, check, call, raise, all-in with proper min-raise tracking
- **Pot management** — Side pot calculation for multi-way all-in scenarios
- **Dealer rotation** — Correct dealer/blind rotation including heads-up rules
- **Blind schedule** — Timed blind level progression with configurable or custom schedules
- **Rebuy system** — Configurable rebuy with max count, time cutoff, and queued rebuys during active hands
- **Elimination tracking** — Players added to elimination order on bust, removed on rebuy; ensures complete final standings
- **Game over detection** — Runs at end of every hand; produces ranked standings (winner → last eliminated → first eliminated)
- **Pause/resume** — Freezes action timers and blind clock; tracks total paused time
- **Serialization** — Full `to_dict()` / `from_dict()` for Redis persistence

Key classes:
- `GameEngine` — Main engine holding all game state
- `PlayerState` — Per-player state (chips, cards, bets, flags)
- `HandHistory` — Records actions and results for each hand
- `Street`, `PlayerAction` — Enums for game phases and actions

### `evaluator.py` — Hand Evaluator

Evaluates the best 5-card hand from any combination of cards (typically 7 — 2 hole + 5 community):

- Uses combinatorial evaluation across all 21 possible 5-card combinations
- Returns a `HandRank` tuple that supports direct comparison
- Categories: High Card → One Pair → Two Pair → Three of a Kind → Straight → Flush → Full House → Four of a Kind → Straight Flush → Royal Flush
- `determine_winners()` handles ties and split pots
- Wheel straight (A-2-3-4-5) correctly handled

### `cards.py` — Cards & Deck

- `Card` — Immutable card with `Rank` (IntEnum 2–14) and `Suit` (str Enum h/d/c/s)
- `Deck` — Standard 52-card deck with Fisher-Yates shuffle, `deal(n)` method
- Full serialization support (`to_dict()` / `from_dict()`)

### `game_manager.py` — Business Logic

Sits between the HTTP routes and the engine, handling:

- Game creation with settings validation
- Player join with PIN verification (SHA-256 hashed)
- Ready toggling and game start authorization (creator only)
- Action dispatch with PIN re-verification
- Engine state retrieval with per-player view filtering

### `main.py` — FastAPI Application

REST endpoints and WebSocket handling:

- **Lobby endpoints** — Create, join, get state, ready, start
- **Game endpoints** — Action, deal, rebuy, cancel rebuy, show cards, pause
- **WebSocket** — Per-player connections with automatic state broadcasting
- **Spectator support** — Unknown player IDs connect as spectators (no hole cards)
- **Broadcasting** — State changes push to all connected players/spectators
- **Background tasks** — Action timer and stale game cleanup start on app lifespan

### `ws_manager.py` — WebSocket Manager

- Tracks player and spectator connections per game
- Heartbeat with configurable ping interval
- Broadcasts connection info (who's online, spectator count)
- Handles reconnection (replaces stale connections)
- `ClientRole` enum distinguishes players from spectators

### `timer.py` — Action Timer

Single asyncio background loop that:

- Checks for expired action deadlines every second
- Auto-folds (or auto-checks if checking is valid) when a player's turn times out
- Handles auto-deal between hands after a configurable delay
- Pauses automatically when the game is paused

### `cleanup.py` — Stale Game Cleanup

Background task that runs every 30 minutes:

- Removes games inactive for 24+ hours
- Preserves completed games for 72 hours (so players can review results)
- Cleans up associated Redis keys

### `redis_client.py` — Redis Persistence

Async Redis wrapper:

- Connection pooling with `redis.asyncio`
- JSON serialization for all game data (lobby state + engine state)
- Key schema: `game:{code}` for lobby, `engine:{code}` for engine state
- Configurable via `REDIS_URL` environment variable (default: `redis://localhost:6379/0`)

### `models.py` — Pydantic Models

Request/response models with built-in validation:

- Name: 1–20 characters
- PIN: exactly 4 digits
- Starting chips: 100–100,000
- Blinds: SB ≥ 1, BB ≥ 2
- Max players: 2–9
- Turn timeout: 0–300 seconds
- Blind level duration: 0–120 minutes

## Development

### Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run (Development)

```bash
uvicorn app.main:app --reload --port 8000
```

Requires Redis at `localhost:6379` (or set `REDIS_URL`).

### Run Tests

```bash
python -m pytest tests/ -v
```

Tests use mocked Redis — no running Redis instance required. The test suite covers:

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_engine.py` | ~130 | Engine lifecycle, betting, pots, blinds, rebuys, elimination, game over |
| `test_actions.py` | ~45 | All betting actions, edge cases, invalid moves |
| `test_api.py` | ~20 | HTTP endpoints, error handling, auth |
| `test_game_manager.py` | ~20 | Business logic, PIN verification, game flow |
| `test_evaluator.py` | ~15 | Hand ranking, winner determination, ties |
| `test_cards.py` | ~5 | Card creation, deck dealing, serialization |
| `test_serialization.py` | ~5 | Engine round-trip through `to_dict()` / `from_dict()` |

### Docker

```bash
docker build -t poker-backend .
docker run -p 8000:8000 -e REDIS_URL=redis://host.docker.internal:6379/0 poker-backend
```

## API Reference

### Lobby

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/games` | Create a new game |
| `POST` | `/api/games/{code}/join` | Join an existing game |
| `GET` | `/api/games/{code}` | Get lobby state |
| `POST` | `/api/games/{code}/ready` | Toggle ready status |
| `POST` | `/api/games/{code}/start` | Start the game (creator only) |

### Gameplay

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/games/{code}/state/{player_id}` | Get engine state (player's view) |
| `POST` | `/api/games/{code}/action` | Submit action (fold/check/call/raise/all_in) |
| `POST` | `/api/games/{code}/deal` | Deal next hand |
| `POST` | `/api/games/{code}/rebuy` | Request a rebuy |
| `POST` | `/api/games/{code}/cancel_rebuy` | Cancel a queued rebuy |
| `POST` | `/api/games/{code}/show_cards` | Voluntarily reveal hole cards |
| `POST` | `/api/games/{code}/pause` | Toggle pause (creator only) |

### Admin

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/admin/cleanup` | Manually trigger stale-game cleanup |

### WebSocket

| Endpoint | Description |
|----------|-------------|
| `WS /ws/{code}/{player_id}` | Real-time game state updates |

Messages are JSON with a `type` field:
- `game_state` — Full engine state (player-specific view)
- `lobby_state` — Lobby state update
- `connection_info` — Who's online + spectator count
- `ping` — Heartbeat (client should respond with pong)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
