import { useState, useEffect, useCallback } from "react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface AdminSummary {
  games_created_24h: number;
  games_cleaned_24h: number;
  active_games_count: number;
}

interface DailyCreation {
  date: string;
  count: number;
}

interface CompletionStats {
  completed: number;
  abandoned: number;
  never_started: number;
  total: number;
}

interface DailyStats {
  daily_creation: DailyCreation[];
  completion_stats: CompletionStats;
}

interface ActiveGame {
  code: string;
  status: string;
  creator_ip: string;
  created_at: number | null;
  player_count: number;
  player_names: string[];
  last_activity: number | null;
  seconds_since_activity: number | null;
}

/* ------------------------------------------------------------------ */
/*  API helper                                                         */
/* ------------------------------------------------------------------ */

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function adminFetch<T>(path: string, password: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${password}`,
    },
  });
  if (res.status === 401) throw new Error("Invalid password");
  if (res.status === 503)
    throw new Error("Admin not configured on server (set ADMIN_PASSWORD)");
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? "Request failed");
  }
  return res.json();
}

/* ------------------------------------------------------------------ */
/*  Formatting helpers                                                 */
/* ------------------------------------------------------------------ */

function timeAgo(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h ago`;
  return `${(seconds / 86400).toFixed(1)}d ago`;
}

function formatTimestamp(ts: number | null): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString();
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function LoginForm({
  onLogin,
  error,
}: {
  onLogin: (pw: string) => void;
  error: string;
}) {
  const [password, setPassword] = useState("");

  return (
    <div className="admin-login">
      <div className="admin-login-card">
        <h1>🔒 Admin</h1>
        <p>Enter the admin password to continue.</p>
        {error && <div className="error">{error}</div>}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onLogin(password);
          }}
        >
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            autoFocus
          />
          <button className="btn btn-primary btn-lg" type="submit">
            Login
          </button>
        </form>
      </div>
    </div>
  );
}

function SummaryCards({ data }: { data: AdminSummary }) {
  return (
    <div className="admin-summary">
      <div className="stat-card">
        <div className="stat-value">{data.games_created_24h}</div>
        <div className="stat-label">Created (24h)</div>
      </div>
      <div className="stat-card">
        <div className="stat-value">{data.games_cleaned_24h}</div>
        <div className="stat-label">Cleaned (24h)</div>
      </div>
      <div className="stat-card accent">
        <div className="stat-value">{data.active_games_count}</div>
        <div className="stat-label">Active Now</div>
      </div>
    </div>
  );
}

function DailyChart({ data }: { data: DailyCreation[] }) {
  const maxCount = Math.max(...data.map((d) => d.count), 1);

  return (
    <div className="admin-section">
      <h2>Daily Game Creation (30 days)</h2>
      <div className="bar-chart">
        {data.map((d) => (
          <div
            key={d.date}
            className="bar-col"
            title={`${d.date}: ${d.count} game${d.count !== 1 ? "s" : ""}`}
          >
            {d.count > 0 && <span className="bar-count">{d.count}</span>}
            <div
              className="bar-fill"
              style={{ height: `${(d.count / maxCount) * 100}%` }}
            />
          </div>
        ))}
      </div>
      <div className="bar-chart-x-axis">
        {data
          .filter((_, i) => i % 7 === 0 || i === data.length - 1)
          .map((d) => (
            <span key={d.date}>{d.date.slice(5)}</span>
          ))}
      </div>
    </div>
  );
}

function OutcomeStats({ data }: { data: CompletionStats }) {
  return (
    <div className="admin-section">
      <h2>Game Outcomes (30 days)</h2>
      <div className="admin-summary">
        <div className="stat-card completed">
          <div className="stat-value">{data.completed}</div>
          <div className="stat-label">Completed</div>
          <div className="stat-hint">Played to the end</div>
        </div>
        <div className="stat-card abandoned">
          <div className="stat-value">{data.abandoned}</div>
          <div className="stat-label">Abandoned</div>
          <div className="stat-hint">Started but not finished</div>
        </div>
        <div className="stat-card never-started">
          <div className="stat-value">{data.never_started}</div>
          <div className="stat-label">Never Started</div>
          <div className="stat-hint">Stayed in lobby</div>
        </div>
      </div>
    </div>
  );
}

