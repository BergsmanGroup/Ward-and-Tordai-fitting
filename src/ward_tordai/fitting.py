"""D-only optimization: fit the apparent diffusion coefficient to data.

Bulk concentration, temperature, solvent surface tension and isotherm
parameters are held fixed; only ``D`` (via ``log10(D)``) is optimized,
minimizing the unweighted sum of squared surface-tension residuals at the
measured surface ages. A failed forward solve is treated as an invalid
(infinite) objective so the optimizer is steered away from it rather than
crashing.
"""
from __future__ import annotations

import dataclasses

import numpy as np
from scipy.optimize import minimize_scalar

from .models import ExperimentalData, FitResult, FitSettings, SimulationResult
from .solver import solve


def _rmse_N_per_m(predicted: np.ndarray, observed: np.ndarray) -> float:
    return float(np.sqrt(np.mean((predicted - observed) ** 2)))


def _r_squared(predicted: np.ndarray, observed: np.ndarray) -> float:
    """Coefficient of determination, a fit-quality value alongside RMSE."""
    ss_res = np.sum((predicted - observed) ** 2)
    ss_tot = np.sum((observed - np.mean(observed)) ** 2)
    if ss_tot == 0:
        return float("nan")
    return float(1.0 - ss_res / ss_tot)


def simulate(settings: FitSettings, data: ExperimentalData) -> SimulationResult:
    """Run the forward solver at the data's measured times (the 'Simulate' action)."""
    return solve(settings, data.time_s)


def _objective_log10_D(
    log10_D: float, settings: FitSettings, data: ExperimentalData
) -> float:
    trial_settings = dataclasses.replace(
        settings, diffusion_coefficient_m2_per_s=10.0**log10_D
    )
    result = solve(trial_settings, data.time_s)
    if not result.converged or np.any(~np.isfinite(result.sigma_N_per_m)):
        return np.inf
    return float(np.sum((result.sigma_N_per_m - data.sigma_N_per_m) ** 2))


def fit_diffusivity(
    settings: FitSettings,
    data: ExperimentalData,
    log10_D_bounds: tuple = (-13.0, -7.0),
) -> FitResult:
    """Fit the apparent diffusion coefficient D by bounded 1-D optimization.

    Parameters
    ----------
    settings:
        Fixed physical settings. ``diffusion_coefficient_m2_per_s`` is used
        only as a fallback if the optimizer cannot find any valid point
        (it is not assumed correct).
    data:
        Measured surface ages/tensions to fit against (SI units). Replicate
        measurements are fit individually; average them beforehand if a
        single averaged fit is desired.
    log10_D_bounds:
        Editable, physically reasonable bounds on log10(D [m^2/s]). The
        default range (1e-13 to 1e-7 m^2/s) comfortably spans small-ion to
        large-micelle diffusivities in aqueous solution.

    Returns
    -------
    FitResult
        ``success=False`` with a descriptive message if optimization failed
        to find any valid (converged) forward solve across the bounds.
    """
    if len(data) == 0:
        raise ValueError("data must contain at least one observation")

    low, high = log10_D_bounds
    if not (np.isfinite(low) and np.isfinite(high) and low < high):
        raise ValueError("log10_D_bounds must be a finite (low, high) pair with low < high")

    opt_result = minimize_scalar(
        _objective_log10_D,
        bounds=(low, high),
        args=(settings, data),
        method="bounded",
        options={"xatol": 1e-4},
    )

    if not opt_result.success or not np.isfinite(opt_result.fun):
        return FitResult(
            fitted_D_m2_per_s=settings.diffusion_coefficient_m2_per_s,
            simulation=None,
            rmse_N_per_m=float("nan"),
            n_observations=len(data),
            success=False,
            message=(
                "Optimizer failed to find a convergent forward solve within "
                f"the D bounds [1e{low:g}, 1e{high:g}] m^2/s. Try adjusting "
                "the bounds or the isotherm/initial-guess parameters."
            ),
            log10_D_bounds=log10_D_bounds,
        )

    fitted_D = 10.0 ** opt_result.x
    final_settings = dataclasses.replace(settings, diffusion_coefficient_m2_per_s=fitted_D)
    final_simulation = solve(final_settings, data.time_s)
    if not final_simulation.converged:
        return FitResult(
            fitted_D_m2_per_s=fitted_D,
            simulation=final_simulation,
            rmse_N_per_m=float("nan"),
            n_observations=len(data),
            success=False,
            message=f"Fit converged to D={fitted_D:.3e} m^2/s but final verification solve failed: "
            f"{final_simulation.message}",
            log10_D_bounds=log10_D_bounds,
        )

    rmse = _rmse_N_per_m(final_simulation.sigma_N_per_m, data.sigma_N_per_m)
    r_squared = _r_squared(final_simulation.sigma_N_per_m, data.sigma_N_per_m)
    return FitResult(
        fitted_D_m2_per_s=fitted_D,
        simulation=final_simulation,
        rmse_N_per_m=rmse,
        n_observations=len(data),
        success=True,
        message="Fit succeeded.",
        r_squared=r_squared,
        log10_D_bounds=log10_D_bounds,
    )
