/** Game Table Page — main gameplay view. */

import { useCallback, useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  buildWsUrl,
  getEngineState,
  sendAction,
  dealNextHand,
  requestRebuy,
  getGame,
} from "../api";
import { useGameSocket } from "../useGameSocket";
import { CardList } from "../components/CardDisplay";
import type { EngineState, GameState } from "../types";

export default function TablePage() {
  const { code } = useParams<{ code: string }>();
  const [engine, setEngine] = useState<EngineState | null>(null);
  const [lobbyGame, setLobbyGame] = useState<GameState | null>(null);
  const [error, setError] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [raiseAmount, setRaiseAmount] = useState(0);

  const playerId = sessionStorage.getItem("playerId");
  const playerPin = sessionStorage.getItem("playerPin");
  const notAuthenticated = !playerId || !playerPin;

  const wsUrl = code && playerId ? buildWsUrl(code, playerId) : null;

  const handleEngineUpdate = useCallback((state: EngineState) => {
    setEngine(state);
  }, []);

  const handleLobbyUpdate = useCallback((state: GameState) => {
    setLobbyGame(state);
  }, []);

  const { connected } = useGameSocket({
    url: notAuthenticated ? null : wsUrl,
    onEngineUpdate: handleEngineUpdate,
    onLobbyUpdate: handleLobbyUpdate,
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

  // Update raise slider when valid actions change
  useEffect(() => {
    if (!engine) return;
    const raiseAction = engine.valid_actions.find((a) => a.action === "raise");
    if (raiseAction?.min_amount) {
      setRaiseAmount(raiseAction.min_amount);
    }
  }, [engine?.valid_actions]);

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
    return <div className="page"><p>Loading game…</p></div>;
  }

  const isCreator = lobbyGame?.creator_id === playerId;
  const me = engine.players.find((p) => p.player_id === playerId);
  const isMyTurn = engine.action_on === playerId;

  const doAction = async (action: string, amount?: number) => {
    if (!code || !playerId || !playerPin) return;
    setActionLoading(true);
    setError("");
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

  // Find valid actions
  const canFold = engine.valid_actions.some((a) => a.action === "fold");
  const canCheck = engine.valid_actions.some((a) => a.action === "check");
  const callAction = engine.valid_actions.find((a) => a.action === "call");
  const raiseAction = engine.valid_actions.find((a) => a.action === "raise");
  const allInAction = engine.valid_actions.find((a) => a.action === "all_in");

  return (
    <div className="page table-page">
      {/* Header */}
      <div className="table-header">
        <span className="game-code">
          {engine.game_code} — Hand #{engine.hand_number}
        </span>
        <span className={`connection-status ${connected ? "online" : "offline"}`}>
          {connected ? "●" : "○"}
        </span>
      </div>

      {/* Street & Pot */}
      <div className="table-info">
        <span className="street-label">{engine.street.toUpperCase()}</span>
        <span className="pot-label">Pot: {engine.pot}</span>
      </div>

      {/* Community Cards */}
      <div className="community-cards">
        {engine.community_cards.length > 0 ? (
          <CardList cards={engine.community_cards} />
        ) : (
          <span className="muted">—</span>
        )}
      </div>

      {/* My Hole Cards */}
      {me && !me.folded && engine.my_cards.length > 0 && (
        <div className="my-cards">
          <CardList cards={engine.my_cards} />
        </div>
      )}

      {/* Players */}
      <div className="player-list">
        {engine.players.map((p) => {
          const isDealer = p.player_id === engine.dealer_player_id;
          const isAction = p.player_id === engine.action_on;
          const isMe = p.player_id === playerId;

          return (
            <div
              key={p.player_id}
              className={`player-row table-player ${isMe ? "me" : ""} ${isAction ? "action-on" : ""} ${p.folded ? "folded" : ""}`}
            >
              <div className="player-top">
                <span className="player-name">
                  {isDealer && <span className="dealer-btn">D</span>}
                  {p.name}
                  {isMe && " (you)"}
                </span>
                <span className="player-chips">{p.chips}</span>
              </div>
              <div className="player-bottom">
                {p.folded && <span className="status-tag folded-tag">Folded</span>}
                {p.all_in && <span className="status-tag allin-tag">All-In</span>}
                {p.is_sitting_out && <span className="status-tag sit-tag">Sitting Out</span>}
                {p.bet_this_round > 0 && (
                  <span className="status-tag bet-tag">Bet: {p.bet_this_round}</span>
                )}
                {/* Show cards at showdown */}
                {engine.showdown && p.hole_cards && !p.folded && (
                  <CardList cards={p.hole_cards} />
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Hand Result */}
      {engine.last_hand_result && !engine.hand_active && (
        <div className="hand-result">
          <h3>Hand Result</h3>
          {engine.last_hand_result.winners.map((w, i) => (
            <p key={i}>
              <strong>{w.name}</strong> wins {w.winnings} — {w.hand}
            </p>
          ))}
        </div>
      )}

      {/* Error */}
      {error && <p className="error">{error}</p>}

      {/* Actions */}
      {isMyTurn && engine.hand_active && (
        <div className="action-bar">
          {canFold && (
            <button
              className="btn btn-fold"
              onClick={() => doAction("fold")}
              disabled={actionLoading}
            >
              Fold
            </button>
          )}
          {canCheck && (
            <button
              className="btn btn-check"
              onClick={() => doAction("check")}
              disabled={actionLoading}
            >
              Check
            </button>
          )}
          {callAction && (
            <button
              className="btn btn-call"
              onClick={() => doAction("call")}
              disabled={actionLoading}
            >
              Call {callAction.amount}
            </button>
          )}
          {raiseAction && (
            <div className="raise-controls">
              <input
                type="range"
                min={raiseAction.min_amount}
                max={raiseAction.max_amount}
                value={raiseAmount}
                onChange={(e) => setRaiseAmount(Number(e.target.value))}
                className="raise-slider"
              />
              <button
                className="btn btn-raise"
                onClick={() => doAction("raise", raiseAmount)}
                disabled={actionLoading}
              >
                Raise {raiseAmount}
              </button>
            </div>
          )}
          {allInAction && !raiseAction && (
            <button
              className="btn btn-allin"
              onClick={() => doAction("all_in")}
              disabled={actionLoading}
            >
              All-In {allInAction.amount}
            </button>
          )}
        </div>
      )}

      {/* Between hands */}
      {!engine.hand_active && !engine.game_over && (
        <div className="between-hands">
          {isCreator && (
            <button
              className="btn btn-primary"
              onClick={doDeal}
              disabled={actionLoading}
            >
              Deal Next Hand
            </button>
          )}
          {me && me.chips === 0 && (
            <button
              className="btn btn-secondary"
              onClick={doRebuy}
              disabled={actionLoading}
            >
              Rebuy
            </button>
          )}
        </div>
      )}

      {engine.game_over && (
        <div className="game-over">
          <h2>Game Over</h2>
          <p>{engine.message}</p>
          <Link to="/" className="btn btn-primary">Back to Home</Link>
        </div>
      )}
    </div>
  );
}
