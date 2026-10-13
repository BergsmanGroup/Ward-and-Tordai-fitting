"""Unit conversions used at the I/O boundaries of the application.

All internal computation (solver, fitting, isotherms) uses SI units:

- time: seconds (s)
- concentration: mol/m^3
- surface excess (Gamma): mol/m^2
- surface tension: N/m
- diffusion coefficient: m^2/s
- temperature: kelvin (K)

Conversions here are only used when reading user input or writing output
(CSV, GUI fields, plots). Keep conversion factors in one place so unit
bugs cannot silently creep into the physics modules.
"""
from __future__ import annotations

from enum import Enum


class TimeUnit(str, Enum):
    SECONDS = "s"
    MILLISECONDS = "ms"


class TensionUnit(str, Enum):
    MILLINEWTON_PER_METER = "mN/m"
    DYNE_PER_CM = "dyn/cm"  # numerically identical to mN/m


class ConcentrationUnit(str, Enum):
    MOLAR = "M"  # mol/L
    MILLIMOLAR = "mM"  # mmol/L
    MICROMOLAR = "uM"  # umol/L


class GammaInfUnit(str, Enum):
    MICROMOL_PER_M2 = "umol/m2"
    MOL_PER_M2 = "mol/m2"


def time_to_seconds(value, unit: TimeUnit):
    """Convert a time value (scalar or array) to seconds."""
    if unit == TimeUnit.SECONDS:
        return value
    if unit == TimeUnit.MILLISECONDS:
        return value / 1000.0
    raise ValueError(f"Unsupported time unit: {unit}")


def seconds_to_time(value, unit: TimeUnit):
    """Convert seconds (scalar or array) to the requested display unit."""
    if unit == TimeUnit.SECONDS:
        return value
    if unit == TimeUnit.MILLISECONDS:
        return value * 1000.0
    raise ValueError(f"Unsupported time unit: {unit}")


def tension_to_N_per_m(value, unit: TensionUnit):
    """Convert a surface-tension value (scalar or array) to N/m.

    dyn/cm and mN/m are numerically identical (1 dyn/cm = 1 mN/m), so both
    units apply the same 1/1000 factor to reach N/m.
    """
    if unit in (TensionUnit.MILLINEWTON_PER_METER, TensionUnit.DYNE_PER_CM):
        return value / 1000.0
    raise ValueError(f"Unsupported surface-tension unit: {unit}")


def N_per_m_to_mN_per_m(value):
    """Convert N/m (SI, internal) to mN/m for display/output."""
    return value * 1000.0


def concentration_to_mol_per_m3(value, unit: ConcentrationUnit):
    """Convert a bulk concentration (scalar or array) to mol/m^3 (SI)."""
    if unit == ConcentrationUnit.MOLAR:
        return value * 1000.0
    if unit == ConcentrationUnit.MILLIMOLAR:
        return value * 1.0
    if unit == ConcentrationUnit.MICROMOLAR:
        return value * 1.0e-3
    raise ValueError(f"Unsupported concentration unit: {unit}")


def mol_per_m3_to_concentration(value, unit: ConcentrationUnit):
    """Convert mol/m^3 (SI) back to the requested display unit."""
    if unit == ConcentrationUnit.MOLAR:
        return value / 1000.0
    if unit == ConcentrationUnit.MILLIMOLAR:
        return value / 1.0
    if unit == ConcentrationUnit.MICROMOLAR:
        return value / 1.0e-3
    raise ValueError(f"Unsupported concentration unit: {unit}")


def gamma_inf_to_mol_per_m2(value, unit: GammaInfUnit):
    """Convert a maximum-packing surface excess to mol/m^2 (SI)."""
    if unit == GammaInfUnit.MICROMOL_PER_M2:
        return value * 1.0e-6
    if unit == GammaInfUnit.MOL_PER_M2:
        return value
    raise ValueError(f"Unsupported Gamma_inf unit: {unit}")


def mol_per_m2_to_gamma_inf(value, unit: GammaInfUnit):
    """Convert mol/m^2 (SI) back to the requested display unit."""
    if unit == GammaInfUnit.MICROMOL_PER_M2:
        return value / 1.0e-6
    if unit == GammaInfUnit.MOL_PER_M2:
        return value
    raise ValueError(f"Unsupported Gamma_inf unit: {unit}")


def celsius_to_kelvin(value):
    return value + 273.15


def kelvin_to_celsius(value):
    return value - 273.15


# Gas constant, J/(mol K)
GAS_CONSTANT_R = 8.314462618
