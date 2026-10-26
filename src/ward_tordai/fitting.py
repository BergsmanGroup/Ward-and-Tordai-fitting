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
from typing import Callable, Mapping

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
    n_values: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
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

    if n_values is not None and n_values < 2:
        raise ValueError("n_values must be at least 2")

    def objective_with_progress(log10_D: float) -> float:
        objective_with_progress.completed += 1
        if progress_callback is not None:
            progress_callback(objective_with_progress.completed, objective_with_progress.total)
        return _objective_log10_D(log10_D, settings, data)

    objective_with_progress.completed = 0
    objective_with_progress.total = n_values or 1
    if n_values is None:
        opt_result = minimize_scalar(
            objective_with_progress,
            bounds=(low, high),
            method="bounded",
            options={"xatol": 1e-4},
        )
        opt_x = opt_result.x
        opt_fun = opt_result.fun
        opt_success = opt_result.success
    else:
        grid = np.linspace(low, high, n_values)
        values = np.array([objective_with_progress(value) for value in grid])
        best_index = int(np.argmin(values))
        opt_x = float(grid[best_index])
        opt_fun = float(values[best_index])
        opt_success = np.isfinite(opt_fun)

    if not opt_success or not np.isfinite(opt_fun):
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

    fitted_D = 10.0 ** opt_x
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
        fitted_parameters={"diffusion_coefficient_m2_per_s": fitted_D},
        optimized_settings=final_settings,
    )


def _fit_with_optional_inputs(
    settings: FitSettings,
    data: ExperimentalData,
    *,
    bulk_concentration_mol_per_m3: float,
    solvent_sigma0_N_per_m: float,
    temperature_K: float,
    time_offset_s: float,
    isotherm_params: Mapping[str, float],
    d_n_values: int,
    progress_callback: Callable[[int, int], None] | None,
    log10_D_bounds: tuple,
) -> FitResult:
    """Fit D after applying one candidate set of non-D parameters."""
    shifted_times = data.time_s + time_offset_s
    if np.any(shifted_times <= 0):
        return FitResult(
            fitted_D_m2_per_s=settings.diffusion_coefficient_m2_per_s,
            simulation=None,
            rmse_N_per_m=float("inf"),
            n_observations=len(data),
            success=False,
            message="Time offset would produce a non-positive surface age.",
            log10_D_bounds=log10_D_bounds,
        )
    candidate_settings = dataclasses.replace(
        settings,
        bulk_concentration_mol_per_m3=bulk_concentration_mol_per_m3,
        solvent_sigma0_N_per_m=solvent_sigma0_N_per_m,
        temperature_K=temperature_K,
        isotherm_params=dict(isotherm_params),
    )
    shifted_data = ExperimentalData(shifted_times, data.sigma_N_per_m)
    result = fit_diffusivity(
        candidate_settings,
        shifted_data,
        log10_D_bounds,
        n_values=d_n_values,
        progress_callback=progress_callback,
    )
    if result.simulation is not None:
        # The model is evaluated at shifted ages, but the plot remains in the
        # instrument's reported time coordinate.
        result.simulation.time_s = data.time_s.copy()
    result.time_offset_s = time_offset_s
    result.optimized_settings = (
        dataclasses.replace(candidate_settings, diffusion_coefficient_m2_per_s=result.fitted_D_m2_per_s)
        if result.success
        else None
    )
    return result


