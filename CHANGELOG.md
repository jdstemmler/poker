# Changelog

All notable changes to this project will be documented in this file.

## [1.4.1] — 2026-02-11

### Fixed
- **Blind timer keeps running after game ends** — The blind countdown timer now
  stops when the game is over. Backend `get_next_blind_change_at()` returns
  `None` when `game_over` is set; frontend clears the countdown on game end.
- **Blind timer disappears while paused** — The blind countdown now stays visible
  (frozen) when the game is paused, matching the behavior of the elapsed and
  rebuy timers. Previously the backend returned `None` during pause, causing the
  timer to vanish entirely.
- **Timer width jitter in header** — Added `font-variant-numeric: tabular-nums`
  to all timer and blind displays (elapsed, rebuy countdown, blind value, blind
  countdown) so digits render at equal width. Set `min-width` and `flex` on
  header sections to keep the rebuy pill and timers stable as numbers change.

### Added
- **Next blind level preview** — The blind countdown in the header now shows the
  upcoming blind values alongside the time remaining (e.g. "15/30 in 4:32"
  instead of "Next: 4:32").

## [1.4.0] — 2026-02-11

### Security
- **Timing-safe admin password check** — Admin endpoint authentication now uses
  `hmac.compare_digest()` instead of direct string comparison to prevent timing
  attacks against the admin password.
- **Rate limiting** — All REST endpoints are now rate-limited via `slowapi`.
  Create/start: 5/min, join/leave/rebuy/pause/admin: 10/min, game actions/deal:
  30/min. Returns HTTP 429 when exceeded. Configurable via `RATE_LIMIT_ENABLED`
  env var (set to `0` to disable).

### Fixed
- **Race conditions in game engine operations** — Added per-game `asyncio.Lock`
  to all engine load-modify-save operations in `game_manager.py` and `timer.py`,
  preventing concurrent requests from corrupting game state.
- **Timer paths missing game-over detection** — Auto-fold and auto-deal timer
  handlers now use `_save_engine()` (which checks for game-over transitions)
  instead of writing raw engine data directly to Redis. Games that end via
  timeout are now properly marked as "ended."
- **Rebuy cutoff ignoring pause time** — Rebuy time window now uses
  `_effective_elapsed()` (which excludes paused time) instead of raw wall-clock
  time. Pausing no longer eats into the rebuy window.
- **Silent exception swallowing** — All bare `except Exception: pass` blocks
  replaced with `logger.debug(...)` or `logger.warning(...)` calls for proper
  observability. Expected failures (disconnected WebSocket clients) log at debug
  level; unexpected failures log at warning level with full tracebacks.

### Added
- **`slowapi` dependency** — Added to `backend/requirements.txt` for rate limiting.
- **`RATE_LIMIT_ENABLED` env var** — Set to `0` to disable rate limiting
  (useful for testing and development).

## [1.3.0] — 2026-02-10

### Changed
- **Auto-calculated blind schedule**: Replaced manual small blind / big blind /
  multiplier inputs with a target-time-based system. New inputs: Starting Chips
  (default 5,000), Target Game Time (hours, default 4), and Level Duration
  (minutes, default 20). Blinds are derived automatically (BB = chips / 100,
  snapped to standard tournament values).
- **Blind algorithm**: Three-phase schedule — linear ramp for the first half of
  levels, geometric progression to reach starting-chips BB by target time, then
  overtime levels at 1.5× until BB ≥ 3× starting chips. All values snapped to a
  standard tournament blind table via binary search.
- **Dynamic blind extension**: If the game clock exceeds the pre-built schedule,
  new levels are appended at runtime (1.5× last BB, snapped to standard values).
  Blinds never stall regardless of game duration or rebuys.
- **Schedule preview modal**: "View Blind Schedule" button on the Create Game page
  opens a full-screen modal showing all levels with SB/BB and cumulative time in
  +H:MM format.
- **Create Game form layout**: Target Game Time and Level Duration fields are
  displayed side-by-side to save vertical space.

### Removed
- Manual Small Blind, Big Blind, and Blind Multiplier settings (now auto-derived).

## [1.2.0] — 2026-02-10

### Added
- **Admin dashboard** — Password-protected admin page at `/admin` with:
  - Summary view (24h game creation/cleanup counts, active game count)
  - Daily stats chart (30-day bar chart with created, completed, abandoned, never-started breakdowns)
  - Active games detail table (game code, creator IP, creation time, player count, last activity)
  - Auto-refresh every 30 seconds
- **Admin API endpoints** — `/api/admin/summary`, `/api/admin/daily-stats`,
  `/api/admin/active-games` secured via `Authorization: Bearer <password>` header.
