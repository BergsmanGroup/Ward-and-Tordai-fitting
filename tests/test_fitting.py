import numpy as np
import pytest

from ward_tordai.fitting import fit_diffusivity, simulate
from ward_tordai.models import ExperimentalData, FitSettings
from ward_tordai.solver import solve

LANGMUIR_PARAMS = {"a_mol_per_m3": 1.0 / 1838.0, "gamma_inf_mol_per_m2": 1.8e-6}


def _settings(D):
    return FitSettings(
        isotherm_name="langmuir",
        isotherm_params=LANGMUIR_PARAMS,
        bulk_concentration_mol_per_m3=5.44e-3,
        temperature_K=298.15,
        solvent_sigma0_N_per_m=0.072,
        diffusion_coefficient_m2_per_s=D,
    )


def test_fit_recovers_known_D_from_synthetic_data():
    true_D = 7.3e-10
    true_settings = _settings(true_D)
    times = np.geomspace(1.0, 2000.0, 20)
    sim = solve(true_settings, times)
    assert sim.converged

    data = ExperimentalData(time_s=times, sigma_N_per_m=sim.sigma_N_per_m)

    # Start the fit from a deliberately wrong initial guess.
    guess_settings = _settings(D=1e-9)
    fit_result = fit_diffusivity(guess_settings, data, log10_D_bounds=(-12.0, -8.0))

    assert fit_result.success, fit_result.message
    assert fit_result.fitted_D_m2_per_s == pytest.approx(true_D, rel=0.02)
    assert fit_result.rmse_N_per_m < 1e-6  # noise-free synthetic data
    assert fit_result.r_squared == pytest.approx(1.0, abs=1e-6)  # near-perfect fit


def test_fit_recovers_known_D_with_added_noise():
    rng = np.random.default_rng(42)
    true_D = 3.0e-10
    true_settings = _settings(true_D)
    times = np.geomspace(1.0, 1500.0, 25)
    sim = solve(true_settings, times)
    assert sim.converged

    noisy_sigma = sim.sigma_N_per_m + rng.normal(0, 2e-4, size=sim.sigma_N_per_m.shape)
    data = ExperimentalData(time_s=times, sigma_N_per_m=noisy_sigma)

    guess_settings = _settings(D=5e-9)
    fit_result = fit_diffusivity(guess_settings, data)

    assert fit_result.success, fit_result.message
    assert fit_result.fitted_D_m2_per_s == pytest.approx(true_D, rel=0.15)
    assert fit_result.r_squared > 0.95  # still a good fit despite noise


def test_simulate_uses_entered_D_without_fitting():
    settings = _settings(D=1e-9)
    times = np.array([1.0, 10.0, 100.0])
    data = ExperimentalData(time_s=times, sigma_N_per_m=np.array([0.070, 0.065, 0.060]))
    result = simulate(settings, data)
    assert result.converged
    assert settings.diffusion_coefficient_m2_per_s == 1e-9  # untouched


def test_fit_handles_empty_data():
    settings = _settings(D=1e-9)
    with pytest.raises(ValueError):
        fit_diffusivity(settings, ExperimentalData(time_s=np.array([]), sigma_N_per_m=np.array([])))


def test_fit_reports_failure_for_impossible_bounds():
    true_D = 7.3e-10
    true_settings = _settings(true_D)
    times = np.geomspace(1.0, 2000.0, 10)
    sim = solve(true_settings, times)
    data = ExperimentalData(time_s=times, sigma_N_per_m=sim.sigma_N_per_m)

    # Isotherm parameters are invalid -> every forward solve fails -> fit must
    # report failure rather than crash or silently return a bad D.
    bad_settings = FitSettings(
        isotherm_name="langmuir",
        isotherm_params={"a_mol_per_m3": -1.0, "gamma_inf_mol_per_m2": 1.8e-6},
        bulk_concentration_mol_per_m3=5.44e-3,
        temperature_K=298.15,
        solvent_sigma0_N_per_m=0.072,
        diffusion_coefficient_m2_per_s=1e-9,
    )
    result = fit_diffusivity(bad_settings, data)
    assert not result.success
