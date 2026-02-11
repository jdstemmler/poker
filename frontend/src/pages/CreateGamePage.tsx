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

/** Standard tournament blind values: factors [1,1.5,2,2.5,3,4,5,6,8] × decade */
const STANDARD_BLINDS = [
  1, 2, 3, 4, 5, 6, 8,
  10, 15, 20, 25, 30, 40, 50, 60, 80,
  100, 150, 200, 250, 300, 400, 500, 600, 800,
  1000, 1500, 2000, 2500, 3000, 4000, 5000, 6000, 8000,
  10000, 15000, 20000, 25000, 30000, 40000, 50000, 60000, 80000,
  100000,
];

/** Snap a value to the nearest standard tournament blind amount. */
function niceBlind(value: number): number {
  if (value <= 1) return 1;
  const v = Math.round(value);
  let lo = 0;
  let hi = STANDARD_BLINDS.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (STANDARD_BLINDS[mid] < v) lo = mid + 1;
    else hi = mid;
  }
  if (lo === 0) return STANDARD_BLINDS[0];
  if (lo >= STANDARD_BLINDS.length) return STANDARD_BLINDS[STANDARD_BLINDS.length - 1];
  const before = STANDARD_BLINDS[lo - 1];
  const after = STANDARD_BLINDS[lo];
  return (value - before) <= (after - value) ? before : after;
}

/** Build a blind schedule preview matching the backend algorithm.
 *  Phase 1 (~half): linear. Phase 2: geometric to starting_chips.
 *  Phase 3 (overtime): 1.5× per level until BB ≥ 3× chips. */
function buildTargetSchedulePreview(
  startingChips: number,
  levelDurationMin: number,
  targetGameTimeHrs: number,
): [number, number][] {
  const bbInitial = Math.max(2, niceBlind(startingChips / 100));

  const totalMinutes = targetGameTimeHrs * 60;
  const nLevels = Math.max(3, Math.floor(totalMinutes / levelDurationMin));

  const phase1Count = Math.max(2, Math.round(nLevels * 0.5));
  const phase2Count = (nLevels + 2) - phase1Count; // +2 buffer beyond target

  const scheduleBb: number[] = [];

  // Phase 1: linear
  for (let i = 0; i < phase1Count; i++) {
    scheduleBb.push(niceBlind(bbInitial * (i + 1)));
  }

  // Phase 2: geometric
  const lastBb = scheduleBb[scheduleBb.length - 1];
  const bbTarget = startingChips;
  if (phase2Count > 0 && lastBb < bbTarget) {
    let ratio = Math.pow(bbTarget / lastBb, 1.0 / Math.max(1, phase2Count - 1));
    ratio = Math.max(ratio, 1.2);
    for (let i = 1; i <= phase2Count; i++) {
      scheduleBb.push(niceBlind(lastBb * Math.pow(ratio, i)));
    }
  }

  // Phase 3: overtime at 1.5× until BB ≥ 3× starting chips
  const overtimeCap = startingChips * 3;
  while (scheduleBb[scheduleBb.length - 1] < overtimeCap) {
    const nxt = niceBlind(scheduleBb[scheduleBb.length - 1] * 1.5);
    scheduleBb.push(nxt > scheduleBb[scheduleBb.length - 1] ? nxt : scheduleBb[scheduleBb.length - 1] + 1);
  }

  // Build (SB, BB) tuples
  const schedule: [number, number][] = scheduleBb.map((bb) => [
    Math.max(1, Math.floor(bb / 2)),
    bb,
  ]);

  // Deduplicate consecutive identical levels
  const deduped: [number, number][] = [schedule[0]];
  for (let i = 1; i < schedule.length; i++) {
    const [ps, pb] = deduped[deduped.length - 1];
    const [s, b] = schedule[i];
    if (s !== ps || b !== pb) deduped.push([s, b]);
  }
  return deduped;
}

