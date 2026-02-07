/** API client for communicating with the backend. */

import type { CreateGameResponse, GameState, JoinGameResponse } from "./types";

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

/** Build WebSocket URL for a game lobby. */
export function buildWsUrl(code: string, playerId: string): string {
  const wsBase =
    import.meta.env.VITE_WS_BASE ??
    `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`;
  return `${wsBase}/ws/${code}/${playerId}`;
}
