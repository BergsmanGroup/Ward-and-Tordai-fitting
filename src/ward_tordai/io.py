"""CSV input/output for experimental data, model predictions, and fit summaries.

No GUI code here; the GUI calls these pure functions.
"""
from __future__ import annotations

import io as _io
from typing import Optional

import numpy as np
import pandas as pd

from .models import ExperimentalData, FitResult, SimulationResult
from .units import (
    N_per_m_to_mN_per_m,
    TensionUnit,
    TimeUnit,
    seconds_to_time,
    tension_to_N_per_m,
    time_to_seconds,
)


class DataLoadError(ValueError):
    """Raised when experimental data cannot be parsed or fails validation."""


def _validate_and_sort(time_s: np.ndarray, sigma_N_per_m: np.ndarray) -> ExperimentalData:
    time_s = np.asarray(time_s, dtype=float)
    sigma_N_per_m = np.asarray(sigma_N_per_m, dtype=float)

    if time_s.size == 0:
        raise DataLoadError("No data rows found")
    if time_s.shape != sigma_N_per_m.shape:
        raise DataLoadError("Time and surface-tension columns must be the same length")

    if np.any(~np.isfinite(time_s)) or np.any(~np.isfinite(sigma_N_per_m)):
        raise DataLoadError("Data contains missing or non-finite values")
    if np.any(time_s <= 0):
        raise DataLoadError(
            "Data contains non-positive time/surface-age values, which cannot be "
            "plotted or fit on a logarithmic time axis"
        )

    order = np.argsort(time_s, kind="stable")
    return ExperimentalData(time_s=time_s[order], sigma_N_per_m=sigma_N_per_m[order])


def parse_text_columns(
    text: str,
    time_unit: TimeUnit,
    tension_unit: TensionUnit,
    delimiter: Optional[str] = None,
) -> ExperimentalData:
    """Parse pasted two-column (time, surface tension) data.

    Accepts whitespace-, comma-, or tab-delimited rows, with or without a
    header row (non-numeric header rows are skipped automatically).
    """
    try:
        df = pd.read_csv(
            _io.StringIO(text),
            sep=delimiter if delimiter is not None else r"[,\t\s]+",
            engine="python",
            header=None,
            comment="#",
            skip_blank_lines=True,
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise DataLoadError(f"Could not parse pasted data: {exc}") from exc

    if df.shape[1] < 2:
        raise DataLoadError("Expected at least two columns (time, surface tension)")
    df = df.iloc[:, :2]
    df.columns = ["time", "sigma"]
    df["time"] = pd.to_numeric(df["time"], errors="coerce")
    df["sigma"] = pd.to_numeric(df["sigma"], errors="coerce")
    df = df.dropna(how="all")
    if df.isna().any().any():
        raise DataLoadError(
            "Data contains missing or non-numeric values (after an optional header row)"
        )

    time_s = time_to_seconds(df["time"].to_numpy(dtype=float), time_unit)
    sigma_N_per_m = tension_to_N_per_m(df["sigma"].to_numpy(dtype=float), tension_unit)
    return _validate_and_sort(time_s, sigma_N_per_m)


def load_csv(
    path: str,
    time_unit: TimeUnit,
    tension_unit: TensionUnit,
    time_column: Optional[str] = None,
    sigma_column: Optional[str] = None,
) -> ExperimentalData:
    """Load a two-column CSV of (surface age, surface tension) data.

    If ``time_column``/``sigma_column`` are not given, the first two
    columns are used.
    """
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        raise DataLoadError(f"Could not read CSV file '{path}': {exc}") from exc

    if df.shape[1] < 2:
        raise DataLoadError("CSV must contain at least two columns")

    time_col = time_column if time_column is not None else df.columns[0]
    sigma_col = sigma_column if sigma_column is not None else df.columns[1]
    if time_col not in df.columns or sigma_col not in df.columns:
        raise DataLoadError(f"Columns '{time_col}'/'{sigma_col}' not found in CSV")

    time_raw = pd.to_numeric(df[time_col], errors="coerce").to_numpy(dtype=float)
    sigma_raw = pd.to_numeric(df[sigma_col], errors="coerce").to_numpy(dtype=float)

    time_s = time_to_seconds(time_raw, time_unit)
    sigma_N_per_m = tension_to_N_per_m(sigma_raw, tension_unit)
    return _validate_and_sort(time_s, sigma_N_per_m)


def export_predictions_csv(
    path: str,
    data: ExperimentalData,
    simulation: SimulationResult,
    time_unit: TimeUnit = TimeUnit.SECONDS,
) -> None:
    """Export measured vs. predicted surface tension at the measured times."""
    if simulation.time_s.shape != data.time_s.shape or not np.allclose(
        np.sort(simulation.time_s), np.sort(data.time_s)
    ):
        raise ValueError("simulation must have been evaluated at the data's measured times")

    out = pd.DataFrame(
        {
            f"time_{time_unit.value}": seconds_to_time(data.time_s, time_unit),
            "sigma_measured_mN_per_m": N_per_m_to_mN_per_m(data.sigma_N_per_m),
            "sigma_predicted_mN_per_m": N_per_m_to_mN_per_m(simulation.sigma_N_per_m),
            "gamma_predicted_mol_per_m2": simulation.gamma_mol_per_m2,
        }
    )
    out.to_csv(path, index=False)


def export_fit_summary_csv(path: str, fit_result: FitResult, settings) -> None:
    """Export a one-row CSV summarizing the fit and the parameters used."""
    row = {
        "fitted_D_m2_per_s": fit_result.fitted_D_m2_per_s,
        "rmse_mN_per_m": N_per_m_to_mN_per_m(fit_result.rmse_N_per_m)
        if np.isfinite(fit_result.rmse_N_per_m)
        else float("nan"),
        "n_observations": fit_result.n_observations,
        "success": fit_result.success,
        "message": fit_result.message,
        "isotherm_name": settings.isotherm_name,
        "bulk_concentration_mol_per_m3": settings.bulk_concentration_mol_per_m3,
        "temperature_K": settings.temperature_K,
        "solvent_sigma0_mN_per_m": N_per_m_to_mN_per_m(settings.solvent_sigma0_N_per_m),
    }
    if fit_result.simulation is not None:
        row["equilibrium_gamma_mol_per_m2"] = fit_result.simulation.equilibrium_gamma_mol_per_m2
        row["equilibrium_sigma_mN_per_m"] = (
            N_per_m_to_mN_per_m(fit_result.simulation.equilibrium_sigma_N_per_m)
            if fit_result.simulation.equilibrium_sigma_N_per_m is not None
            else float("nan")
        )
    for key, value in settings.isotherm_params.items():
        row[f"isotherm_param_{key}"] = value

    pd.DataFrame([row]).to_csv(path, index=False)
