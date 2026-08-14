"""Qt-independent representation of a circuit, used for save/load.

This is deliberately kept separate from the QGraphicsScene/Item classes in
``ui/``. A future nodal-analysis or Bode-plot engine should be able to consume
a ``Circuit`` (components + wires) without importing any Qt code: walk the
wires to group terminals into electrical nodes, then build the component
equations from ``ComponentData.type`` and ``.value``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class ComponentData:
    id: str
    type: str
    x: float
    y: float
    rotation: float
    value: float
    label: str


@dataclass
class TerminalRef:
    component_id: str
    terminal_index: int


@dataclass
class WireData:
    id: str
    start: TerminalRef
    end: TerminalRef


@dataclass
class Circuit:
    components: list[ComponentData] = field(default_factory=list)
    wires: list[WireData] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "components": [asdict(c) for c in self.components],
            "wires": [
                {"id": w.id, "start": asdict(w.start), "end": asdict(w.end)}
                for w in self.wires
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Circuit":
        components = [ComponentData(**c) for c in data.get("components", [])]
        wires = [
            WireData(
                id=w["id"],
                start=TerminalRef(**w["start"]),
                end=TerminalRef(**w["end"]),
            )
            for w in data.get("wires", [])
        ]
        return cls(components=components, wires=wires)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "Circuit":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
