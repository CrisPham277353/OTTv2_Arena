"""Game-independent contract for two-player alternating games, plugin API 1.0."""
from dataclasses import dataclass, field
from typing import Any, Protocol


class IllegalAction(ValueError):
    """The bot supplied an action which is not legal in this state."""


@dataclass(frozen=True)
class GameStatus:
    turn: str
    ply: int
    winner: str | None = None
    reason: str | None = None
    details: dict = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.winner is not None


@dataclass
class StepResult:
    state: Any
    events: list[dict]


class GamePlugin(Protocol):
    def create(self, config: dict, seed: int, players: tuple[str, str]) -> Any: ...
    def observe(self, state: Any, player: str) -> dict: ...
    def legal_actions(self, state: Any, player: str) -> list[dict]: ...
    def step(self, state: Any, player: str, action: dict) -> StepResult: ...
    def status(self, state: Any) -> GameStatus: ...
    def serialize_state(self, state: Any) -> dict: ...
    def render_metadata(self, state: Any) -> dict: ...
