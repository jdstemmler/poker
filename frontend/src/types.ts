/** Shared types mirroring backend models. */

export type GameStatus = "lobby" | "active" | "ended";

export interface PlayerInfo {
  id: string;
  name: string;
  ready: boolean;
  connected: boolean;
  is_creator: boolean;
}

export interface GameSettings {
  starting_chips: number;
  small_blind: number;
  big_blind: number;
  max_players: number;
  allow_rebuys: boolean;
}

export interface GameState {
  code: string;
  status: GameStatus;
  settings: GameSettings;
  players: PlayerInfo[];
  creator_id: string;
}

export interface CreateGameResponse {
  code: string;
  player_id: string;
  game: GameState;
}

export interface JoinGameResponse {
  player_id: string;
  game: GameState;
}
