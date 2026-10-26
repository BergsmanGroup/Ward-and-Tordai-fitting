"""Core dataclasses shared across the ward_tordai package.

These are plain data containers (SI units only); no GUI or I/O logic lives
here. See ``units.py`` for conversions at the I/O boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class ExperimentalData:
    """Measured dynamic-surface-tension data, in SI units.

    Attributes
    ----------
    time_s:
        Surface age (bubble lifetime) in seconds, strictly positive,
        sorted ascending. Duplicate ages are preserved (replicate
        measurements), not averaged, unless the caller explicitly
        averages them beforehand.
    sigma_N_per_m:
        Measured surface tension in N/m, same length as ``time_s``.
    """

    time_s: np.ndarray
    sigma_N_per_m: np.ndarray

    def __post_init__(self) -> None:
        self.time_s = np.asarray(self.time_s, dtype=float)
        self.sigma_N_per_m = np.asarray(self.sigma_N_per_m, dtype=float)
        if self.time_s.shape != self.sigma_N_per_m.shape:
            raise ValueError("time_s and sigma_N_per_m must have the same shape")
        if self.time_s.ndim != 1:
            raise ValueError("time_s and sigma_N_per_m must be 1-D arrays")

    def __len__(self) -> int:
        return self.time_s.size


@dataclass
class FitSettings:
    """All fixed physical inputs needed to run a forward simulation.

    ``diffusion_coefficient_m2_per_s`` is the value used by ``solve`` /
    ``Simulate``; during fitting it is treated as the optimizer's current
    trial value and is not itself assumed correct.
    """

    isotherm_name: str
    isotherm_params: dict
    bulk_concentration_mol_per_m3: float
    temperature_K: float
    solvent_sigma0_N_per_m: float
    diffusion_coefficient_m2_per_s: float

    def __post_init__(self) -> None:
        if self.bulk_concentration_mol_per_m3 <= 0:
            raise ValueError("bulk_concentration_mol_per_m3 must be positive")
        if self.temperature_K <= 0:
            raise ValueError("temperature_K must be positive")
        if self.diffusion_coefficient_m2_per_s <= 0:
            raise ValueError("diffusion_coefficient_m2_per_s must be positive")


@dataclass
class SimulationResult:
    """Output of a forward Ward-Tordai solve at requested times."""

    time_s: np.ndarray
    gamma_mol_per_m2: np.ndarray
    sigma_N_per_m: np.ndarray
    converged: bool
    message: str = ""
    equilibrium_gamma_mol_per_m2: Optional[float] = None
    equilibrium_sigma_N_per_m: Optional[float] = None


@dataclass
class FitResult:
    """Output of a D optimization, optionally profiled over other inputs.

    ``r_squared`` is the coefficient of determination
    (``1 - SS_res/SS_tot``) of the fitted curve against the measured
    surface tensions, reported alongside RMSE as a fit-quality value.
    """

    fitted_D_m2_per_s: float
    simulation: Optional[SimulationResult]
    rmse_N_per_m: float
    n_observations: int
    success: bool
    message: str = ""
    r_squared: float = float("nan")
    log10_D_bounds: tuple = field(default_factory=lambda: (-13.0, -7.0))
    fitted_parameters: dict[str, float] = field(default_factory=dict)
    parameter_profile_rmse_span_N_per_m: dict[str, float] = field(default_factory=dict)
    optimized_settings: Optional[FitSettings] = None
    time_offset_s: float = 0.0
