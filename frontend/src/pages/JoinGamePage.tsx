import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { joinGame } from "../api";
import HelpModal from "../components/HelpModal";

export default function JoinGamePage() {
  const navigate = useNavigate();
  const { code: urlCode } = useParams<{ code?: string }>();
  const [code, setCode] = useState(urlCode?.toUpperCase() ?? "");
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await joinGame(code.toUpperCase(), {
        player_name: name.trim(),
        player_pin: pin,
      });
      sessionStorage.setItem("playerId", res.player_id);
      sessionStorage.setItem("playerPin", pin);
      sessionStorage.setItem("playerName", name.trim());
      // Navigate to table if game is active, lobby otherwise
      const dest = res.game.status === "active"
        ? `/game/${code.toUpperCase()}/table`
        : `/game/${code.toUpperCase()}`;
      navigate(dest);
    } catch (err: any) {
      setError(err.message || "Failed to join game");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <button className="help-btn" onClick={() => setHelpOpen(true)} aria-label="Help">?</button>
      <h1>Join Game</h1>
      <form onSubmit={handleSubmit} className="form">
        <label>
          Game Code
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase().slice(0, 6))}
            maxLength={6}
            placeholder="e.g. ABC123"
            className="code-input"
            required
          />
        </label>

        <label>
          Your Name
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={20}
            placeholder="Display name"
            required
          />
        </label>

        <label>
          4-Digit PIN
          <input
            type="password"
            inputMode="numeric"
            pattern="\d{4}"
            maxLength={4}
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
            placeholder="••••"
            required
          />
        </label>

        {error && <p className="error">{error}</p>}

        <button
          type="submit"
          className="btn btn-primary btn-lg"
          disabled={loading || code.length < 4 || pin.length !== 4 || !name.trim()}
        >
          {loading ? "Joining…" : "Join Game"}
        </button>
      </form>

      <HelpModal open={helpOpen} onClose={() => setHelpOpen(false)} title="Joining a Game">
        <h3>What You Need</h3>
        <dl>
          <dt>Game Code</dt>
          <dd>
            The 6-character code shared by the game creator. You can also join
            via a direct link — the code will be filled in automatically.
          </dd>
          <dt>Your Name</dt>
          <dd>
            Pick a display name (up to 20 characters). This is how other players
            will see you at the table.
          </dd>
          <dt>4-Digit PIN</dt>
          <dd>
            A simple password that secures your seat. If you get disconnected,
            use the <strong>same name and PIN</strong> to reconnect — even if the
            game has already started.
          </dd>
        </dl>

        <h3>Good to Know</h3>
        <ul>
          <li>You can only join a game that's still in the lobby (not yet started) unless you're reconnecting.</li>
          <li>Names are case-insensitive — "Alice" and "alice" are the same player.</li>
          <li>If the game has already started, reconnecting will take you straight to the table.</li>
        </ul>
      </HelpModal>
    </div>
  );
}