- **Metrics system** — Redis sorted-set–based tracking for game creation,
  completion, and cleanup events with automatic 90-day pruning.
- **Game completion tracking** — Games marked as "ended" immediately when the
  last opponent is eliminated (previously only updated during cleanup 24–72 h later).
- **`ADMIN_PASSWORD` env var** — Controls admin dashboard access; added to
  `docker-compose.yml` backend environment.

### Fixed
- **Game completion count always 0** — Completion metric was only recorded
  during stale-game cleanup, not at the moment the game actually ended.
- **Game status stuck on "ACTIVE"** — `_save_engine()` now detects the
  `game_over` transition and updates lobby status to "ended" immediately.
- **Elapsed timer kept ticking after game over** — Timer interval now stops
  when `engine.game_over` is set.
- **Rebuy status showed "Closed" prematurely** — Header text now uses the
  time-based rebuy window instead of player eligibility, so it reads "Open"
  when rebuys are still available even if no one has busted yet.
- **Rebuy timer jumped on first bust** — Timer is now always visible when
  rebuys are enabled (no sudden appearance/jump).
- **Between-hands rebuy button confusing** — Shows "Cancel Rebuy" when a
  rebuy is already queued instead of offering a duplicate "Rebuy" button.
- **Side pot refund displayed as a "win"** — When a player's uncalled all-in
  excess is returned (e.g., all-in for 1980 vs opponent's max 960), the hand
  result overlay now shows "1000 returned" instead of "wins 1000 with One Pair".
  Refunds are tracked in a separate `refunds` list in `last_hand_result`.

## [1.1.0] — 2026-02-10

### Fixed
- **All-in action logic**: When a player can't meet the minimum re-raise but has
  chips beyond the call amount, the engine now returns a `raise` action
  (min = max = stack) instead of a separate `all_in` action. The frontend shows
  an "All-In" button directly for this case and a normal raise slider otherwise.
- **Blind multiplier button hover bug**: The "Blind Increase" option buttons no
  longer cause the first button to highlight on any hover (was caused by `<label>`
  wrapping interactive buttons).

### Changed
- **Blind schedule options**: Replaced `[1.5×, 2×, 3×, 4×]` multiplier choices
  with `[Linear, 1.5×, 2×]`. "Linear" adds the initial blinds each level
  (e.g. 10/20 → 20/40 → 30/60). Maximum multiplier capped at 2×.
- Blind increase validation range updated from `1.0–4.0` to `0–2.0`
  (`0` = linear/additive mode).

## [1.0.0] — 2026-02-08

### Features
- **Core poker engine**: Full Texas Hold'em with preflop through showdown,
  side pots, split pots, and proper hand evaluation.
- **Real-time multiplayer**: WebSocket-based game state sync with Redis
  persistence.
- **Game creation**: Configurable starting chips, blinds, rebuys, turn timer,
  and blind level scheduling with multiplier.
- **Auto-deal**: Hands auto-deal after a 10-second countdown; any player can
  deal early.
- **Blind level increases**: Configurable duration and multiplier with schedule
  preview.
- **Rebuy system**: Max rebuys, cutoff timer, queued rebuys during active hands.
- **Pause/resume**: Game creator can pause the game between hands.
- **Spectator mode**: "Watch Game" button lets non-players observe.
- **Elimination tracking**: Ranked standings with add-on-bust / remove-on-rebuy.
- **Game over**: Inline ranked standings when one player remains.
- **Copy join link**: Easy share button to invite players.
- **Help modals**: Contextual help on Home, Create, and Join pages.
- **Stale game cleanup**: Background task and admin endpoint.

### UI / UX
- Mobile-optimized layout with sticky action tray.
- Hamburger menu with navigation links.
- Playing cards favicon.
- Compact square card design.
- Single-line player rows (action left, pot + chips right).
- Raise slider with big-blind stepping and snap presets (Min, ½ Pot, Pot, All-In).
- Call button as prominent full-width row above Fold/Check/Raise.
- Game creation form organized into logical fieldsets (Blinds, Timing, Rebuys).
- Auto-deal toggle on game creation.
- NumericInput fields show placeholder text when value is "off" (0); select
  content on focus.
- PIN field clarified to avoid confusion with a game-wide password.
- Exit lobby option for players to leave before the game starts.
- iOS Safari fixes for button colors, GPU compositing, and repaint bugs.
- Suppressed password manager prompts on PIN and form fields.

### Infrastructure
- Docker Compose stack: FastAPI backend, React/Vite frontend behind nginx, Redis.
- Comprehensive backend test suite (250+ tests).
- Backend and frontend READMEs.