function ActiveGamesTable({ games }: { games: ActiveGame[] }) {
  if (games.length === 0) {
    return (
      <div className="admin-section">
        <h2>Active Games</h2>
        <p className="muted">No active games right now.</p>
      </div>
    );
  }

  return (
    <div className="admin-section">
      <h2>Active Games ({games.length})</h2>
      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Status</th>
              <th>IP</th>
              <th>Created</th>
              <th>Players</th>
              <th>Last Activity</th>
            </tr>
          </thead>
          <tbody>
            {games.map((g) => (
              <tr key={g.code}>
                <td className="mono">{g.code}</td>
                <td>
                  <span className={`status-pill ${g.status}`}>{g.status}</span>
                </td>
                <td className="mono">{g.creator_ip}</td>
                <td>{formatTimestamp(g.created_at)}</td>
                <td>
                  {g.player_count}
                  <span className="player-names-hint">
                    {" "}
                    ({g.player_names.join(", ")})
                  </span>
                </td>
                <td>{timeAgo(g.seconds_since_activity)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main page component                                                */
/* ------------------------------------------------------------------ */

export default function AdminPage() {
  const [password, setPassword] = useState(
    () => sessionStorage.getItem("admin_pw") || ""
  );
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [summary, setSummary] = useState<AdminSummary | null>(null);
  const [dailyStats, setDailyStats] = useState<DailyStats | null>(null);
  const [activeGames, setActiveGames] = useState<ActiveGame[]>([]);

  const fetchData = useCallback(async (pw: string) => {
    if (!pw) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [s, d, a] = await Promise.all([
        adminFetch<AdminSummary>("/api/admin/summary", pw),
        adminFetch<DailyStats>("/api/admin/daily-stats", pw),
        adminFetch<{ games: ActiveGame[] }>("/api/admin/active-games", pw),
      ]);
      setSummary(s);
      setDailyStats(d);
      setActiveGames(a.games);
      setAuthenticated(true);
      sessionStorage.setItem("admin_pw", pw);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Unknown error";
      if (message === "Invalid password") {
        setAuthenticated(false);
        sessionStorage.removeItem("admin_pw");
      }
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleLogin = (pw: string) => {
    setPassword(pw);
    fetchData(pw);
  };

  const handleLogout = () => {
    setPassword("");
    setAuthenticated(false);
    sessionStorage.removeItem("admin_pw");
  };

  // Try auto-login from session storage on mount
  useEffect(() => {
    fetchData(password);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-refresh every 30 s
  useEffect(() => {
    if (!authenticated || !password) return;
    const id = setInterval(() => fetchData(password), 30_000);
    return () => clearInterval(id);
  }, [authenticated, password, fetchData]);

  /* ---------- Render ---------- */

  if (loading && !authenticated) {
    return (
      <div className="admin-login">
        <div className="loading-spinner" />
      </div>
    );
  }

  if (!authenticated) {
    return <LoginForm onLogin={handleLogin} error={error} />;
  }

  return (
    <div className="admin-page">
      <div className="admin-header">
        <h1>🔒 Admin Dashboard</h1>
        <div className="admin-header-actions">
          <button
            className="btn btn-secondary"
            onClick={() => fetchData(password)}
            disabled={loading}
          >
            {loading ? "..." : "↻ Refresh"}
          </button>
          <button className="btn btn-secondary" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      {summary && <SummaryCards data={summary} />}

      {dailyStats && (
        <>
          <DailyChart data={dailyStats.daily_creation} />
          <OutcomeStats data={dailyStats.completion_stats} />
        </>
      )}

      <ActiveGamesTable games={activeGames} />
    </div>
  );
}
