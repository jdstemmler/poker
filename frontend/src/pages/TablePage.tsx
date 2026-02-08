/** Game Table Page — main gameplay view. */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  buildWsUrl,
  getEngineState,
  sendAction,
  dealNextHand,
  requestRebuy,
  cancelRebuy,
  showCards,
  getGame,
  togglePause,
} from "../api";
import { useGameSocket } from "../useGameSocket";
import { CardList } from "../components/CardDisplay";
import type { EngineState, GameState, ConnectionInfo } from "../types";

export default function TablePage() {
  const { code } = useParams<{ code: string }>();
  const [engine, setEngine] = useState<EngineState | null>(null);
  const [lobbyGame, setLobbyGame] = useState<GameState | null>(null);
  const [connInfo, setConnInfo] = useState<ConnectionInfo | null>(null);
  const [error, setError] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [raiseAmount, setRaiseAmount] = useState(0);
  const [showRaisePanel, setShowRaisePanel] = useState(false);
  const [preFold, setPreFold] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const playerId = sessionStorage.getItem("playerId");
  const playerPin = sessionStorage.getItem("playerPin");
  const isSpectator = sessionStorage.getItem("isSpectator") === "true";
  const notAuthenticated = !playerId || (!playerPin && !isSpectator);

  const wsUrl = code && playerId ? buildWsUrl(code, playerId) : null;

  const handleEngineUpdate = useCallback((state: EngineState) => {
    setEngine(state);
  }, []);

  const handleLobbyUpdate = useCallback((state: GameState) => {
    setLobbyGame(state);
  }, []);

  const handleConnectionInfo = useCallback((info: ConnectionInfo) => {
    setConnInfo(info);
  }, []);

  const { connected } = useGameSocket({
    url: notAuthenticated ? null : wsUrl,
    onEngineUpdate: handleEngineUpdate,
    onLobbyUpdate: handleLobbyUpdate,
    onConnectionInfo: handleConnectionInfo,
  });

  // Fetch initial engine state
  useEffect(() => {
    if (!code || !playerId) return;
    getEngineState(code, playerId)
      .then(setEngine)
      .catch((e) => setError(e.message));
    getGame(code)
      .then(setLobbyGame)
      .catch(() => {});
  }, [code, playerId]);

  const isCreator = lobbyGame?.creator_id === playerId;

  // Update raise slider when valid actions change
  useEffect(() => {
    if (!engine) return;
    const raiseAction = engine.valid_actions.find((a) => a.action === "raise");
    if (raiseAction?.min_amount) {
      setRaiseAmount(raiseAction.min_amount);
    }
    // Close raise panel when it's no longer our turn
    if (engine.action_on !== playerId) {
      setShowRaisePanel(false);
    }
  }, [engine?.valid_actions, engine?.action_on, playerId]);

  // Pre-fold: auto-fold when it becomes our turn
  useEffect(() => {
    if (!engine || !preFold) return;
    if (engine.action_on === playerId && engine.hand_active) {
      setPreFold(false);
      doAction("fold");
    }
  }, [engine?.action_on, engine?.hand_active, preFold, playerId]);

  // Clear pre-fold when hand ends  
  useEffect(() => {
    if (engine && !engine.hand_active) {
      setPreFold(false);
    }
  }, [engine?.hand_active]);

  // Countdown timer
  const [timeLeft, setTimeLeft] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    clearInterval(timerRef.current);

    if (!engine?.action_deadline || !engine.hand_active || engine.turn_timeout === 0) {
      setTimeLeft(null);
      return;
    }

    const tick = () => {
      const remaining = engine.action_deadline! - Date.now() / 1000;
      setTimeLeft(Math.max(0, remaining));
    };

    tick();
    timerRef.current = setInterval(tick, 250);

    return () => clearInterval(timerRef.current);
  }, [engine?.action_deadline, engine?.hand_active, engine?.turn_timeout]);

  // Auto-deal countdown
  const [dealTimeLeft, setDealTimeLeft] = useState<number | null>(null);
  const dealTimerRef = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    clearInterval(dealTimerRef.current);

    if (!engine?.auto_deal_deadline || engine.hand_active) {
      setDealTimeLeft(null);
      return;
    }

    const tick = () => {
      const remaining = engine.auto_deal_deadline! - Date.now() / 1000;
      setDealTimeLeft(Math.max(0, remaining));
    };

    tick();
    dealTimerRef.current = setInterval(tick, 250);

    return () => clearInterval(dealTimerRef.current);
  }, [engine?.auto_deal_deadline, engine?.hand_active]);

  // Elapsed game time
  const [elapsed, setElapsed] = useState("");
  const elapsedRef = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    clearInterval(elapsedRef.current);

    if (!engine?.game_started_at) {
      setElapsed("");
      return;
    }

    const tick = () => {
      const totalElapsed = Date.now() / 1000 - engine.game_started_at!;
      const secs = Math.max(0, Math.floor(totalElapsed - (engine.total_paused_seconds ?? 0)));
      const h = Math.floor(secs / 3600);
      const m = Math.floor((secs % 3600) / 60);
      const s = secs % 60;
      setElapsed(
        h > 0
          ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
          : `${m}:${String(s).padStart(2, "0")}`
      );
    };

    tick();
    // Stop ticking while paused (time is frozen)
    if (!engine.paused) {
      elapsedRef.current = setInterval(tick, 1000);
    }

    return () => clearInterval(elapsedRef.current);
  }, [engine?.game_started_at, engine?.paused, engine?.total_paused_seconds]);

  // Rebuy clock countdown
  const [rebuyTimeLeft, setRebuyTimeLeft] = useState<number | null>(null);
  const rebuyRef = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    clearInterval(rebuyRef.current);

    if (
      !engine?.allow_rebuys ||
      !engine.rebuy_cutoff_minutes ||
      !engine.game_started_at
    ) {
      setRebuyTimeLeft(null);
      return;
    }

    const tick = () => {
      const totalElapsed = Date.now() / 1000 - engine.game_started_at!;
      const activeSecs = totalElapsed - (engine.total_paused_seconds ?? 0);
      const cutoffSecs = engine.rebuy_cutoff_minutes * 60;
      setRebuyTimeLeft(Math.max(0, cutoffSecs - activeSecs));
    };

    tick();
    if (!engine.paused) {
      rebuyRef.current = setInterval(tick, 1000);
    }

    return () => clearInterval(rebuyRef.current);
  }, [
    engine?.allow_rebuys,
    engine?.rebuy_cutoff_minutes,
    engine?.game_started_at,
    engine?.paused,
    engine?.total_paused_seconds,
  ]);

  // Next blind change countdown
  const [blindCountdown, setBlindCountdown] = useState("");
  const blindRef = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    clearInterval(blindRef.current);

    if (!engine?.next_blind_change_at) {
      setBlindCountdown("");
      return;
    }

    const tick = () => {
      const secs = Math.max(0, Math.floor(engine.next_blind_change_at! - Date.now() / 1000));
      const m = Math.floor(secs / 60);
      const s = secs % 60;
      setBlindCountdown(`${m}:${String(s).padStart(2, "0")}`);
    };

    tick();
    blindRef.current = setInterval(tick, 1000);

    return () => clearInterval(blindRef.current);
  }, [engine?.next_blind_change_at]);

  if (notAuthenticated) {
    return (
      <div className="page">
        <h1>Not Authenticated</h1>
        <Link to="/" className="btn btn-primary">Go Home</Link>
      </div>
    );
  }

  if (error && !engine) {
    return (
      <div className="page">
        <h1>Error</h1>
        <p className="error">{error}</p>
        <Link to="/" className="btn btn-primary">Go Home</Link>
      </div>
    );
  }

  if (!engine) {
    return (
      <div className="page"><div className="loading-spinner" /><p>Loading game…</p></div>
    );
  }

  const me = engine.players.find((p) => p.player_id === playerId);
  const isMyTurn = engine.action_on === playerId;

  const doAction = async (action: string, amount?: number) => {
    if (!code || !playerId || !playerPin) return;
    setActionLoading(true);
    setError("");
    setShowRaisePanel(false);
    try {
      await sendAction(code, {
        player_id: playerId,
        pin: playerPin,
        action,
        amount: amount ?? 0,
      });
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const doDeal = async () => {
    if (!code || !playerId || !playerPin) return;
    setActionLoading(true);
    setError("");
    try {
      await dealNextHand(code, { player_id: playerId, pin: playerPin });
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const doRebuy = async () => {
    if (!code || !playerId || !playerPin) return;
    setActionLoading(true);
    setError("");
    try {
      await requestRebuy(code, { player_id: playerId, pin: playerPin });
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const doCancelRebuy = async () => {
    if (!code || !playerId || !playerPin) return;
    setActionLoading(true);
    setError("");
    try {
      await cancelRebuy(code, { player_id: playerId, pin: playerPin });
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const doShowCards = async () => {
    if (!code || !playerId || !playerPin) return;
    setActionLoading(true);
    setError("");
    try {
      await showCards(code, { player_id: playerId, pin: playerPin });
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const doPause = async () => {
    if (!code || !playerId || !playerPin) return;
    setActionLoading(true);
    setError("");
    try {
      await togglePause(code, { player_id: playerId, pin: playerPin });
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Find valid actions
  const canFold = engine.valid_actions.some((a) => a.action === "fold");
  const canCheck = engine.valid_actions.some((a) => a.action === "check");
  const callAction = engine.valid_actions.find((a) => a.action === "call");
  const raiseAction = engine.valid_actions.find((a) => a.action === "raise");
  const allInAction = engine.valid_actions.find((a) => a.action === "all_in");

  // Raise step size — use big blind as the natural increment, minimum 5
  const raiseStep = raiseAction ? Math.max(5, engine.big_blind) : 5;
  const snapToStep = (value: number) => {
    if (!raiseAction) return value;
    const min = raiseAction.min_amount ?? 0;
    const max = raiseAction.max_amount ?? 0;
    const snapped = Math.round((value - min) / raiseStep) * raiseStep + min;
    return Math.min(Math.max(snapped, min), max);
  };

  // Raise presets
  const raisePresets = raiseAction ? [
    { label: "Min", value: raiseAction.min_amount ?? 0 },
    { label: "½ Pot", value: snapToStep(Math.floor(engine.pot / 2)) },
    { label: "Pot", value: snapToStep(engine.pot) },
    { label: "All-In", value: raiseAction.max_amount ?? 0 },
  ] : [];

  // Separate "me" from "others" for layout
  const otherPlayers = engine.players.filter((p) => p.player_id !== playerId);

  return (
    <div className="table-page">
      {/* Header bar */}
      <header className="table-header">
        <div className="table-header-left">
          <div className="table-menu-wrapper">
            <button className="table-menu-btn" onClick={() => setMenuOpen(!menuOpen)} aria-label="Menu">☰</button>
            {menuOpen && (
              <>
                <div className="table-menu-backdrop" onClick={() => setMenuOpen(false)} />
                <div className="table-menu-dropdown">
                  <Link to="/" className="table-menu-item" onClick={() => setMenuOpen(false)}>Home</Link>
                  <Link to="/create" className="table-menu-item" onClick={() => setMenuOpen(false)}>Create Game</Link>
                  <Link to="/join" className="table-menu-item" onClick={() => setMenuOpen(false)}>Join Game</Link>
                </div>
              </>
            )}
          </div>
          <div className="table-header-info">
            <span className="table-code">{engine.game_code}</span>
            <span className="table-hand">Hand #{engine.hand_number}{elapsed ? ` · ${elapsed}` : ""}</span>
          </div>
        </div>
        {engine.allow_rebuys && (
          <div className="table-header-center">
            {engine.rebuy_cutoff_minutes > 0 ? (
              rebuyTimeLeft !== null && rebuyTimeLeft > 0 ? (
                <>
                  <span className="rebuy-status open">Rebuy Open</span>
                  <span className="rebuy-countdown">
                    {Math.floor(rebuyTimeLeft / 60)}:{String(Math.floor(rebuyTimeLeft % 60)).padStart(2, "0")}
                  </span>
                </>
              ) : (
                <span className="rebuy-status closed">Rebuy Closed</span>
              )
            ) : (
              <span className="rebuy-status open">Rebuy Open</span>
            )}
          </div>
        )}
        {!engine.allow_rebuys && (
          <div className="table-header-center">
            <span className="rebuy-status disabled">No Rebuys</span>
          </div>
        )}
        <div className="table-header-right">
          <div className="table-blinds-info">
            <span className="blinds-value">{engine.small_blind}/{engine.big_blind}</span>
            {blindCountdown && <span className="blinds-next">Next: {blindCountdown}</span>}
          </div>
          {connInfo && connInfo.spectator_count > 0 && (
            <span className="spectator-badge">👁 {connInfo.spectator_count}</span>
          )}
          {isSpectator && <span className="spectator-badge">Watching</span>}
          <span className={`conn-indicator ${connected ? "on" : "off"}`} />
        </div>
      </header>

      {/* Timer Bar */}
      {engine.hand_active && engine.turn_timeout > 0 && timeLeft !== null && engine.action_on && (
        <div className="timer-bar-container">
          <div
            className={`timer-bar-fill ${timeLeft < 5 ? "urgent" : ""}`}
            style={{ width: `${Math.min(100, (timeLeft / engine.turn_timeout) * 100)}%` }}
          />
          <span className="timer-label">
            {engine.action_on === playerId ? "Your turn" : ""} {Math.ceil(timeLeft)}s
          </span>
        </div>
      )}

      {/* Paused banner */}
      {engine.paused && (
        <div className="paused-banner">
          ⏸ Game Paused
        </div>
      )}

      {/* Felt area — community + pot */}
      <div className="felt-area">
        <div className="felt-street">{engine.street.toUpperCase()}</div>
        <div className="felt-pot">
          <span className="pot-chip" />
          <span className="pot-amount">{engine.pot}</span>
        </div>
        <div className="community-cards">
          {engine.community_cards.length > 0 ? (
            <CardList cards={engine.community_cards} size="lg" />
          ) : (
            engine.hand_active
              ? <span className="muted-cards">Dealing…</span>
              : <span className="muted-cards">—</span>
          )}
        </div>
      </div>

      {/* My hole cards */}
      {me && !me.folded && engine.my_cards.length > 0 && (
        <div className="my-cards-area">
          <span className="my-cards-label">Your Hand</span>
          <CardList cards={engine.my_cards} size="lg" />
        </div>
      )}

      {/* Hand Result overlay */}
      {engine.last_hand_result && !engine.hand_active && (
        <div className="hand-result">
          <div className="hand-result-inner">
            {engine.last_hand_result.winners.map((w, i) => (
              <div key={i} className="winner-line">
                <span className="winner-name">{w.name}</span>
                <span className="winner-detail">wins <strong>{w.winnings}</strong></span>
                <span className="winner-hand">{w.hand}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Players */}
      <div className="player-list">
        {/* My row always first */}
        {me && (
          <div className={`player-row table-player me ${engine.action_on === playerId ? "action-on" : ""} ${me.folded ? "folded" : ""}`}>
            <div className="player-left">
              <span className="player-identity">
                <span className={`conn-dot ${connInfo?.connected_players.includes(me.player_id) ? "on" : "off"}`} />
                {me.player_id === engine.dealer_player_id && <span className="dealer-chip">D</span>}
                <span className="player-name">{me.name} <span className="you-tag">you</span></span>
              </span>
              {me.last_action && <span className="status-tag action-tag">{me.last_action}</span>}
              {me.folded && <span className="status-tag folded-tag">Folded</span>}
              {me.all_in && <span className="status-tag allin-tag">All-In</span>}
              {me.is_sitting_out && <span className="status-tag sit-tag">Sitting Out</span>}
              {me.rebuy_queued && <span className="status-tag rebuy-tag">Rebuy Queued</span>}
              {me.rebuy_count > 0 && <span className="status-tag rebuy-tag">🔄 {me.rebuy_count}</span>}
            </div>
            <div className="player-right">
              {me.bet_this_hand > 0 && <span className="status-tag bet-tag">Pot: {me.bet_this_hand}</span>}
              <span className="player-chips"><span className="chip-icon" />{me.chips}</span>
            </div>
          </div>
        )}
        {otherPlayers.map((p) => {
          const isDealer = p.player_id === engine.dealer_player_id;
          const isAction = p.player_id === engine.action_on;
          const isOnline = connInfo?.connected_players.includes(p.player_id) ?? false;

          return (
            <div
              key={p.player_id}
              className={`player-row table-player ${isAction ? "action-on" : ""} ${p.folded ? "folded" : ""}`}
            >
              <div className="player-left">
                <span className="player-identity">
                  <span className={`conn-dot ${isOnline ? "on" : "off"}`} />
                  {isDealer && <span className="dealer-chip">D</span>}
                  <span className="player-name">{p.name}</span>
                </span>
                {p.last_action && <span className="status-tag action-tag">{p.last_action}</span>}
                {p.folded && <span className="status-tag folded-tag">Folded</span>}
                {p.all_in && <span className="status-tag allin-tag">All-In</span>}
                {p.is_sitting_out && <span className="status-tag sit-tag">Sitting Out</span>}
                {p.rebuy_queued && <span className="status-tag rebuy-tag">Rebuy Queued</span>}
                {p.rebuy_count > 0 && <span className="status-tag rebuy-tag">🔄 {p.rebuy_count}</span>}
              </div>
              <div className="player-right">
                {p.bet_this_hand > 0 && <span className="status-tag bet-tag">Pot: {p.bet_this_hand}</span>}
                <span className="player-chips"><span className="chip-icon" />{p.chips}</span>
                {engine.showdown && p.hole_cards && !p.folded && engine.shown_cards?.includes(p.player_id) && (
                  <CardList cards={p.hole_cards} size="sm" />
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Error */}
      {error && <p className="error">{error}</p>}

      {/* Bottom action area — sticky (hidden for spectators) */}
      {!isSpectator && <div className="action-tray">
        {/* Raise panel (slides up) */}
        {showRaisePanel && raiseAction && (
          <div className="raise-panel">
            <div className="raise-presets">
              {raisePresets.map((p) => (
                <button
                  key={p.label}
                  className={`btn btn-preset ${raiseAmount === p.value ? "active" : ""}`}
                  onClick={() => setRaiseAmount(p.value)}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <div className="raise-slider-row">
              <span className="raise-value">{raiseAmount}</span>
              <input
                type="range"
                min={raiseAction.min_amount}
                max={raiseAction.max_amount}
                step={raiseStep}
                value={raiseAmount}
                onChange={(e) => setRaiseAmount(Number(e.target.value))}
                className="raise-slider"
              />
            </div>
            <button
              className="btn btn-raise-confirm"
              onClick={() => doAction("raise", raiseAmount)}
              disabled={actionLoading}
            >
              Raise to {raiseAmount}
            </button>
          </div>
        )}

        {/* Main action buttons — always visible during active hand */}
        {engine.hand_active && me && !me.folded && !me.is_sitting_out && (
          <div className="action-bar">
            {isMyTurn ? (
              <>
                {canFold && (
                  <button className="btn btn-fold" onClick={() => doAction("fold")} disabled={actionLoading}>
                    Fold
                  </button>
                )}
                {canCheck && (
                  <button className="btn btn-check" onClick={() => doAction("check")} disabled={actionLoading}>
                    Check
                  </button>
                )}
                {callAction && (
                  <button className="btn btn-call" onClick={() => doAction("call")} disabled={actionLoading}>
                    Call {callAction.amount}
                  </button>
                )}
                {raiseAction && (
                  <button
                    className={`btn btn-raise ${showRaisePanel ? "active" : ""}`}
                    onClick={() => setShowRaisePanel(!showRaisePanel)}
                    disabled={actionLoading}
                  >
                    Raise
                  </button>
                )}
                {allInAction && !raiseAction && (
                  <button className="btn btn-allin" onClick={() => doAction("all_in")} disabled={actionLoading}>
                    All-In {allInAction.amount}
                  </button>
                )}
              </>
            ) : (
              <>
                <button
                  className={`btn ${preFold ? "btn-prefold-active" : "btn-prefold"}`}
                  onClick={() => setPreFold(!preFold)}
                >
                  {preFold ? "Pre-Fold ✓" : "Pre-Fold"}
                </button>
                <button className="btn btn-check" disabled>Check</button>
                <button className="btn btn-raise" disabled>Raise</button>
              </>
            )}
          </div>
        )}

        {/* Queue rebuy during active hand for busted players (not while all-in — they might still win) */}
        {engine.hand_active && me && me.chips === 0 && (me.can_rebuy || me.rebuy_queued) && (me.is_sitting_out || me.folded) && !me.all_in && (
          <div className="action-bar">
            {me.rebuy_queued ? (
              <button className="btn btn-cancel-rebuy" onClick={doCancelRebuy} disabled={actionLoading}>
                Cancel Queued Rebuy
              </button>
            ) : (
              <button className="btn btn-rebuy" onClick={doRebuy} disabled={actionLoading}>
                Queue Rebuy
              </button>
            )}
          </div>
        )}

        {/* Between hands */}
        {!engine.hand_active && !engine.game_over && (
          <div className="between-hands">
            <button className="btn btn-deal" onClick={doDeal} disabled={actionLoading || engine.paused}>
              Deal Now{dealTimeLeft !== null && !engine.paused ? ` (${Math.ceil(dealTimeLeft)}s)` : ""}
            </button>
            {isCreator && (
              <button className={`btn ${engine.paused ? "btn-resume" : "btn-pause"}`} onClick={doPause} disabled={actionLoading}>
                {engine.paused ? "▶ Resume" : "⏸ Pause"}
              </button>
            )}
            {me && me.chips === 0 && me.can_rebuy && (
              <button className="btn btn-rebuy" onClick={doRebuy} disabled={actionLoading}>
                Rebuy
              </button>
            )}
            {me && engine.my_cards.length > 0 && !engine.shown_cards?.includes(playerId!) && (
              <button className="btn btn-show-cards" onClick={doShowCards} disabled={actionLoading}>
                Show Cards
              </button>
            )}
          </div>
        )}
      </div>}

      {engine.game_over && (
        <div className="game-over-overlay">
          <div className="game-over-card">
            <h2>Game Over</h2>
            {engine.final_standings && engine.final_standings.length > 0 ? (
              <div className="standings-list">
                {engine.final_standings.map((s, i) => (
                  <div key={s.player_id} className={`standing-row ${i === 0 ? "winner" : ""}`}>
                    <span className="standing-place">
                      {i === 0 ? "\u{1F3C6}" : `#${s.place}`}
                    </span>
                    <span className="standing-name">{s.name}</span>
                    <span className="standing-chips">
                      {i === 0 ? `${s.chips} chips` : `Out hand #${s.eliminated_hand}`}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p>{engine.message}</p>
            )}
            <Link to="/" className="btn btn-primary">Back to Home</Link>
          </div>
        </div>
      )}
    </div>
  );
}
