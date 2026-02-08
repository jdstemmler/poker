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
  const [copied, setCopied] = useState(false);

  const playerId = sessionStorage.getItem("playerId");
  const playerPin = sessionStorage.getItem("playerPin");

  const notAuthenticated = !playerId || !playerPin;

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

  useEffect(() => {
    if (!code) return;
    getGame(code)
      .then(setGame)
      .catch((e) => setError(e.message));
  }, [code]);

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
        <Link to="/" className="btn btn-primary">Go Home</Link>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <h1>Error</h1>
        <p className="error">{error}</p>
        <Link to="/" className="btn btn-primary">Go Home</Link>
      </div>
    );
  }

  if (!game) {
    return (
      <div className="page"><div className="loading-spinner" /><p>Loading…</p></div>
    );
  }

  const isCreator = playerId === game.creator_id;
  const me = game.players.find((p) => p.id === playerId);
  const allReady = game.players.length >= 2 && game.players.every((p) => p.ready);
  const readyCount = game.players.filter((p) => p.ready).length;

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
        <p>Redirecting to table…</p>
      </div>
    );
  }

  return (
    <div className="page lobby-page">
      <div className="lobby-header">
        <h1>Lobby</h1>
        <div className="lobby-code">
          <span className="lobby-code-value">{game.code}</span>
          <span className="lobby-code-hint">Share this code with friends</span>
        </div>
        <button
          className="btn btn-secondary btn-copy-link"
          onClick={() => {
            const url = `${window.location.origin}/join/${game.code}`;
            navigator.clipboard.writeText(url).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            });
          }}
        >
          {copied ? "✓ Copied!" : "Copy Join Link"}
        </button>
        <span className={`conn-status-pill ${connected ? "on" : "off"}`}>
          <span className="conn-dot-sm" />
          {connected ? "Connected" : "Disconnected"}
        </span>
      </div>

      <div className="settings-pills">
        <span className="pill">💰 {game.settings.starting_chips}</span>
        <span className="pill">🎯 {game.settings.small_blind}/{game.settings.big_blind}</span>
        <span className="pill">👥 Max {game.settings.max_players}</span>
        {game.settings.allow_rebuys && <span className="pill">🔄 Rebuys</span>}
        {game.settings.turn_timeout > 0 && <span className="pill">⏱ {game.settings.turn_timeout}s</span>}
        {game.settings.blind_level_duration > 0 && <span className="pill">📈 Blinds every {game.settings.blind_level_duration}m</span>}
      </div>

      <div className="player-list">
        <h2 className="section-heading">
          Players
          <span className="ready-count">{readyCount}/{game.players.length} ready</span>
        </h2>
        {game.players.map((p) => {
          const isOnline = connInfo?.connected_players.includes(p.id) ?? p.connected;
          return (
            <div
              key={p.id}
              className={`player-row lobby-player ${p.id === playerId ? "me" : ""}`}
            >
              <span className="player-identity">
                <span className={`conn-dot ${isOnline ? "on" : "off"}`} />
                <span className="player-name">
                  {p.name}
                  {p.is_creator && <span className="creator-star"> ★</span>}
                  {p.id === playerId && <span className="you-tag">you</span>}
                </span>
              </span>
              <span className={`ready-badge ${p.ready ? "ready" : "not-ready"}`}>
                {p.ready ? "✓ Ready" : "Waiting"}
              </span>
            </div>
          );
        })}
      </div>

      <div className="lobby-actions">
        <button
          className={`btn btn-lg ${me?.ready ? "btn-secondary" : "btn-primary"}`}
          onClick={handleReady}
          disabled={actionLoading}
        >
          {me?.ready ? "Unready" : "Ready Up"}
        </button>

        {isCreator && (
          <button
            className="btn btn-primary btn-lg"
            onClick={handleStart}
            disabled={actionLoading || !allReady}
            title={!allReady ? "All players must be ready" : ""}
          >
            Start Game
          </button>
        )}
      </div>
    </div>
  );
}
