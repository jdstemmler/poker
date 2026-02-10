# Frontend — Poker Game UI

React single-page application providing the mobile-first interface for the poker game. Communicates with the backend via REST API and WebSocket for real-time updates.

## Tech Stack

| Component | Version |
|-----------|---------|
| React | 19 |
| TypeScript | ~5.9 |
| Vite | 7 |
| React Router | 7 |
| Nginx | Alpine (production) |

No additional UI libraries — all styling is hand-written CSS with a dark theme.

## Project Structure

```
frontend/
├── public/
│   └── favicon.svg          # Playing cards SVG favicon
├── src/
│   ├── api.ts               # REST API client (all fetch calls)
│   ├── types.ts             # TypeScript interfaces mirroring backend models
│   ├── useGameSocket.ts     # WebSocket hook with auto-reconnection
│   ├── App.tsx              # Router setup
│   ├── main.tsx             # React entry point
│   ├── index.css            # All styles (dark theme, responsive)
│   ├── pages/
│   │   ├── HomePage.tsx     # Landing page — create or join
│   │   ├── CreateGamePage.tsx # Game configuration form
│   │   ├── JoinGamePage.tsx # Enter name/PIN to join + spectator mode
│   │   ├── LobbyPage.tsx   # Waiting room, ready up, start
│   │   ├── TablePage.tsx   # Main gameplay view (698 lines)
│   │   └── AdminPage.tsx   # Admin dashboard (password-protected)
│   └── components/
│       ├── CardDisplay.tsx  # Playing card rendering (rank + suit)
│       └── HelpModal.tsx    # In-game help overlay
├── Dockerfile               # Multi-stage: Node build → Nginx serve
├── nginx.conf               # Reverse proxy config for API/WS
├── index.html               # SPA shell
├── vite.config.ts           # Dev proxy for API/WS
├── package.json
├── tsconfig.json
└── eslint.config.js
```

## Pages

### `HomePage`
Landing page with two options: **Create New Game** or **Join Game** (with optional game code input).

### `CreateGamePage`
Configuration form for new games with all settings:
- Starting chips, small/big blind
- Max players (2–9)
- Rebuy settings (enable/disable, max count, time cutoff)
- Turn timeout
- Blind level duration
- Input fields suppress password managers (custom autocomplete attributes)

### `JoinGamePage`
- Enter name and 4-digit PIN to join via game code
- **Watch Game** button for spectator mode (generates random spectator ID)
- Help modal explaining gameplay and spectating

### `LobbyPage`
Waiting room before the game starts:
- Shows all joined players with ready status
- Ready toggle button
- Creator sees **Start Game** button (requires all players ready)
- **Copy Join Link** for easy sharing
- Real-time updates via WebSocket

### `TablePage`
The main gameplay view — the largest and most complex page:

**Layout:**
- **Header** — Game code, blind info, hamburger menu (Home, Create Game, Join Game), rebuy status indicator
- **Community cards** — Displayed in the center during active hands
- **Player list** — All players in consistent seat order with chips, bets, status indicators (dealer chip, action badges, fold/all-in/sitting-out states)
- **Action tray** — Fold, Check/Call, Raise slider + All-In for the active player
- **Between-hands section** — Deal button, show cards, rebuy options

**Features:**
- Pot and bet displays
- Turn timer countdown bar
- Auto-deal countdown
- Blind level display with next-level timer
- Pause/resume control (creator only)
- Last hand result with winner info and separate refund display for uncalled bets
- Showdown card reveal
- Voluntary card showing after hands
- Rebuy button (queues during active hand, immediate between hands)
- Cancel rebuy option
- Game over overlay with ranked standings (trophy for winner)
- Spectator mode (hidden hole cards, no action buttons, "Watching" badge)
- "(you)" tag on own player row

### `AdminPage`
- Password-gated admin dashboard
- Summary cards: 24h game creation/cleanup counts, active game count
- 30-day daily bar chart with created, completed, abandoned, never-started breakdowns
- Active games table: game code, creator IP, creation time, player count, last activity
- Auto-refresh every 30 seconds
- Logout button to clear session

## Components