def fit_profiled_parameters(
    settings: FitSettings,
    data: ExperimentalData,
    *,
    fit_concentration: bool = False,
    concentration_bounds_mol_per_m3: tuple[float, float] = (0.2, 2.0),
    fit_solvent_sigma0: bool = False,
    solvent_sigma0_bounds_N_per_m: tuple[float, float] = (0.070, 0.075),
    fit_temperature: bool = False,
    temperature_bounds_K: tuple[float, float] = (293.15, 299.15),
    fixed_temperature_K: float | None = None,
    fit_time_offset: bool = False,
    time_offset_bounds_s: tuple[float, float] = (-2.0, 2.0),
    initial_time_offset_s: float = 0.0,
    fit_isotherm_params: Mapping[str, tuple[float, float]] | None = None,
    fixed_isotherm_params: Mapping[str, float] | None = None,
    d_n_values: int = 25,
    n_values: Mapping[str, int] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    log10_D_bounds: tuple = (-13.0, -7.0),
) -> FitResult:
    """Fit D primarily, with optional bounded profile fits for teaching data.

    The optional parameters are explored one at a time. Every candidate is
    evaluated by a complete D-only fit, preserving D as the primary fitting
    parameter and avoiding an unconstrained multi-parameter optimizer.
    """
    if len(data) == 0:
        raise ValueError("data must contain at least one observation")

    ranges: dict[str, tuple[float, float]] = {}
    if fit_concentration:
        ranges["bulk_concentration_mol_per_m3"] = concentration_bounds_mol_per_m3
    if fit_solvent_sigma0:
        ranges["solvent_sigma0_N_per_m"] = solvent_sigma0_bounds_N_per_m
    if fit_temperature:
        ranges["temperature_K"] = temperature_bounds_K
    if fit_time_offset:
        ranges["time_offset_s"] = time_offset_bounds_s
    for name, bounds in (fit_isotherm_params or {}).items():
        ranges[f"isotherm_param:{name}"] = bounds
    counts = {name: 9 for name in ranges}
    if d_n_values < 2:
        raise ValueError("d_n_values must be at least 2")
    if n_values is not None:
        for name in ranges:
            lookup_name = name.split(":", 1)[1] if name.startswith("isotherm_param:") else name
            count = int(n_values.get(lookup_name, counts[name]))
            if count < 2:
                raise ValueError(f"{name} must test at least 2 values")
            counts[name] = count
    for name, (low, high) in ranges.items():
        if not (np.isfinite(low) and np.isfinite(high) and low < high):
            raise ValueError(f"{name} bounds must be a finite (low, high) pair with low < high")

    current = {
        "bulk_concentration_mol_per_m3": settings.bulk_concentration_mol_per_m3,
        "solvent_sigma0_N_per_m": settings.solvent_sigma0_N_per_m,
        "temperature_K": (
            fixed_temperature_K if fixed_temperature_K is not None else settings.temperature_K
        ),
        "time_offset_s": initial_time_offset_s,
    }
    isotherm_current = dict(settings.isotherm_params)
    isotherm_current.update(fixed_isotherm_params or {})
    for name in (fit_isotherm_params or {}):
        if name not in isotherm_current:
            raise ValueError(f"Missing current value for isotherm parameter '{name}'")
        current[f"isotherm_param:{name}"] = isotherm_current[name]
    if not (np.isfinite(current["time_offset_s"]) and time_offset_bounds_s[0] <= current["time_offset_s"] <= time_offset_bounds_s[1]):
        raise ValueError("initial_time_offset_s must be finite and within time_offset_bounds_s")
    if not np.isfinite(current["temperature_K"]) or current["temperature_K"] <= 0:
        raise ValueError("fixed_temperature_K must be finite and positive")

    outer_evaluation_count = 1 + sum(3 * count + 2 for count in counts.values())
    progress_completed = 0
    progress_total = outer_evaluation_count * d_n_values

    def report_progress(_completed: int, _total: int) -> None:
        nonlocal progress_completed
        progress_completed += 1
        if progress_callback is not None:
            progress_callback(progress_completed, progress_total)

    def evaluate(candidate: Mapping[str, float]) -> FitResult:
        return _fit_with_optional_inputs(
            settings,
            data,
            bulk_concentration_mol_per_m3=candidate["bulk_concentration_mol_per_m3"],
            solvent_sigma0_N_per_m=candidate["solvent_sigma0_N_per_m"],
            temperature_K=candidate["temperature_K"],
            time_offset_s=candidate["time_offset_s"],
            isotherm_params={
                **isotherm_current,
                **{
                    name.split(":", 1)[1]: value
                    for name, value in candidate.items()
                    if name.startswith("isotherm_param:")
                },
            },
            d_n_values=d_n_values,
            log10_D_bounds=log10_D_bounds,
            progress_callback=report_progress,
        )

    if progress_callback is not None:
        progress_callback(0, progress_total)
    best = evaluate(current)
    # Three coordinate passes are enough for the small teaching ranges and
    # keep the number of expensive forward solves predictable.
    for pass_number in range(3):
        for name, (low, high) in ranges.items():
            if pass_number == 0:
                grid = np.linspace(low, high, counts[name])
            else:
                center = current[name]
                half_width = (high - low) * (0.5 ** pass_number) / 2.0
                grid = np.linspace(
                    max(low, center - half_width),
                    min(high, center + half_width),
                    counts[name],
                )
            for value in grid:
                candidate = dict(current)
                candidate[name] = float(value)
                result = evaluate(candidate)
                if result.success and (not best.success or result.rmse_N_per_m < best.rmse_N_per_m):
                    best = result
                    current = candidate

    if not best.success:
        return best

    profile_spans: dict[str, float] = {}
    for name, (low, high) in ranges.items():
        center = current[name]
        half_width = max((high - low) * 0.1, np.finfo(float).eps)
        profile_values = (
            max(low, center - half_width),
            min(high, center + half_width),
        )
        profile_results = []
        for value in profile_values:
            candidate = dict(current)
            candidate[name] = value
            result = evaluate(candidate)
            if result.success:
                profile_results.append(result.rmse_N_per_m)
        if profile_results:
            profile_spans[name] = float(max(profile_results) - best.rmse_N_per_m)

    fitted_settings = best.optimized_settings
    fitted_parameters = {
        "diffusion_coefficient_m2_per_s": best.fitted_D_m2_per_s,
        "bulk_concentration_mol_per_m3": current["bulk_concentration_mol_per_m3"],
        "solvent_sigma0_N_per_m": current["solvent_sigma0_N_per_m"],
        "temperature_K": current["temperature_K"],
        "time_offset_s": current["time_offset_s"],
    }
    fitted_parameters.update(
        {
            name: current[f"isotherm_param:{name}"]
            for name in (fit_isotherm_params or {})
        }
    )
    return dataclasses.replace(
        best,
        fitted_parameters=fitted_parameters,
        parameter_profile_rmse_span_N_per_m=profile_spans,
        optimized_settings=fitted_settings,
        time_offset_s=current["time_offset_s"],
        message=(
            "D fit succeeded."
            if not ranges
            else "D-primary profiled fit succeeded; see parameter profile diagnostics."
        ),
    )
