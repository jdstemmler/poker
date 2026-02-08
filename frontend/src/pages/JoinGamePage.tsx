import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { joinGame } from "../api";

export default function JoinGamePage() {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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
        ? `/game/${code.toUpperCase()}`
        : `/game/${code.toUpperCase()}/lobby`;
      navigate(dest);
    } catch (err: any) {
      setError(err.message || "Failed to join game");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
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
    </div>
  );
}
