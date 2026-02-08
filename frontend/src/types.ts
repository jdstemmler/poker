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
  max_rebuys: number;
  rebuy_cutoff_minutes: number;
  turn_timeout: number;
  blind_level_duration: number;
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

// --- Engine / Game types (Phase 2) ---

export interface CardData {
  rank: number;
  suit: string; // "h" | "d" | "c" | "s"
}

export interface EnginePlayer {
  player_id: string;
  name: string;
  chips: number;
  bet_this_round: number;
  bet_this_hand: number;
  folded: boolean;
  all_in: boolean;
  is_sitting_out: boolean;
  last_action: string;
  rebuy_count: number;
  hole_cards?: CardData[];
}

export interface ValidAction {
  action: string;
  amount?: number;
  min_amount?: number;
  max_amount?: number;
}

export interface HandResultWinner {
  player_id: string;
  name: string;
  winnings: number;
  hand: string;
}

export interface HandResult {
  winners: HandResultWinner[];
  pot: number;
  community_cards: CardData[];
  player_hands: Record<
    string,
    { cards: CardData[]; hand_name: string | null }
  >;
}

export type Street = "preflop" | "flop" | "turn" | "river" | "showdown";

export interface EngineState {
  game_code: string;
  hand_number: number;
  street: Street;
  pot: number;
  community_cards: CardData[];
  dealer_idx: number;
  dealer_player_id: string;
  action_on: string | null;
  current_bet: number;
  min_raise: number;
  hand_active: boolean;
  game_over: boolean;
  message: string;
  last_hand_result: HandResult | null;
  players: EnginePlayer[];
  showdown: boolean;
  shown_cards: string[];
  my_cards: CardData[];
  valid_actions: ValidAction[];
  turn_timeout: number;
  action_deadline: number | null;
  auto_deal_deadline: number | null;
  game_started_at: number | null;
  small_blind: number;
  big_blind: number;
  blind_level: number;
  blind_level_duration: number;
  blind_schedule: number[][];
  next_blind_change_at: number | null;
  max_rebuys: number;
  rebuy_cutoff_minutes: number;
}

/** WebSocket message wrapper. */
export interface WsMessage {
  type: "game_state" | "lobby_state" | "connection_info" | "ping";
  data: EngineState;
}

/** Connection info broadcast from server. */
export interface ConnectionInfo {
  type: "connection_info";
  connected_players: string[];
  spectator_count: number;
}
