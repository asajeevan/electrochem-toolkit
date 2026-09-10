"""Closed, versioned unit registry; not a general symbolic unit algebra.

Registry values map to SI via x_si = x * scale + offset. Absolute
temperature is deliberately separate from temperature differences.
"""
from dataclasses import dataclass
import math
from types import MappingProxyType

UNIT_REGISTRY_VERSION = "0.1.0"


@dataclass(frozen=True)
class Unit:
    dimension: str
    si: str
    scale: float
    offset: float = 0.0


def _registry():
    groups = {
        "time": ("s", {"s": 1., "ms": .001, "min": 60., "h": 3600.}),
        "current": ("A", {"A": 1., "mA": .001, "µA": 1e-6, "uA": 1e-6}),
        "potential": ("V", {"V": 1., "mV": .001}),
        "charge": ("C", {"C": 1., "Ah": 3600., "mAh": 3.6, "mA.h": 3.6}),
        "energy": ("J", {"J": 1., "Wh": 3600., "mWh": 3.6}),
        "mass": ("kg", {"kg": 1., "g": .001, "mg": 1e-6}),
        "length": ("m", {"m": 1., "cm": .01, "mm": .001, "µm": 1e-6}),
        "area": ("m^2", {"m^2": 1., "cm^2": 1e-4, "mm^2": 1e-6}),
        "specific_charge": ("C/kg", {"C/kg": 1., "mAh/g": 3600.}),
        "areal_charge": ("C/m^2", {"C/m^2": 1., "mAh/cm^2": 36000.}),
        "specific_energy": ("J/kg", {"J/kg": 1., "Wh/kg": 3600.}),
        "current_density": ("A/m^2", {"A/m^2": 1., "mA/cm^2": 10.}),
        "resistance": ("ohm", {"ohm": 1., "Ω": 1., "kohm": 1000.}),
        "frequency": ("Hz", {"Hz": 1., "kHz": 1000.}),
        "conductivity": ("S/m", {"S/m": 1., "S/cm": 100.}),
        "diffusivity": ("m^2/s", {"m^2/s": 1., "cm^2/s": 1e-4}),
        "fraction": ("1", {"1": 1., "%": .01, "ppm": 1e-6}),
        "rate": ("s^-1", {"s^-1": 1., "h^-1": 1/3600.}),
        "temperature_difference": ("delta_K", {"delta_K": 1., "delta_degC": 1.}),
    }
    r = {name: Unit(dim, si, scale) for dim, (si, names) in groups.items()
         for name, scale in names.items()}
    r.update({"K": Unit("temperature", "K", 1.),
              "degC": Unit("temperature", "K", 1., 273.15),
              "°C": Unit("temperature", "K", 1., 273.15)})
    return r


UNITS = MappingProxyType(_registry())


def unit(name: str) -> Unit:
    try:
        return UNITS[name]
    except (KeyError, TypeError) as e:
        raise ValueError(f"Unknown unit {name!r}; no unit inference is permitted") from e


def convert(value: float, source: str, target: str) -> float:
    """Convert finite scalar quantities only; None and booleans are not numbers."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("A finite numeric value is required")
    a, b = unit(source), unit(target)
    if a.dimension != b.dimension:
        raise ValueError(f"Incompatible dimensions: {source} -> {target}")
    si_value = value * a.scale + a.offset
    if a.dimension == "temperature" and si_value < 0:
        raise ValueError("Absolute temperature cannot be below zero kelvin")
    result = (si_value - b.offset) / b.scale
    if not math.isfinite(result):
        raise ValueError("Unit conversion overflow")
    return result
