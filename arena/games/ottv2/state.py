from dataclasses import dataclass, field


@dataclass(frozen=True)
class Piece:
    side: str
    kind: str


@dataclass
class State:
    board: dict[str, Piece]
    seed: int = 42
    game_instance_id: str = 'game-1'
    turn: str = 'A'
    ply: int = 0
    winner: str | None = None
    reason: str | None = None
    details: dict = field(default_factory=dict)
    repetitions: dict[str, int] = field(default_factory=dict)
    last_move: dict | None = None
