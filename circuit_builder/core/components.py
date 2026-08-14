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
# A real 1uF-ish capacitor charges/discharges through a typical resistor in
# well under a second - too fast to watch happen. Defaulting much larger
# ("supercapacitor" territory) means a fresh switch+capacitor+bulb demo
# circuit visibly charges/discharges over a few seconds instead of
# instantly; a real-world value is one edit away for anyone who wants one.
CAPACITOR = ComponentType("capacitor", "Capacitor", "F", 1e-2, "C", "C")
# Same reasoning as the capacitor above, mirrored: a real 1mH-ish inductor's
# L/R time constant against a typical load is also well under a second.
# Defaulting much larger keeps a fresh switch+inductor+bulb demo circuit's
# current ramp-up visible over a couple of seconds instead of instant.
INDUCTOR = ComponentType("inductor", "Inductor", "H", 20.0, "L", "I")
# Electrically just a resistor with a glow - see ui/component_item.py's
# _draw_lamp and main_window's simulation refresh for the brightness visual.
LAMP = ComponentType("lamp", "Bulb", "Ω", 50.0, "LP", "L")
# Has no numeric value at all - its state is the open/closed ComponentItem.closed
# flag, flipped by clicking it (see ComponentItem.toggle_requested).
SWITCH = ComponentType("switch", "Switch", "", 0.0, "SW", "S")

# A junction has no electrical value of its own - it's just a wiring hub with
# a single terminal that any number of wires can connect to. ComponentItem
# special-cases component_type == "junction" to render it as a bare dot with
# one terminal instead of a labeled two-terminal symbol.
JUNCTION = ComponentType("junction", "Node", "", 0.0, "J", "N")

COMPONENT_TYPES: dict[str, ComponentType] = {
    c.key: c for c in (RESISTOR, BATTERY, CAPACITOR, INDUCTOR, LAMP, SWITCH, JUNCTION)
}