export default function CreateGamePage() {
  const navigate = useNavigate();
  const [helpOpen, setHelpOpen] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [startingChips, setStartingChips] = useState(5000);
  const [targetGameTime, setTargetGameTime] = useState(4);
  const [blindLevelDuration, setBlindLevelDuration] = useState(20);
  const [allowRebuys, setAllowRebuys] = useState(true);
  const [maxRebuys, setMaxRebuys] = useState(1);
  const [rebuyCutoffMinutes, setRebuyCutoffMinutes] = useState(60);
  const [turnTimeout, setTurnTimeout] = useState(0);
  const [autoDealEnabled, setAutoDealEnabled] = useState(true);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const blindsIncrease = targetGameTime > 0;
  const bbInitial = Math.max(2, niceBlind(startingChips / 100));
  const sbInitial = Math.max(1, Math.floor(bbInitial / 2));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await createGame({
        creator_name: name.trim(),
        creator_pin: pin,
        starting_chips: startingChips,
        allow_rebuys: allowRebuys,
        max_rebuys: allowRebuys ? maxRebuys : 0,
        rebuy_cutoff_minutes: allowRebuys ? rebuyCutoffMinutes : 0,
        turn_timeout: turnTimeout,
        blind_level_duration: blindLevelDuration,
        target_game_time: targetGameTime,
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
              placeholder="5000"
            />
            <span className="hint">Starting blinds: {sbInitial}/{bbInitial}</span>
          </label>

          <div className="row">
            <label>
              Target Game Time (hours)
              <NumericInput
                value={targetGameTime}
                onChange={setTargetGameTime}
                placeholder="0 = fixed blinds"
                emptyValue={0}
              />
              <span className="hint">{blindsIncrease ? `~${targetGameTime}h game` : "Fixed blinds"}</span>
            </label>

            {blindsIncrease && (
              <label>
                Level Duration (min)
                <NumericInput
                  value={blindLevelDuration}
                  onChange={(v) => setBlindLevelDuration(Math.max(5, Math.min(60, v)))}
                  placeholder="20"
                />
                <span className="hint">Every {blindLevelDuration} min</span>
              </label>
            )}
          </div>

          {blindsIncrease && (
            <>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setScheduleOpen(true)}
                style={{ marginTop: "0.25rem" }}
              >
                View Blind Schedule
              </button>
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

      {/* Blind Schedule Modal */}
      {blindsIncrease && scheduleOpen && (
        <div className="help-backdrop" onClick={() => setScheduleOpen(false)}>
          <div className="help-modal" onClick={(e) => e.stopPropagation()}>
            <div className="help-modal-header">
              <h2>Blind Schedule</h2>
              <button className="help-modal-close" onClick={() => setScheduleOpen(false)} aria-label="Close">✕</button>
            </div>
            <div className="help-modal-body">
              <div className="schedule-table">
                {buildTargetSchedulePreview(startingChips, blindLevelDuration, targetGameTime).map(([sb, bb], i) => {
                  const totalMin = i * blindLevelDuration;
                  const hrs = Math.floor(totalMin / 60);
                  const mins = totalMin % 60;
                  const timeStr = `+${hrs}:${String(mins).padStart(2, "0")}`;
                  return (
                    <div key={i} className={`schedule-row${i === 0 ? " current" : ""}`}>
                      <span className="schedule-level">L{i + 1}</span>
                      <span className="schedule-blinds">{sb}/{bb}</span>
                      <span className="schedule-time">{timeStr}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

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
          <dd>How many chips each player begins with (100–100,000). Starting blinds are automatically calculated as chips / 50.</dd>
          <dt>Target Game Time</dt>
          <dd>
            How long you want the game to last. Blinds are calculated automatically
            using geometric progression to reach all-in level by the target time.
            Set to <strong>0</strong> for fixed blinds (no increases).
          </dd>
          <dt>Level Duration</dt>
          <dd>
            Minutes between blind increases (5–60 min). Only applies when target
            game time is set.
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
