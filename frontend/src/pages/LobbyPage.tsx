import { useCallback, useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { buildWsUrl, getGame, toggleReady, startGame } from "../api";
import { useGameSocket } from "../useGameSocket";
import type { GameState, ConnectionInfo } from "../types";

export default function LobbyPage() {
  const { code } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const [game, setGame] = useState<GameState | null>(null);
  const [connInfo, setConnInfo] = useState<ConnectionInfo | null>(null);
  const [error, setError] = useState("");
  const [actionLoading, setActionLoading] = useState(false);

  const playerId = sessionStorage.getItem("playerId");
  const playerPin = sessionStorage.getItem("playerPin");

  // Not authenticated — must join/create first
  const notAuthenticated = !playerId || !playerPin;

  // WebSocket URL (only connect when authenticated)
  const wsUrl =
    code && playerId ? buildWsUrl(code, playerId) : null;

  const handleLobbyUpdate = useCallback((state: GameState) => {
    setGame(state);
  }, []);

  const handleConnectionInfo = useCallback((info: ConnectionInfo) => {
    setConnInfo(info);
  }, []);

  const { connected } = useGameSocket({
    url: notAuthenticated ? null : wsUrl,
    onLobbyUpdate: handleLobbyUpdate,
    onConnectionInfo: handleConnectionInfo,
  });

  // Fetch initial game state
  useEffect(() => {
    if (!code) return;
    getGame(code)
      .then(setGame)
      .catch((e) => setError(e.message));
  }, [code]);

  // Redirect to table when game becomes active
  useEffect(() => {
    if (game?.status === "active" && code) {
      navigate(`/game/${code}/table`);
    }
  }, [game?.status, code, navigate]);

  if (notAuthenticated) {
    return (
      <div className="page">
        <h1>Not Authenticated</h1>
        <p>You need to create or join a game first.</p>
        <Link to="/" className="btn btn-primary">
          Go Home
        </Link>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <h1>Error</h1>
        <p className="error">{error}</p>
        <Link to="/" className="btn btn-primary">
          Go Home
        </Link>
      </div>
    );
  }

  if (!game) {
    return (
      <div className="page">
        <p>Loading…</p>
      </div>
    );
  }

  const isCreator = playerId === game.creator_id;
  const me = game.players.find((p) => p.id === playerId);
  const allReady = game.players.length >= 2 && game.players.every((p) => p.ready);

  const handleReady = async () => {
    if (!code || !playerId || !playerPin) return;
    setActionLoading(true);
    try {
      const state = await toggleReady(code, {
        player_id: playerId,
        pin: playerPin,
      });
      setGame(state);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleStart = async () => {
    if (!code || !playerId || !playerPin) return;
    setActionLoading(true);
    try {
      const state = await startGame(code, {
        player_id: playerId,
        pin: playerPin,
      });
      setGame(state);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  if (game.status === "active") {
    return (
      <div className="page">
        <h1>Game Started!</h1>
        <p>Game <strong>{game.code}</strong> is now active.</p>
        <p className="muted">(Gameplay will be implemented in Phase 2)</p>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="lobby-header">
        <h1>Lobby</h1>
        <div className="game-code">
          Code: <strong>{game.code}</strong>
        </div>
        <div className={`connection-status ${connected ? "online" : "offline"}`}>
          {connected ? "● Connected" : "○ Disconnected"}
        </div>
      </div>

      <div className="settings-summary">
        <span>Chips: {game.settings.starting_chips}</span>
        <span>
          Blinds: {game.settings.small_blind}/{game.settings.big_blind}
        </span>
        <span>Max: {game.settings.max_players} players</span>
        {game.settings.allow_rebuys && <span>Rebuys: On</span>}
      </div>

      <div className="player-list">
        <h2>
          Players ({game.players.length}/{game.settings.max_players})
        </h2>
        {game.players.map((p) => (
          <div
            key={p.id}
            className={`player-row ${p.id === playerId ? "me" : ""}`}
          >
            <span className={`conn-dot ${connInfo?.connected_players.includes(p.id) ? "on" : p.connected ? "on" : "off"}`} />
            <span className="player-name">
              {p.name}
              {p.is_creator && " ★"}
              {p.id === playerId && " (you)"}
            </span>
            <span className={`ready-badge ${p.ready ? "ready" : "not-ready"}`}>
              {p.ready ? "Ready" : "Not Ready"}
            </span>
          </div>
        ))}
      </div>

      <div className="lobby-actions">
        <button
          className={`btn ${me?.ready ? "btn-secondary" : "btn-primary"}`}
          onClick={handleReady}
          disabled={actionLoading}
        >
          {me?.ready ? "Unready" : "Ready Up"}
        </button>

        {isCreator && (
          <button
            className="btn btn-primary"
            onClick={handleStart}
            disabled={actionLoading || !allReady}
            title={!allReady ? "All players must be ready" : ""}
          >
            Start Game
          </button>
        )}
      </div>

      <p className="share-hint">
        Share code <strong>{game.code}</strong> with friends to join!
      </p>
    </div>
  );
}
