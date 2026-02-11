# Changelog

All notable changes to this project will be documented in this file.

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
- **Admin dashboard**: Password-protected metrics page at `/admin` showing game
  and player statistics.
- **Game completion tracking**: Games are marked as ended immediately upon
  completion with recorded metrics.
- **Hand probability validation tests**: Statistical tests verifying correct
  distribution of dealt hands.

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
