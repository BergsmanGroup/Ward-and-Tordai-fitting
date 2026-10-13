import numpy as np
import pandas as pd
import pytest

from ward_tordai.io import (
    DataLoadError,
    export_fit_summary_csv,
    export_predictions_csv,
    load_csv,
    parse_text_columns,
)
from ward_tordai.models import ExperimentalData, FitResult, FitSettings, SimulationResult
from ward_tordai.units import TensionUnit, TimeUnit


def test_load_csv_basic(tmp_path):
    path = tmp_path / "data.csv"
    pd.DataFrame(
        {"time_ms": [5000, 1000, 2000], "sigma_mN_per_m": [60.0, 70.0, 65.0]}
    ).to_csv(path, index=False)

    data = load_csv(path, time_unit=TimeUnit.MILLISECONDS, tension_unit=TensionUnit.MILLINEWTON_PER_METER)

    # Must be sorted ascending by time.
    assert np.all(np.diff(data.time_s) > 0)
    assert data.time_s[0] == pytest.approx(1.0)
    np.testing.assert_allclose(data.sigma_N_per_m, data.sigma_N_per_m)  # sanity


def test_load_csv_preserves_duplicates(tmp_path):
    path = tmp_path / "data.csv"
    pd.DataFrame({"t": [1, 1, 2], "s": [70.0, 69.5, 68.0]}).to_csv(path, index=False)
    data = load_csv(path, time_unit=TimeUnit.SECONDS, tension_unit=TensionUnit.MILLINEWTON_PER_METER)
    assert len(data) == 3


def test_load_csv_rejects_nonpositive_time(tmp_path):
    path = tmp_path / "data.csv"
    pd.DataFrame({"t": [0, 1, 2], "s": [70.0, 69.0, 68.0]}).to_csv(path, index=False)
    with pytest.raises(DataLoadError):
        load_csv(path, time_unit=TimeUnit.SECONDS, tension_unit=TensionUnit.MILLINEWTON_PER_METER)


def test_load_csv_rejects_missing_values(tmp_path):
    path = tmp_path / "data.csv"
    pd.DataFrame({"t": [1, 2, 3], "s": [70.0, None, 68.0]}).to_csv(path, index=False)
    with pytest.raises(DataLoadError):
        load_csv(path, time_unit=TimeUnit.SECONDS, tension_unit=TensionUnit.MILLINEWTON_PER_METER)


def test_parse_text_columns_whitespace_and_header():
    text = "time sigma\n1 70.0\n2 69.0\n3 68.0\n"
    data = parse_text_columns(text, time_unit=TimeUnit.SECONDS, tension_unit=TensionUnit.MILLINEWTON_PER_METER)
    assert len(data) == 3
    assert data.time_s[0] == pytest.approx(1.0)


def test_parse_text_columns_comma_delimited():
    text = "1,70.0\n2,69.0\n3,68.0\n"
    data = parse_text_columns(text, time_unit=TimeUnit.SECONDS, tension_unit=TensionUnit.MILLINEWTON_PER_METER)
    assert len(data) == 3


def test_parse_text_columns_rejects_non_numeric():
    text = "a,b\nfoo,bar\n"
    with pytest.raises(DataLoadError):
        parse_text_columns(text, time_unit=TimeUnit.SECONDS, tension_unit=TensionUnit.MILLINEWTON_PER_METER)


def test_export_predictions_csv(tmp_path):
    data = ExperimentalData(time_s=np.array([1.0, 2.0]), sigma_N_per_m=np.array([0.070, 0.065]))
    sim = SimulationResult(
        time_s=np.array([1.0, 2.0]),
        gamma_mol_per_m2=np.array([1e-7, 2e-7]),
        sigma_N_per_m=np.array([0.069, 0.064]),
        converged=True,
    )
    out_path = tmp_path / "predictions.csv"
    export_predictions_csv(out_path, data, sim)
    df = pd.read_csv(out_path)
    assert "sigma_measured_mN_per_m" in df.columns
    assert "sigma_predicted_mN_per_m" in df.columns
    assert len(df) == 2


def test_export_fit_summary_csv(tmp_path):
    settings = FitSettings(
        isotherm_name="langmuir",
        isotherm_params={"a_mol_per_m3": 1e-4, "gamma_inf_mol_per_m2": 3e-6},
        bulk_concentration_mol_per_m3=1e-3,
        temperature_K=296.15,
        solvent_sigma0_N_per_m=0.0725,
        diffusion_coefficient_m2_per_s=1e-9,
    )
    sim = SimulationResult(
        time_s=np.array([1.0]),
        gamma_mol_per_m2=np.array([1e-7]),
        sigma_N_per_m=np.array([0.069]),
        converged=True,
        equilibrium_gamma_mol_per_m2=2e-6,
        equilibrium_sigma_N_per_m=0.05,
    )
    fit_result = FitResult(
        fitted_D_m2_per_s=1.2e-9,
        simulation=sim,
        rmse_N_per_m=1e-4,
        n_observations=10,
        success=True,
        message="ok",
        r_squared=0.987,
    )
    out_path = tmp_path / "summary.csv"
    export_fit_summary_csv(out_path, fit_result, settings)
    df = pd.read_csv(out_path)
    assert df.loc[0, "fitted_D_m2_per_s"] == pytest.approx(1.2e-9)
    assert df.loc[0, "isotherm_param_a_mol_per_m3"] == pytest.approx(1e-4)
    assert df.loc[0, "r_squared"] == pytest.approx(0.987)
