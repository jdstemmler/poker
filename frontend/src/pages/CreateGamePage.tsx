import { useState, useCallback, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createGame } from "../api";
import HelpModal from "../components/HelpModal";

/** Numeric input that avoids leading zeros and selects all on focus.
 *  When `emptyValue` is provided and the value equals it, the field
 *  renders empty so the placeholder is visible — no need to delete first. */
function NumericInput({
  value,
  onChange,
  placeholder,
  emptyValue,
  ...rest
}: {
  value: number;
  onChange: (v: number) => void;
  placeholder?: string;
  emptyValue?: number;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type" | "placeholder">) {
  const shouldBeEmpty = emptyValue !== undefined && value === emptyValue;
  const [display, setDisplay] = useState(shouldBeEmpty ? "" : String(value));
  const [focused, setFocused] = useState(false);

  // Sync display when value changes externally (not while user is typing)
  useEffect(() => {
    if (!focused) {
      const empty = emptyValue !== undefined && value === emptyValue;
      setDisplay(empty ? "" : String(value));
    }
  }, [value, emptyValue, focused]);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const raw = e.target.value;
      // Allow empty field
      if (raw === "" || raw === "-") {
        setDisplay(raw);
        onChange(emptyValue ?? 0);
        return;
      }
      const n = Number(raw);
      if (!isNaN(n)) {
        setDisplay(raw.replace(/^0+(?=\d)/, "")); // strip leading zeros
        onChange(n);
      }
    },
    [onChange, emptyValue],
  );

  const handleFocus = useCallback((e: React.FocusEvent<HTMLInputElement>) => {
    setFocused(true);
    // Delay select to work around browsers that clear selection after focus
    const input = e.target;
    requestAnimationFrame(() => {
      if (input.value) input.select();
    });
  }, []);

  const handleBlur = useCallback(() => {
    setFocused(false);
    const empty = emptyValue !== undefined && value === emptyValue;
    setDisplay(empty ? "" : String(value));
  }, [value, emptyValue]);

  return (
    <input
      type="text"
      inputMode="numeric"
      value={display}
      onChange={handleChange}
      onFocus={handleFocus}
      onBlur={handleBlur}
      placeholder={placeholder}
      {...rest}
    />
  );
}

/** Mirror the backend _round_blind logic for preview.
 *  Uses banker's rounding to match Python's round(). */
function bankersRound(n: number): number {
  const floor = Math.floor(n);
  const frac = n - floor;
  if (Math.abs(frac - 0.5) < 1e-9) return floor % 2 === 0 ? floor : floor + 1;
  return Math.round(n);
}

function roundBlind(value: number): number {
  const v = bankersRound(value);
  if (v >= 100) return bankersRound(v / 10) * 10;
  if (v >= 10) return bankersRound(v / 5) * 5;
  return Math.max(1, v);
}

/** Build a blind schedule preview (same algorithm as backend). */
function buildSchedulePreview(startSb: number, startBb: number, multiplier: number): [number, number][] {
  const schedule: [number, number][] = [[startSb, startBb]];
  let sb = startSb;
  let bb = startBb;
  for (let i = 0; i < 10; i++) {
    sb *= multiplier;
    bb *= multiplier;
    schedule.push([roundBlind(sb), roundBlind(bb)]);
  }
  return schedule;
}

