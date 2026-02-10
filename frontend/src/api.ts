/** API client for communicating with the backend. */

import type {
  CreateGameResponse,
  EngineState,
  GameState,
  JoinGameResponse,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? "Request failed");
  }
  return res.json() as Promise<T>;
}

export function createGame(data: {
  creator_name: string;
  creator_pin: string;
  starting_chips?: number;
  small_blind?: number;
  big_blind?: number;
  max_players?: number;
  allow_rebuys?: boolean;
  max_rebuys?: number;
  rebuy_cutoff_minutes?: number;
  turn_timeout?: number;
  blind_level_duration?: number;
  blind_multiplier?: number;
  auto_deal_enabled?: boolean;
}): Promise<CreateGameResponse> {
  return request("/api/games", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function joinGame(
  code: string,
  data: { player_name: string; player_pin: string }
): Promise<JoinGameResponse> {
  return request(`/api/games/${code}/join`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function getGame(code: string): Promise<GameState> {
  return request(`/api/games/${code}`);
}

export function toggleReady(
  code: string,
  data: { player_id: string; pin: string }
): Promise<GameState> {
  return request(`/api/games/${code}/ready`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function startGame(
  code: string,
  data: { player_id: string; pin: string }
): Promise<GameState> {
  return request(`/api/games/${code}/start`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function leaveGame(
  code: string,
  data: { player_id: string; pin: string }
): Promise<GameState> {
  return request(`/api/games/${code}/leave`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// --- Engine / Game endpoints (Phase 2) ---

export function getEngineState(
  code: string,
  playerId: string
): Promise<EngineState> {
  return request(`/api/games/${code}/state/${playerId}`);
}

export function sendAction(
  code: string,
  data: { player_id: string; pin: string; action: string; amount?: number }
): Promise<{ ok: boolean }> {
  return request(`/api/games/${code}/action`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function dealNextHand(
  code: string,
  data: { player_id: string; pin: string }
): Promise<{ ok: boolean }> {
  return request(`/api/games/${code}/deal`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function requestRebuy(
  code: string,
  data: { player_id: string; pin: string }
): Promise<{ ok: boolean }> {
  return request(`/api/games/${code}/rebuy`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function cancelRebuy(
  code: string,
  data: { player_id: string; pin: string }
): Promise<{ ok: boolean }> {
  return request(`/api/games/${code}/cancel_rebuy`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function showCards(
  code: string,
  data: { player_id: string; pin: string }
): Promise<{ ok: boolean }> {
  return request(`/api/games/${code}/show_cards`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function togglePause(
  code: string,
  data: { player_id: string; pin: string }
): Promise<{ ok: boolean }> {
  return request(`/api/games/${code}/pause`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/** Build WebSocket URL for a game. */
export function buildWsUrl(code: string, playerId: string): string {
  const wsBase =
    import.meta.env.VITE_WS_BASE ??
    `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`;
  return `${wsBase}/ws/${code}/${playerId}`;
}
