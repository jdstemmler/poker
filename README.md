# ♠♥♦♣ Poker Game

A self-hosted, mobile-first web application for playing **No-Limit Texas Hold'em** with friends. Create a game, share the code, and play from any device on your network.

## Features

- **Lobby system** — Create/join games with a short room code and 4-digit PIN
- **Full NL Hold'em engine** — Blinds, betting rounds, pot management, showdown, side pots
- **Real-time updates** — WebSocket-driven state sync with automatic reconnection
- **Turn timer** — Optional configurable countdown with auto-fold/auto-check
- **Mobile-first UI** — Dark theme, touch-optimized action buttons, responsive layout
- **Pre-Fold** — Queue a fold before your turn arrives
- **Voluntary card reveal** — Cards hidden by default after each hand; players choose whether to show
- **Spectator mode** — Watch a game without joining
- **Rebuys** — Optional rebuy when busted

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Frontend | React 19, TypeScript 5.9, Vite 7 |
| State | Redis 7 (async, hiredis) |
| Auth | Name + 4-digit PIN (SHA-256 hashed) |
| Real-time | WebSocket (FastAPI native) |
| Deployment | Docker Compose (3 containers) |
| Reverse Proxy | Nginx (serves frontend, proxies API/WS) |

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose

### Run

```bash
git clone <repo-url> poker-game
cd poker-game
docker compose up -d
```

Open **http://localhost:3000** in your browser.

To play with others on your local network, share `http://<your-ip>:3000`.

### Stop

```bash
docker compose down
```

Add `-v` to also clear Redis data:

```bash
docker compose down -v
```

## Development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Requires a running Redis instance at `localhost:6379` (or set `REDIS_URL`).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dev server runs on `http://localhost:5173` with HMR. Set the `VITE_API_BASE` and `VITE_WS_BASE` env vars to point at the backend:

```bash
VITE_API_BASE=http://localhost:8000 VITE_WS_BASE=ws://localhost:8000 npm run dev
```

## Architecture

```
┌─────────────┐       ┌──────────────┐       ┌───────────┐
│   Browser    │◄─────►│   Nginx      │◄─────►│  FastAPI   │
│  (React SPA) │  WS   │  :3000       │ proxy │  :8000     │
└─────────────┘       └──────────────┘       └─────┬─────┘
                                                   │
                                              ┌────▼────┐
                                              │  Redis   │
                                              │  :6379   │
                                              └─────────┘
```

- **Nginx** serves the built React SPA and proxies `/api/*` and `/ws/*` to the backend
- **FastAPI** handles REST endpoints, WebSocket connections, and the game engine
- **Redis** stores all game state (lobby, players, engine) as JSON

### Backend Modules

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, REST + WebSocket endpoints, broadcasting |
| `engine.py` | Core game engine — dealing, betting, showdown, pot management |
| `cards.py` | Card and Deck classes with serialization |
| `evaluator.py` | Hand evaluation (7-card to 5-card best hand, winner determination) |
| `game_manager.py` | Business logic layer between routes and engine |
| `ws_manager.py` | WebSocket connection manager with heartbeat and spectator support |
| `timer.py` | Background action timer (auto-fold/auto-check on timeout) |
| `models.py` | Pydantic request/response models |
| `redis_client.py` | Async Redis persistence layer |

### Frontend Pages

| Page | Route | Purpose |
|------|-------|---------|
| `HomePage` | `/` | Landing — create or join a game |
| `CreateGamePage` | `/create` | Configure game settings |
| `JoinGamePage` | `/join/:code?` | Enter name and PIN to join |
| `LobbyPage` | `/game/:code/lobby` | Waiting room, ready up, start game |
| `TablePage` | `/game/:code` | Main gameplay view |

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
| `POST` | `/api/games/{code}/deal` | Deal next hand (creator only) |
| `POST` | `/api/games/{code}/rebuy` | Request a rebuy |
| `POST` | `/api/games/{code}/show_cards` | Voluntarily reveal cards after a hand |

### WebSocket

| Endpoint | Description |
|----------|-------------|
| `WS /ws/{code}/{player_id}` | Real-time game state updates, connection info, heartbeat |

## Game Flow

1. **Create** a game — configure blinds, starting chips, timer, max players
2. **Share** the 6-character room code with friends
3. **Join** — each player enters their name and a 4-digit PIN
4. **Ready up** — everyone toggles ready in the lobby
5. **Start** — creator starts the game, first hand is dealt automatically
6. **Play** — standard No-Limit Hold'em: preflop → flop → turn → river → showdown
7. **Between hands** — cards are hidden; players may click "Show Cards" to reveal
8. **Next hand** — creator clicks "Deal Next Hand" to continue
9. **Rebuy** — busted players can rebuy back to starting chips (if enabled)

## Configuration

Game settings are configured at creation time:

| Setting | Default | Description |
|---------|---------|-------------|
| Starting Chips | 1000 | Chips each player starts with |
| Small Blind | 5 | Small blind amount |
| Big Blind | 10 | Big blind amount |
| Max Players | 8 | Maximum seats at the table |
| Allow Rebuys | Yes | Whether busted players can rebuy |
| Turn Timeout | 0 (off) | Seconds per turn (0 = unlimited) |

## License

Private / personal project.