export default function CreateGamePage() {
  const navigate = useNavigate();
  const [helpOpen, setHelpOpen] = useState(false);
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [startingChips, setStartingChips] = useState(1000);
  const [smallBlind, setSmallBlind] = useState(10);
  const [bigBlind, setBigBlind] = useState(20);
  const [allowRebuys, setAllowRebuys] = useState(true);
  const [maxRebuys, setMaxRebuys] = useState(1);
  const [rebuyCutoffMinutes, setRebuyCutoffMinutes] = useState(60);
  const [turnTimeout, setTurnTimeout] = useState(0);
  const [blindLevelDuration, setBlindLevelDuration] = useState(0);
  const [blindMultiplier, setBlindMultiplier] = useState(2.0);
  const [autoDealEnabled, setAutoDealEnabled] = useState(true);
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
        allow_rebuys: allowRebuys,
        max_rebuys: allowRebuys ? maxRebuys : 0,
        rebuy_cutoff_minutes: allowRebuys ? rebuyCutoffMinutes : 0,
        turn_timeout: turnTimeout,
        blind_level_duration: blindLevelDuration,
        blind_multiplier: blindLevelDuration > 0 ? blindMultiplier : 2.0,
        auto_deal_enabled: autoDealEnabled,
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
      <Link to="/" className="back-arrow" aria-label="Back to Home">←</Link>
      <h1>Create Game</h1>
      <form onSubmit={handleSubmit} className="form" autoComplete="off" data-1p-ignore>
        <fieldset className="form-section">
          <legend>Your Identity</legend>
          <label>
            Name
            <input
              type="text"
              autoComplete="off"
              data-1p-ignore
              data-lpignore="true"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={20}
              placeholder="Display name"
              required
            />
          </label>

          <label>
            Choose a 4-Digit PIN
            <input
              type="text"
              inputMode="numeric"
              autoComplete="off"
              data-1p-ignore
              data-lpignore="true"
              pattern="\d{4}"
              maxLength={4}
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
              placeholder="Pick any 4 digits"
              className="pin-input"
              required
            />
            <span className="hint">This is YOUR password — pick any 4 digits and remember them</span>
          </label>
        </fieldset>

        <fieldset className="form-section">
          <legend>Chips &amp; Blinds</legend>
          <label>
            Starting Chips
            <NumericInput
              value={startingChips}
              onChange={setStartingChips}
              placeholder="1000"
            />
          </label>

          <div className="row">
            <label>
              Small Blind
              <NumericInput
                value={smallBlind}
                onChange={setSmallBlind}
                placeholder="10"
              />
            </label>
            <label>
              Big Blind
              <NumericInput
                value={bigBlind}
                onChange={setBigBlind}
                placeholder="20"
              />
            </label>
          </div>

          <label>
            Blind Level Duration (min)
            <NumericInput
              value={blindLevelDuration}
              onChange={setBlindLevelDuration}
              placeholder="0 = no increases"
              emptyValue={0}
            />
            {blindLevelDuration > 0 && (
              <span className="hint">Blinds increase every {blindLevelDuration} min</span>
            )}
          </label>

          {blindLevelDuration > 0 && (
            <>
              <label>
                Blind Multiplier
                <div className="multiplier-options">
                  {[1.5, 2, 3, 4].map((m) => (
                    <button
                      key={m}
                      type="button"
                      className={`multiplier-btn${blindMultiplier === m ? " active" : ""}`}
                      onClick={() => setBlindMultiplier(m)}
                    >
                      {m}×
                    </button>
                  ))}
                </div>
                <span className="hint">Blinds multiply by {blindMultiplier}× each level</span>
              </label>

              <div className="blind-schedule-preview">
                <span className="schedule-title">Blind Schedule Preview</span>
                <div className="schedule-table">
                  {buildSchedulePreview(smallBlind, bigBlind, blindMultiplier).map(([sb, bb], i) => (
                    <div key={i} className={`schedule-row${i === 0 ? " current" : ""}`}>
                      <span className="schedule-level">L{i + 1}</span>
                      <span className="schedule-blinds">{sb}/{bb}</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </fieldset>

        <fieldset className="form-section">
          <legend>Timing</legend>
          <label>
            Turn Timer (sec)
            <NumericInput
              value={turnTimeout}
              onChange={setTurnTimeout}
              placeholder="0 = off"
              emptyValue={0}
            />
          </label>

          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={autoDealEnabled}
              onChange={(e) => setAutoDealEnabled(e.target.checked)}
            />
            Auto Deal Next Hand
            <span className="hint">When enabled, the next hand deals automatically after 10 seconds</span>
          </label>
        </fieldset>

        <fieldset className="form-section">
          <legend>Rebuys</legend>
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
                <NumericInput
                  value={maxRebuys}
                  onChange={setMaxRebuys}
                  placeholder="0 = unlimited"
                  emptyValue={0}
                />
                <span className="hint">{maxRebuys === 0 ? "Unlimited" : `${maxRebuys} allowed`}</span>
              </label>
              <label>
                Rebuy Cutoff (min)
                <NumericInput
                  value={rebuyCutoffMinutes}
                  onChange={setRebuyCutoffMinutes}
                  placeholder="0 = no cutoff"
                  emptyValue={0}
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
            <strong>You choose this yourself</strong> — pick any four digits.
            You'll need it to reconnect if you drop — remember it!
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
          <dt>Blind Level Duration</dt>
          <dd>
            Minutes between blind increases. Set to <strong>0</strong> for fixed blinds.
          </dd>
          <dt>Blind Multiplier</dt>
          <dd>
            How much the blinds multiply each level (e.g. 2× means blinds
            double). Only applies when blind level duration is set.
          </dd>
        </dl>

        <h3>Timing</h3>
        <dl>
          <dt>Turn Timer</dt>
          <dd>
            Seconds each player has to act. When time runs out, the player
            auto-checks or auto-folds. Set to <strong>0</strong> for unlimited time.
          </dd>
          <dt>Auto Deal Next Hand</dt>
          <dd>
            When enabled, the next hand is dealt automatically after a 10-second
            delay. When disabled, the host must deal each hand manually.
          </dd>
        </dl>

        <h3>Rebuys</h3>
        <dl>
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
