import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createGame } from "../api";
import HelpModal from "../components/HelpModal";

export default function CreateGamePage() {
  const navigate = useNavigate();
  const [helpOpen, setHelpOpen] = useState(false);
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [startingChips, setStartingChips] = useState(1000);
  const [smallBlind, setSmallBlind] = useState(10);
  const [bigBlind, setBigBlind] = useState(20);
  const [maxPlayers, setMaxPlayers] = useState(9);
  const [allowRebuys, setAllowRebuys] = useState(true);
  const [maxRebuys, setMaxRebuys] = useState(1);
  const [rebuyCutoffMinutes, setRebuyCutoffMinutes] = useState(60);
  const [turnTimeout, setTurnTimeout] = useState(0);
  const [blindLevelDuration, setBlindLevelDuration] = useState(0);
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
        max_rebuys: allowRebuys ? maxRebuys : 0,
        rebuy_cutoff_minutes: allowRebuys ? rebuyCutoffMinutes : 0,
        turn_timeout: turnTimeout,
        blind_level_duration: blindLevelDuration,
      });
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
      <button className="help-btn" onClick={() => setHelpOpen(true)} aria-label="Help">?</button>
      <h1>Create Game</h1>
      <form onSubmit={handleSubmit} className="form">
        <fieldset className="form-section">
          <legend>Your Identity</legend>
          <label>
            Name
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
        </fieldset>

        <fieldset className="form-section">
          <legend>Game Settings</legend>
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

          <div className="row">
            <label>
              Max Players
              <input
                type="number"
                min={2}
                max={9}
                value={maxPlayers}
                onChange={(e) => setMaxPlayers(Number(e.target.value))}
              />
            </label>
            <label>
              Turn Timer
              <input
                type="number"
                min={0}
                max={300}
                step={5}
                value={turnTimeout}
                onChange={(e) => setTurnTimeout(Number(e.target.value))}
                placeholder="0 = off"
              />
            </label>
          </div>

          <label>
            Blind Level Duration (minutes)
            <input
              type="number"
              min={0}
              max={120}
              step={1}
              value={blindLevelDuration}
              onChange={(e) => setBlindLevelDuration(Number(e.target.value))}
              placeholder="0 = no increases"
            />
            {blindLevelDuration > 0 && (
              <span className="hint">Blinds increase every {blindLevelDuration} min</span>
            )}
          </label>

          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={allowRebuys}
              onChange={(e) => setAllowRebuys(e.target.checked)}
            />
            Allow Rebuys
          </label>

          {allowRebuys && (
            <div className="row rebuy-options">
              <label>
                Max Rebuys
                <input
                  type="number"
                  min={0}
                  max={99}
                  value={maxRebuys}
                  onChange={(e) => setMaxRebuys(Number(e.target.value))}
                  placeholder="0 = unlimited"
                />
                <span className="hint">{maxRebuys === 0 ? "Unlimited" : `${maxRebuys} allowed`}</span>
              </label>
              <label>
                Rebuy Cutoff (min)
                <input
                  type="number"
                  min={0}
                  max={480}
                  step={5}
                  value={rebuyCutoffMinutes}
                  onChange={(e) => setRebuyCutoffMinutes(Number(e.target.value))}
                  placeholder="0 = no cutoff"
                />
                <span className="hint">{rebuyCutoffMinutes === 0 ? "No cutoff" : `${rebuyCutoffMinutes} min`}</span>
              </label>
            </div>
          )}
        </fieldset>

        {error && <p className="error">{error}</p>}

        <button type="submit" className="btn btn-primary btn-lg" disabled={loading || pin.length !== 4 || !name.trim()}>
          {loading ? "Creating…" : "Create Game"}
        </button>
      </form>

      <HelpModal open={helpOpen} onClose={() => setHelpOpen(false)} title="Game Settings Help">
        <h3>Your Identity</h3>
        <dl>
          <dt>Name</dt>
          <dd>Your display name at the table (up to 20 characters).</dd>
          <dt>4-Digit PIN</dt>
          <dd>
            A simple password for your seat. You'll need it to reconnect if you
            drop — remember it!
          </dd>
        </dl>

        <h3>Game Settings</h3>
        <dl>
          <dt>Starting Chips</dt>
          <dd>How many chips each player begins with (100–100,000).</dd>
          <dt>Small Blind / Big Blind</dt>
          <dd>
            The forced bets posted each hand. The big blind is typically 2× the
            small blind.
          </dd>
          <dt>Max Players</dt>
          <dd>Seats available at the table (4–9).</dd>
          <dt>Turn Timer</dt>
          <dd>
            Seconds each player has to act. When time runs out, the player
            auto-checks or auto-folds. Set to <strong>0</strong> for unlimited time.
          </dd>
          <dt>Blind Level Duration</dt>
          <dd>
            Minutes between blind increases. The blinds double at each level
            on an auto-generated schedule. Set to <strong>0</strong> for fixed blinds.
          </dd>
          <dt>Allow Rebuys</dt>
          <dd>
            When enabled, busted players (0 chips) can rebuy back to the starting
            stack between hands.
          </dd>
          <dt>Max Rebuys</dt>
          <dd>
            How many times a player can rebuy. Set to <strong>0</strong> for unlimited.
          </dd>
          <dt>Rebuy Cutoff</dt>
          <dd>
            Minutes after game start when rebuys are no longer allowed.
            Set to <strong>0</strong> for no time limit.
          </dd>
        </dl>
      </HelpModal>
    </div>
  );
}
