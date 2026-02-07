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
    starting_chips: int = Field(default=1000, ge=100, le=100000)
    small_blind: int = Field(default=10, ge=1)
    big_blind: int = Field(default=20, ge=2)
    max_players: int = Field(default=9, ge=4, le=9)
    allow_rebuys: bool = Field(default=True)


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
    small_blind: int
    big_blind: int
    max_players: int
    allow_rebuys: bool


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