### `CardDisplay`
Renders a playing card as a compact square with rank and suit. Supports:
- Face-up cards (colored by suit — red for hearts/diamonds, dark for clubs/spades)
- Face-down cards (back design)
- Responsive sizing via CSS classes

### `HelpModal`
Overlay explaining gameplay controls, hand rankings reference, and spectator mode. Toggled by the (?) button in the header.

## Key Modules

### `api.ts` — API Client
Typed fetch wrapper for all backend endpoints:
- `createGame()`, `joinGame()`, `getGame()`
- `toggleReady()`, `startGame()`
- `sendAction()`, `dealNextHand()`
- `requestRebuy()`, `cancelRebuy()`
- `showCards()`, `togglePause()`
- `buildWsUrl()` — constructs WebSocket URL (auto-detects protocol)

Uses `VITE_API_BASE` and `VITE_WS_BASE` environment variables (defaults to same origin).

### `useGameSocket.ts` — WebSocket Hook
Custom React hook providing real-time game state:
- Automatic connection and reconnection with exponential backoff
- Parses `game_state`, `lobby_state`, `connection_info`, and `ping` messages
- Responds to server pings with pong
- Returns current `EngineState` that triggers re-renders on updates
- Cleans up on unmount

### `types.ts` — Type Definitions
TypeScript interfaces mirroring the backend's JSON structures:
- `EngineState` — Full game state (50+ fields)
- `EnginePlayer` — Per-player state (chips, bets, flags, actions)
- `CardData` — Card rank + suit
- `ValidAction` — Available actions with min/max amounts
- `HandResult` — Winner info, pot, player hands, refunds for uncalled bets
- `HandResultRefund` — Uncalled bet return (player, amount)
- `FinalStanding` — End-of-game ranking
- `GameState`, `GameSettings`, `PlayerInfo` — Lobby types
- `WsMessage`, `ConnectionInfo` — WebSocket message types

### `index.css` — Styles
All CSS in a single file (1,800+ lines):
- Dark theme with CSS custom properties
- Mobile-first responsive design
- Card styling (compact square layout, suit colors)
- Player row states (active, folded, all-in, sitting out, winner)
- Action button styling (fold=red, check/call=green, raise=blue)
- Raise slider
- Timer animation bars
- Hamburger menu
- Game over standings overlay
- Spectator badge
- Admin dashboard styles (login form, summary cards, chart, table)
- Lobby and form styles

## Development

### Setup

```bash
cd frontend
npm install
```

### Run (Development)

```bash
npm run dev
```

Dev server runs on `http://localhost:5173` with HMR. The Vite config proxies `/api/*` and `/ws/*` to `http://localhost:8000` automatically.

To point at a different backend:

```bash
VITE_API_BASE=http://192.168.1.100:8000 VITE_WS_BASE=ws://192.168.1.100:8000 npm run dev
```

### Build

```bash
npm run build
```

Produces optimized static files in `dist/`.

### Lint

```bash
npm run lint
```

### Docker

The Dockerfile uses a multi-stage build:

1. **Build stage** — `node:20-alpine`, runs `npm ci` + `npm run build`
2. **Serve stage** — `nginx:alpine`, serves `dist/` with custom `nginx.conf`

```bash
docker build -t poker-frontend .
docker run -p 3000:3000 poker-frontend
```

## Nginx Configuration

The production nginx config (`nginx.conf`) handles three concerns:

| Path | Behavior |
|------|----------|
| `/api/*` | Proxied to `http://backend:8000` |
| `/ws/*` | Proxied with WebSocket upgrade headers, 24h read timeout |
| `/*` | Serves static files with SPA fallback (`try_files → /index.html`) |

## Session Storage

Player identity is stored in `sessionStorage` (per-tab):
- `player_id` — UUID assigned on join
- `player_pin` — 4-digit PIN (sent with authenticated requests)
- `game_code` — Current game code
- `player_name` — Display name
- `is_spectator` — Whether viewing as spectator

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE` | `""` (same origin) | Backend API base URL |
| `VITE_WS_BASE` | Auto-detected | WebSocket base URL (ws/wss based on page protocol) |
