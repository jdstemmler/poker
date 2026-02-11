"""Pydantic models for the poker lobby."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class GameStatus(str, Enum):
    LOBBY = "lobby"
    ACTIVE = "active"
    ENDED = "ended"


# --- Request models ---


class CreateGameRequest(BaseModel):
    creator_name: str = Field(..., min_length=1, max_length=20)
    creator_pin: str = Field(..., pattern=r"^\d{4}$")
    starting_chips: int = Field(default=5000, ge=100, le=100000)
    max_players: int = Field(default=50, ge=2, le=50)
    allow_rebuys: bool = Field(default=True)
    max_rebuys: int = Field(default=1, ge=0, le=99)  # 0 = unlimited
    rebuy_cutoff_minutes: int = Field(default=60, ge=0, le=480)  # 0 = no cutoff
    turn_timeout: int = Field(default=0, ge=0, le=300)  # seconds, 0 = no timer
    blind_level_duration: int = Field(default=20, ge=5, le=60)  # minutes
    target_game_time: int = Field(default=4, ge=0, le=12)  # hours, 0 = fixed blinds
    auto_deal_enabled: bool = True  # auto-deal next hand


class JoinGameRequest(BaseModel):
    player_name: str = Field(..., min_length=1, max_length=20)
    player_pin: str = Field(..., pattern=r"^\d{4}$")


class ReadyRequest(BaseModel):
    player_id: str
    pin: str = Field(..., pattern=r"^\d{4}$")


class StartGameRequest(BaseModel):
    player_id: str
    pin: str = Field(..., pattern=r"^\d{4}$")


# --- Response / state models ---


class PlayerInfo(BaseModel):
    """Public-facing player information (no PIN)."""

    id: str
    name: str
    ready: bool = False
    connected: bool = False
    is_creator: bool = False


class GameSettings(BaseModel):
    starting_chips: int
    max_players: int
    allow_rebuys: bool
    max_rebuys: int = 1  # 0 = unlimited
    rebuy_cutoff_minutes: int = 60  # 0 = no cutoff
    turn_timeout: int = 0  # seconds, 0 = no timer
    blind_level_duration: int = 20  # minutes
    target_game_time: int = 4  # hours, 0 = fixed blinds
    auto_deal_enabled: bool = True  # auto-deal next hand


class GameState(BaseModel):
    """Full lobby state sent to clients."""

    code: str
    status: GameStatus
    settings: GameSettings
    players: list[PlayerInfo]
    creator_id: str


class CreateGameResponse(BaseModel):
    code: str
    player_id: str
    game: GameState


class JoinGameResponse(BaseModel):
    player_id: str
    game: GameState


class ErrorResponse(BaseModel):
    detail: str
