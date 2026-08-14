"""Metadata for the electrical component types the builder supports.

Adding a new component type means adding one entry here plus a matching
``_draw_<key>`` method on ``ComponentItem`` (see ui/component_item.py).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComponentType:
    key: str
    display_name: str
    unit: str
    default_value: float
    prefix: str  # used to auto-generate labels, e.g. "R1", "C2"
    shortcut: str  # keyboard shortcut that enters placement mode for this type


RESISTOR = ComponentType("resistor", "Resistor", "Ω", 1000.0, "R", "R")
BATTERY = ComponentType("battery", "Battery", "V", 9.0, "V", "B")
CAPACITOR = ComponentType("capacitor", "Capacitor", "F", 1e-6, "C", "C")
INDUCTOR = ComponentType("inductor", "Inductor", "H", 1e-3, "L", "I")

# A junction has no electrical value of its own - it's just a wiring hub with
# a single terminal that any number of wires can connect to. ComponentItem
# special-cases component_type == "junction" to render it as a bare dot with
# one terminal instead of a labeled two-terminal symbol.
JUNCTION = ComponentType("junction", "Node", "", 0.0, "J", "N")

COMPONENT_TYPES: dict[str, ComponentType] = {
    c.key: c for c in (RESISTOR, BATTERY, CAPACITOR, INDUCTOR, JUNCTION)
}
