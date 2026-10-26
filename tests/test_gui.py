import numpy as np
import pytest

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QValidator

from ward_tordai.gui import MainWindow, ScientificDoubleSpinBox
from ward_tordai.io import load_csv
from ward_tordai.models import ExperimentalData
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


def test_scientific_spin_box_accepts_suffix_and_uses_additive_tenth_steps(qapp):
    box = ScientificDoubleSpinBox(0.2, 2.0)
    box.setSuffix(" mM")
    box.setSingleStep(0.1)
    box._use_additive_step = True
    state, _, _ = box.validate("1.2 mM", len("1.2 mM"))
    assert state == QValidator.State.Acceptable
    assert box.valueFromText("1.2 mM") == pytest.approx(1.2)
    box.setValue(1.2)
    box.stepBy(1)
    assert box.value() == pytest.approx(1.3)
    box.stepBy(-2)
    assert box.value() == pytest.approx(1.1)


def test_main_window_contains_export_and_plot_controls_without_preset_popup(qapp, monkeypatch):
    information_calls = []
    monkeypatch.setattr(
        "ward_tordai.gui.QMessageBox.information",
        lambda *args, **kwargs: information_calls.append((args, kwargs)),
    )
    window = MainWindow()

    window._on_solute_changed("Triton X-100")

    assert window.simulation_point_count.value() == 100
    assert window.plot_title_value.placeholderText() == "Optional plot title"
    assert window.experimental_legend_value.text() == "Experimental"
    assert window.model_legend_value.text() == "Ward-Tordai"
    assert window.permutation_count_label.text() == "Fit permutations: 1 (D evaluations: 25)"
    assert window.temperature_last_used.text() == "23"
    assert window.concentration_last_used.text() == "1"
    assert window.sigma0_last_used.text() == "72.5"
    assert window.time_offset_last_used.text() == "0.0"
    assert window.temperature_last_used.isReadOnly() is False
    assert window.temperature_lower.isEnabled() is False
    assert window.fit_isotherm_lower["a_mol_per_m3"].minimum() == pytest.approx(1e-6)
    assert window.fit_isotherm_upper["a_mol_per_m3"].maximum() == pytest.approx(1e-3)
    assert window.fit_isotherm_lower["gamma_inf_mol_per_m2"].minimum() == pytest.approx(1.0)
    assert window.fit_isotherm_upper["gamma_inf_mol_per_m2"].maximum() == pytest.approx(10.0)
    assert window._build_settings().isotherm_params["a_mol_per_m3"] == pytest.approx(6.62e-3)
    window.fit_temperature_check.setChecked(True)
    assert window.temperature_last_used.isReadOnly() is True
    assert window.temperature_lower.isEnabled() is True
    window.plot_title_value.setText("Live plot title")
    assert window.figure.axes[0].get_title() == "Live plot title"
    assert not information_calls
    window.close()


def test_simulation_grid_uses_requested_number_of_points(qapp):
    window = MainWindow()
    window.data = ExperimentalData(
        np.array([0.001, 0.01, 1.0]),
        np.array([0.071, 0.060, 0.040]),
    )
    grid = window._simulation_grid_data(window.data)
    assert len(grid.time_s) == window.simulation_point_count.value() == 100
    assert not np.array_equal(grid.time_s, window.data.time_s)
    assert np.all(np.diff(grid.time_s) > 0)
    window.close()

