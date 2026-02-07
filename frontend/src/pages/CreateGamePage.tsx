import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createGame } from "../api";

export default function CreateGamePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [startingChips, setStartingChips] = useState(1000);
  const [smallBlind, setSmallBlind] = useState(10);
  const [bigBlind, setBigBlind] = useState(20);
  const [maxPlayers, setMaxPlayers] = useState(9);
  const [allowRebuys, setAllowRebuys] = useState(true);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await createGame({
        creator_name: name.trim(),
        creator_pin: pin,
        starting_chips: startingChips,
        small_blind: smallBlind,
        big_blind: bigBlind,
        max_players: maxPlayers,
        allow_rebuys: allowRebuys,
      });
      // Store credentials in sessionStorage for lobby
      sessionStorage.setItem("playerId", res.player_id);
      sessionStorage.setItem("playerPin", pin);
      sessionStorage.setItem("playerName", name.trim());
      navigate(`/game/${res.code}`);
    } catch (err: any) {
      setError(err.message || "Failed to create game");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <h1>Create Game</h1>
      <form onSubmit={handleSubmit} className="form">
        <label>
          Your Name
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={20}
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
            required
          />
        </label>

        <label>
          Starting Chips
          <input
            type="number"
            min={100}
            max={100000}
            step={100}
            value={startingChips}
            onChange={(e) => setStartingChips(Number(e.target.value))}
          />
        </label>

        <div className="row">
          <label>
            Small Blind
            <input
              type="number"
              min={1}
              value={smallBlind}
              onChange={(e) => setSmallBlind(Number(e.target.value))}
            />
          </label>
          <label>
            Big Blind
            <input
              type="number"
              min={2}
              value={bigBlind}
              onChange={(e) => setBigBlind(Number(e.target.value))}
            />
          </label>
        </div>

        <label>
          Max Players (4–9)
          <input
            type="number"
            min={4}
            max={9}
            value={maxPlayers}
            onChange={(e) => setMaxPlayers(Number(e.target.value))}
          />
        </label>

        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={allowRebuys}
            onChange={(e) => setAllowRebuys(e.target.checked)}
          />
          Allow Rebuys
        </label>

        {error && <p className="error">{error}</p>}

        <button type="submit" className="btn btn-primary" disabled={loading || pin.length !== 4 || !name.trim()}>
          {loading ? "Creating…" : "Create Game"}
        </button>
      </form>
    </div>
  );
}
