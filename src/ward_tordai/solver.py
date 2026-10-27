"""Planar Ward-Tordai forward solver (diffusion-controlled adsorption only).

Not in scope: spherical/curved-interface geometry, micelle breakup /
post-CMC modeling, and the legacy workbook's "root estimation" /
"solution tweaking" acceleration heuristics.

Governing equation (Ward & Tordai, 1946; see Li, Shaw, Evans & Stevenson,
2010, Eq. 1)::

    Gamma(t) = 2*sqrt(D/pi)*cb*sqrt(t) - sqrt(D/pi) * Integral_0^t c(tau) / sqrt(t - tau) dtau

Note the two terms do **not** share the same prefactor: the first (no
back-diffusion) term has a factor of 2, the back-diffusion integral does
not. The integrand of that integral has an *integrable* singularity at
tau = t (``1/sqrt(t-tau)`` diverges but the integral is finite). Rather
than evaluating this kernel directly at tau = t (which both diverges and
is what the prompt specifically warns against), this solver eliminates
the singularity analytically via the substitution ``u = sqrt(t - tau)``,
which contributes its own factor of 2 (``dtau = -2u du``):

    Integral_0^t c(tau)/sqrt(t-tau) dtau = 2 * Integral_0^{sqrt(t)} c(t - u**2) du

so that, after substitution, both terms recombine under a single common
prefactor::

    Gamma(t) = 2*sqrt(D/pi) * [ cb*sqrt(t) - Integral_0^{sqrt(t)} c(t - u**2) du ]

and the right-hand integral is manifestly finite at u = 0. Discretizing
it with the trapezoidal rule on the (non-uniform) grid u_j = sqrt(t_n -
t_j) reproduces exactly the same recursion used in the legacy VBA
workbook (``WardAndTordai.bas``, functions ``PastBackDiff``/``Equal``),
which was cross-checked term-by-term against this module (see
``tests/test_solver.py::test_legacy_vba_bisection_recursion_matches_new_solver``),
and is also the trapezoidal/bisection scheme of Li et al. (2010),
Section 3.

At each new time step t_n, Gamma(t_n) appears on both sides of the
discretized equation (through the unknown c(Gamma(t_n)) term in the
trapezoidal sum), so a bounded root solve (``scipy.optimize.brentq``) is
used, bracketed by ``[Gamma(t_{n-1}), Gamma_inf)`` (or an expanding
bracket for non-saturating isotherms such as Henry). This mirrors the
bisection approach recommended by Li et al. (2010) for its robustness.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from .isotherms import IsothermError, build_isotherm
from .models import FitSettings, SimulationResult


class SolverError(RuntimeError):
    """Raised when the forward solve fails to converge or is physically invalid."""


@dataclass
class _GridSolution:
    time_s: np.ndarray
    gamma_mol_per_m2: np.ndarray
    c_subsurface_mol_per_m3: np.ndarray


def _build_solve_grid(
    requested_times_s: np.ndarray,
    n_internal_points: int = 200,
    min_time_s: float | None = None,
) -> np.ndarray:
    """Build the time grid the solver marches over.

    The grid is the sorted union of a dense, log-spaced internal grid
    (to resolve the rapid early-time dynamics, as recommended by the
    legacy workbook's own "minimum time step" / log-style refinement) and
    every requested (measurement) time. Including the measurement times
    directly in the solve grid lets the solver return Gamma/sigma *at
    those exact times* with no interpolation error, rather than matching
    each observation to the next grid point (the approach explicitly
    disallowed for this implementation) or relying on interpolation.
    """
    t_max = float(np.max(requested_times_s))
    if min_time_s is None:
        min_time_s = min(float(np.min(requested_times_s)), t_max) / 1000.0
        min_time_s = max(min_time_s, 1e-9)
    log_grid = np.geomspace(min_time_s, t_max, n_internal_points)
    grid = np.union1d(log_grid, requested_times_s)
    grid = np.union1d(grid, np.array([0.0]))
    return np.sort(np.unique(grid))


def solve(settings: FitSettings, time_s: np.ndarray) -> SimulationResult:
    """Solve the planar Ward-Tordai equation at the requested times.

    Parameters
    ----------
    settings:
        Fixed physical settings (isotherm, bulk concentration, temperature,
        solvent tension, and the diffusion coefficient to use).
    time_s:
        Requested surface ages (s), must be positive and finite. Need not
        be sorted or unique; the returned arrays follow the same order.

    Returns
    -------
    SimulationResult
        ``converged=False`` with a descriptive ``message`` if the forward
        solve failed (non-convergent root search or an invalid physical
        state); callers must check this flag rather than trust a returned
        curve.
    """
    time_s = np.asarray(time_s, dtype=float)
    if time_s.ndim != 1 or time_s.size == 0:
        raise ValueError("time_s must be a non-empty 1-D array")
    if np.any(~np.isfinite(time_s)) or np.any(time_s <= 0):
        raise ValueError("time_s must contain only finite, positive values")

    if settings.geometry == "spherical":
        return _solve_spherical(settings, time_s)

    try:
        isotherm = build_isotherm(settings.isotherm_name, settings.isotherm_params)
    except IsothermError as exc:
        return SimulationResult(
            time_s=time_s,
            gamma_mol_per_m2=np.full_like(time_s, np.nan),
            sigma_N_per_m=np.full_like(time_s, np.nan),
            converged=False,
            message=f"Invalid isotherm parameters: {exc}",
        )

    D = settings.diffusion_coefficient_m2_per_s
    cb = settings.bulk_concentration_mol_per_m3

    grid = _build_solve_grid(time_s)
    n = grid.size

    gamma = np.zeros(n)
    c_sub = np.zeros(n)  # c_sub[0] = c(Gamma=0) = 0 for all isotherms here

    prefactor = 2.0 * math.sqrt(D / math.pi)
    gamma_upper_limit = isotherm.gamma_inf

    message = ""
    converged = True

    for i in range(1, n):
        t_n = grid[i]
        # u_j = sqrt(t_n - t_j) for j = 0..i-1 (all known); u_i = 0 (unknown term).
        u = np.sqrt(np.clip(t_n - grid[:i], 0.0, None))
        # Trapezoidal weights over the non-uniform u-grid, excluding the
        # final (singular-looking but finite, since u_i=0) interval which
        # involves the unknown c at t_n and is added inside the residual.
        du = u[:-1] - u[1:]  # u decreases as j increases toward i-1
        c_known = c_sub[:i]
        trapz_known = 0.0
        if i >= 2:
            trapz_known = np.sum(0.5 * (c_known[:-1] + c_known[1:]) * du)
        # Last interval: between grid[i-1] (u = sqrt(t_n - t_{i-1})) and
        # grid[i] (u = 0), involving the unknown c(Gamma(t_n)).
        u_last = u[-1]
        c_prev = c_sub[i - 1]

        def residual(gamma_trial: float) -> float:
            c_trial = isotherm.c_subsurface(gamma_trial)
            trapz_last = 0.5 * (c_prev + c_trial) * u_last
            back_diffusion = trapz_known + trapz_last
            rhs = prefactor * (cb * math.sqrt(t_n) - back_diffusion)
            return gamma_trial - rhs

        lower = gamma[i - 1]
        if gamma_upper_limit is not None:
            upper = gamma_upper_limit * (1 - 1e-12)
        else:
            upper = max(lower * 2.0, prefactor * cb * math.sqrt(t_n) * 2.0, 1e-9)
            tries = 0
            while residual(upper) < 0 and tries < 60:
                upper *= 2.0
                tries += 1

        f_lower = residual(lower)
        f_upper = residual(upper)
        if f_lower == 0.0:
            gamma[i] = lower
        elif f_lower * f_upper > 0:
            # Bracket failed to capture a sign change: widen from zero as a
            # fallback before declaring non-convergence (do not silently
            # return a result from an un-bracketed solve).
            lower_fallback = 0.0
            f_lower_fb = residual(lower_fallback)
            if f_lower_fb * f_upper > 0:
                converged = False
                message = (
                    f"Root bracketing failed at t={t_n:.6g}s (step {i}/{n-1}); "
                    "forward solve aborted."
                )
                break
            gamma[i] = brentq(residual, lower_fallback, upper, xtol=1e-18, rtol=1e-12, maxiter=200)
        else:
            gamma[i] = brentq(residual, lower, upper, xtol=1e-18, rtol=1e-12, maxiter=200)

        try:
            isotherm.validate_gamma(gamma[i])
        except IsothermError as exc:
            converged = False
            message = f"Invalid Gamma at t={t_n:.6g}s: {exc}"
            break
        c_sub[i] = isotherm.c_subsurface(gamma[i])

    if not converged:
        return SimulationResult(
            time_s=time_s,
            gamma_mol_per_m2=np.full_like(time_s, np.nan),
            sigma_N_per_m=np.full_like(time_s, np.nan),
            converged=False,
            message=message,
        )

    # Extract results at exactly the requested times (all present in grid).
    idx = np.searchsorted(grid, time_s)
    # Guard against floating-point mismatches in the union/searchsorted step.
    idx = np.clip(idx, 0, n - 1)
    close = np.isclose(grid[idx], time_s, rtol=0, atol=1e-12)
    if not np.all(close):
        # Fall back to nearest-match (should not normally happen).
        idx = np.array([int(np.argmin(np.abs(grid - t))) for t in time_s])

    gamma_out = gamma[idx]
    sigma_out = isotherm.surface_tension(
        gamma_out, settings.temperature_K, settings.solvent_sigma0_N_per_m
    )

    equilibrium_gamma = None
    equilibrium_sigma = None
    try:
        equilibrium_gamma = isotherm.equilibrium_gamma(cb)
        equilibrium_sigma = isotherm.surface_tension(
            equilibrium_gamma, settings.temperature_K, settings.solvent_sigma0_N_per_m
        )
    except IsothermError:
        pass  # Equilibrium state not numerically determinable; leave as None.

    return SimulationResult(
        time_s=time_s,
        gamma_mol_per_m2=gamma_out,
        sigma_N_per_m=sigma_out,
        converged=True,
        message="Converged",
        equilibrium_gamma_mol_per_m2=equilibrium_gamma,
        equilibrium_sigma_N_per_m=equilibrium_sigma,
    )


def _solve_spherical(settings: FitSettings, time_s: np.ndarray) -> SimulationResult:
    """Solve fixed-radius spherical diffusion with a conservative shell grid."""
    time_s = np.asarray(time_s, dtype=float)
    if time_s.ndim != 1 or time_s.size == 0:
        raise ValueError("time_s must be a non-empty 1-D array")
    if np.any(~np.isfinite(time_s)) or np.any(time_s <= 0):
        raise ValueError("time_s must contain only finite, positive values")
    if settings.radius_m is None:
        raise ValueError("spherical geometry requires radius_m")

    try:
        isotherm = build_isotherm(settings.isotherm_name, settings.isotherm_params)
        radius = float(settings.radius_m)
        t_max = float(np.max(time_s))
        diffusion_length = math.sqrt(settings.diffusion_coefficient_m2_per_s * t_max)
        domain_length = max(2.0 * radius, 8.0 * diffusion_length)
        cell_count = 96
        faces = radius + np.linspace(0.0, domain_length, cell_count + 1)
        centers = 0.5 * (faces[:-1] + faces[1:])
        cell_volumes = (faces[1:] ** 3 - faces[:-1] ** 3) / 3.0
        widths = np.diff(faces)
        bulk = settings.bulk_concentration_mol_per_m3

        def rhs(_time: float, state: np.ndarray) -> np.ndarray:
            excess = state[:-1]
            gamma = float(state[-1])
            isotherm.validate_gamma(gamma)
            surface_excess_concentration = float(isotherm.c_subsurface(gamma) - bulk)
            gradients = np.empty(cell_count + 1)
            gradients[0] = (excess[0] - surface_excess_concentration) / (widths[0] / 2.0)
            gradients[-1] = -excess[-1] / (widths[-1] / 2.0)
            gradients[1:-1] = (excess[1:] - excess[:-1]) / (
                centers[1:] - centers[:-1]
            )
            radial_flux = settings.diffusion_coefficient_m2_per_s * gradients
            excess_rate = (
                faces[1:] ** 2 * radial_flux[1:]
                - faces[:-1] ** 2 * radial_flux[:-1]
            ) / cell_volumes
            gamma_rate = radial_flux[0]
            return np.concatenate((excess_rate, [gamma_rate]))

        unique_times = np.unique(time_s)
        integration_times = np.concatenate(([0.0], unique_times))
        initial_state = np.zeros(cell_count + 1)
        result = solve_ivp(
            rhs,
            (0.0, t_max),
            initial_state,
            method="BDF",
            t_eval=integration_times,
            rtol=2e-5,
            atol=np.concatenate((np.full(cell_count, 1e-8), [1e-14])),
            max_step=max(t_max / 50.0, 1e-8),
        )
        if not result.success or result.y.shape[1] != integration_times.size:
            message = result.message or "spherical integration did not reach all requested times"
            return SimulationResult(
                time_s=time_s,
                gamma_mol_per_m2=np.full_like(time_s, np.nan),
                sigma_N_per_m=np.full_like(time_s, np.nan),
                converged=False,
                message=f"Spherical solve failed: {message}",
            )

        gamma_by_time = result.y[-1, 1:]
        lookup = {value: index for index, value in enumerate(unique_times)}
        gamma_out = np.array([gamma_by_time[lookup[value]] for value in time_s])
        sigma_out = isotherm.surface_tension(
            gamma_out, settings.temperature_K, settings.solvent_sigma0_N_per_m
        )
        equilibrium_gamma = None
        equilibrium_sigma = None
        try:
            equilibrium_gamma = isotherm.equilibrium_gamma(bulk)
            equilibrium_sigma = isotherm.surface_tension(
                equilibrium_gamma,
                settings.temperature_K,
                settings.solvent_sigma0_N_per_m,
            )
        except IsothermError:
            pass
        return SimulationResult(
            time_s=time_s,
            gamma_mol_per_m2=gamma_out,
            sigma_N_per_m=sigma_out,
            converged=True,
            message="Converged (fixed-radius spherical geometry)",
            equilibrium_gamma_mol_per_m2=equilibrium_gamma,
            equilibrium_sigma_N_per_m=equilibrium_sigma,
        )
    except (IsothermError, ValueError, FloatingPointError) as exc:
        return SimulationResult(
            time_s=time_s,
            gamma_mol_per_m2=np.full_like(time_s, np.nan),
            sigma_N_per_m=np.full_like(time_s, np.nan),
            converged=False,
            message=f"Spherical solve failed: {exc}",
        )
