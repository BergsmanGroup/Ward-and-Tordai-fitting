import math

import numpy as np
import pytest

from ward_tordai.models import FitSettings
from ward_tordai.solver import solve
import ward_tordai.solver as solver_module


LANGMUIR_PARAMS = {"a_mol_per_m3": 1.0 / 1838.0, "gamma_inf_mol_per_m2": 1.8e-6}


def _li_et_al_settings(D):
    return FitSettings(
        isotherm_name="langmuir",
        isotherm_params=LANGMUIR_PARAMS,
        bulk_concentration_mol_per_m3=5.44e-3,
        temperature_K=298.15,
        solvent_sigma0_N_per_m=0.072,
        diffusion_coefficient_m2_per_s=D,
    )


def test_solver_converges_and_is_monotonic_langmuir():
    settings = _li_et_al_settings(D=5e-10)
    times = np.geomspace(0.5, 3000.0, 15)
    result = solve(settings, times)
    assert result.converged, result.message
    assert np.all(np.isfinite(result.gamma_mol_per_m2))
    # Gamma must increase monotonically with time (adsorption, no desorption).
    assert np.all(np.diff(result.gamma_mol_per_m2) > 0)
    # Surface tension must decrease monotonically as Gamma builds up.
    assert np.all(np.diff(result.sigma_N_per_m) < 0)
    # Gamma must stay strictly below Gamma_inf and approach, but not exceed,
    # the equilibrium value.
    gamma_inf = LANGMUIR_PARAMS["gamma_inf_mol_per_m2"]
    assert np.all(result.gamma_mol_per_m2 < gamma_inf)
    assert result.equilibrium_gamma_mol_per_m2 < gamma_inf
    assert result.gamma_mol_per_m2[-1] < result.equilibrium_gamma_mol_per_m2 * 1.01


def test_early_time_matches_diffusion_limited_asymptote():
    """For small t, Gamma(t) -> 2*cb*sqrt(D*t/pi) (negligible back-diffusion)."""
    D = 5e-10
    cb = 5.44e-3
    settings = _li_et_al_settings(D=D)
    t_small = np.array([1e-4, 3e-4])
    result = solve(settings, t_small)
    assert result.converged, result.message
    expected = 2.0 * cb * np.sqrt(D * t_small / math.pi)
    np.testing.assert_allclose(result.gamma_mol_per_m2, expected, rtol=0.02)


def test_grid_refinement_converges():
    """Refining the internal grid should change the prediction by a
    shrinking amount (convergence of the numerical scheme)."""
    settings = _li_et_al_settings(D=5e-10)
    times = np.array([3000.0])

    original_grid_fn = solver_module._build_solve_grid
    sigmas = []
    for n in (50, 100, 200, 400, 800):
        def patched(requested_times_s, n_internal_points=200, min_time_s=None, _n=n):
            return original_grid_fn(requested_times_s, n_internal_points=_n, min_time_s=min_time_s)

        solver_module._build_solve_grid = patched
        try:
            result = solve(settings, times)
            assert result.converged
            sigmas.append(result.sigma_N_per_m[0])
        finally:
            solver_module._build_solve_grid = original_grid_fn

    diffs = np.abs(np.diff(sigmas))
    # Each refinement should bring successive results closer together.
    assert np.all(diffs[1:] < diffs[:-1] + 1e-12)
    # The finest two grids should agree closely.
    assert diffs[-1] < 1e-5  # N/m, i.e. < 0.01 mN/m


def test_legacy_vba_bisection_recursion_matches_new_solver():
    """Re-implements the legacy VBA workbook's own recursive algorithm
    (WardAndTordai.bas / EqAdsorb.bas, Langmuir, no curvature/micelle
    terms) independently in Python, and checks it agrees with this
    package's brentq-based solver within a documented tolerance."""

    def c_of_gamma(g, a, ginf):
        return a * g / (ginf - g)

    def vba_style_solve(D, cb, a, ginf, t):
        n = t.size
        G = np.zeros(n)
        C = np.zeros(n)
        for i in range(1, n):
            lo, hi = 0.0, ginf * (1 - 1e-10)

            def equal(g_trial):
                c_trial = c_of_gamma(g_trial, a, ginf)
                # Reconstruct back-diffusion sum exactly as PastBackDiff +
                # the final interval handled in Equal().
                csum = 0.0
                for j in range(0, i - 1):
                    f_a = 0.5 * (C[j + 1] + C[j])
                    f_b = math.sqrt(t[i] - t[j + 1]) - math.sqrt(t[i] - t[j])
                    csum += f_a * f_b
                eqA = math.sqrt(4 * D / math.pi)
                eqB = cb * math.sqrt(t[i])
                eqC = -0.5 * (c_trial + C[i - 1]) * math.sqrt(t[i] - t[i - 1])
                return g_trial - eqA * (eqB + eqC + csum)

            for _ in range(200):
                mid = 0.5 * (lo + hi)
                f_lo = equal(lo)
                f_mid = equal(mid)
                if abs(f_mid) < 1e-20 or (hi - lo) < 1e-18:
                    break
                if f_lo * f_mid < 0:
                    hi = mid
                else:
                    lo = mid
            G[i] = 0.5 * (lo + hi)
            C[i] = c_of_gamma(G[i], a, ginf)
        return G

    D = 5e-10
    cb = 5.44e-3
    a = LANGMUIR_PARAMS["a_mol_per_m3"]
    ginf = LANGMUIR_PARAMS["gamma_inf_mol_per_m2"]
    t = np.linspace(0.0, 500.0, 60)
    t[0] = 0.0

    legacy_gamma = vba_style_solve(D, cb, a, ginf, t)

    # Force the new solver to march over exactly the same uniform grid (no
    # internal log-spaced densification), so this is a true apples-to-apples
    # comparison of the two recursions rather than of two different grids
    # (grid-refinement behavior is covered separately, in
    # test_grid_refinement_converges).
    original_grid_fn = solver_module._build_solve_grid
    solver_module._build_solve_grid = lambda requested_times_s, n_internal_points=200, min_time_s=None: t
    try:
        settings = _li_et_al_settings(D=D)
        result = solve(settings, t[1:])
    finally:
        solver_module._build_solve_grid = original_grid_fn
    assert result.converged, result.message

    np.testing.assert_allclose(result.gamma_mol_per_m2, legacy_gamma[1:], rtol=2e-3)


def test_solver_rejects_nonpositive_times():
    settings = _li_et_al_settings(D=5e-10)
    with pytest.raises(ValueError):
        solve(settings, np.array([0.0, 1.0]))
    with pytest.raises(ValueError):
        solve(settings, np.array([-1.0]))


def test_solver_reports_failure_for_invalid_isotherm_params():
    settings = FitSettings(
        isotherm_name="langmuir",
        isotherm_params={"a_mol_per_m3": -1.0, "gamma_inf_mol_per_m2": 1.8e-6},
        bulk_concentration_mol_per_m3=5.44e-3,
        temperature_K=298.15,
        solvent_sigma0_N_per_m=0.072,
        diffusion_coefficient_m2_per_s=5e-10,
    )
    result = solve(settings, np.array([1.0, 10.0]))
    assert not result.converged
    assert "Invalid isotherm parameters" in result.message
