import numpy as np
import pytest

from PySide6.QtWidgets import QApplication

from ward_tordai.gui import ScientificDoubleSpinBox
from ward_tordai.io import load_csv
from ward_tordai.isotherms import SURFACTANT_PRESETS
from ward_tordai.units import TensionUnit, TimeUnit


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_scientific_spin_box_parses_lowercase_and_uppercase_notation(qapp):
    box = ScientificDoubleSpinBox(-1e30, 1e30)
    assert box.valueFromText("7e-11") == pytest.approx(7e-11)
    assert box.valueFromText("7E-11") == pytest.approx(7e-11)
    assert box.valueFromText("-3.25e9") == pytest.approx(-3.25e9)


def test_scientific_spin_box_parses_many_trailing_zeros(qapp):
    box = ScientificDoubleSpinBox(-1e30, 1e30)
    assert box.valueFromText("0.0000000001") == pytest.approx(1e-10)
    assert box.valueFromText("100000000000") == pytest.approx(1e11)


def test_scientific_spin_box_validate_accepts_in_progress_exponent(qapp):
    box = ScientificDoubleSpinBox(-1e30, 1e30)
    from PySide6.QtGui import QValidator

    state, _, _ = box.validate("7e-11", 5)
    assert state == QValidator.State.Acceptable
    state, _, _ = box.validate("7e-", 3)
    assert state != QValidator.State.Invalid
    state, _, _ = box.validate("7e", 2)
    assert state != QValidator.State.Invalid


def test_test_preset_reproduces_workbook_equilibrium_state(qapp):
    """The 'Test' preset's Langmuir parameters, bulk concentration,
    temperature, and solvent tension must exactly reproduce the legacy
    KBC workbook's own saved Console equilibrium state (Gamma_eq =
    2.8827375392714613e-10 mol/cm^2 = 2.8827... umol/m^2, sigma_eq =
    38.80869748765195 dyne/cm = mN/m)."""
    from ward_tordai.isotherms import LangmuirIsotherm
    from ward_tordai.units import (
        ConcentrationUnit,
        GammaInfUnit,
        celsius_to_kelvin,
        concentration_to_mol_per_m3,
        gamma_inf_to_mol_per_m2,
    )

    preset = SURFACTANT_PRESETS["Test (unknown surfactant)"]
    iso = LangmuirIsotherm(
        a_mol_per_m3=concentration_to_mol_per_m3(preset.a_M, ConcentrationUnit.MOLAR),
        gamma_inf_mol_per_m2=gamma_inf_to_mol_per_m2(
            preset.gamma_inf_umol_per_m2, GammaInfUnit.MICROMOL_PER_M2
        ),
    )
    cb = concentration_to_mol_per_m3(preset.suggested_bulk_conc_M, ConcentrationUnit.MOLAR)
    geq = iso.equilibrium_gamma(cb)
    seq = iso.surface_tension(
        geq,
        celsius_to_kelvin(preset.suggested_temperature_C),
        preset.suggested_sigma0_mN_per_m / 1000.0,
    )
    assert geq * 1e6 == pytest.approx(2.8827375392714613, rel=1e-4)
    assert seq * 1000 == pytest.approx(38.80869748765195, rel=1e-4)


def test_test_preset_fit_quality_against_real_experimental_data():
    """Fitting D with the 'Test' preset's parameters against the real
    experimental_data.csv (the same dataset used in the legacy workbook)
    must achieve a good fit (R^2 > 0.99), matching the workbook's own
    good-looking result."""
    import os

    from ward_tordai.fitting import fit_diffusivity
    from ward_tordai.models import FitSettings
    from ward_tordai.units import ConcentrationUnit, GammaInfUnit, celsius_to_kelvin, concentration_to_mol_per_m3, gamma_inf_to_mol_per_m2

    repo_root = os.path.join(os.path.dirname(__file__), "..")
    csv_path = os.path.join(repo_root, "experimental_data.csv")
    if not os.path.exists(csv_path):
        pytest.skip("experimental_data.csv not present in this checkout")

    data = load_csv(csv_path, time_unit=TimeUnit.SECONDS, tension_unit=TensionUnit.DYNE_PER_CM)
    preset = SURFACTANT_PRESETS["Test (unknown surfactant)"]
    settings = FitSettings(
        isotherm_name="langmuir",
        isotherm_params={
            "a_mol_per_m3": concentration_to_mol_per_m3(preset.a_M, ConcentrationUnit.MOLAR),
            "gamma_inf_mol_per_m2": gamma_inf_to_mol_per_m2(
                preset.gamma_inf_umol_per_m2, GammaInfUnit.MICROMOL_PER_M2
            ),
        },
        bulk_concentration_mol_per_m3=concentration_to_mol_per_m3(
            preset.suggested_bulk_conc_M, ConcentrationUnit.MOLAR
        ),
        temperature_K=celsius_to_kelvin(preset.suggested_temperature_C),
        solvent_sigma0_N_per_m=preset.suggested_sigma0_mN_per_m / 1000.0,
        diffusion_coefficient_m2_per_s=preset.suggested_D_m2_per_s,
    )
    fit = fit_diffusivity(settings, data)
    assert fit.success, fit.message
    assert fit.r_squared > 0.99
    assert fit.rmse_N_per_m * 1000 < 1.5  # mN/m
