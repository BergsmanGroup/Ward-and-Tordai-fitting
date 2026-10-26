"""PySide6 GUI: presentation and orchestration only.

No mathematical expressions or optimizer calls live in button callbacks;
they only gather UI state into dataclasses and delegate to
``solver``/``fitting``/``io``/``plotting``.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from typing import Optional

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator, QValidator
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QToolButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .config import (
    BUILTIN_PROFILE_NAMES,
    ParameterConfigError,
    builtin_fitting_profiles,
    custom_profile_directory,
    load_custom_fitting_profiles,
    save_custom_fitting_profile,
    safe_profile_filename,
)
from .fitting import fit_profiled_parameters, simulate
from .io import (
    DataLoadError,
    export_fit_summary_workbook,
    load_csv,
    parse_text_columns,
)
from .isotherms import SURFACTANT_PRESETS, IsothermError
from .models import ExperimentalData, FitSettings
from .plotting import plot_sigma_vs_time, save_figure_png
from .units import (
    ConcentrationUnit,
    GammaInfUnit,
    TensionUnit,
    TimeUnit,
    celsius_to_kelvin,
    concentration_to_mol_per_m3,
    gamma_inf_to_mol_per_m2,
    tension_to_N_per_m,
)

ISOTHERM_DISPLAY_NAMES = {
    "henry": "Henry",
    "langmuir": "Langmuir",
    "frumkin": "Frumkin",
    "generalized_frumkin": "Generalized Frumkin",
}


class ScientificDoubleSpinBox(QDoubleSpinBox):
    """A QDoubleSpinBox that accepts plain decimal *or* scientific notation.

    The stock ``QDoubleSpinBox`` validator rejects 'e'/'E' entirely and
    limits the number of typed digits to its ``decimals()`` setting, which
    makes it impossible to type values like ``7e-11`` or extra trailing
    zeros of a single significant figure (e.g. ``0.0000000001``). This
    subclass accepts any text a ``QDoubleValidator`` in scientific-notation
    mode allows, and parses/formats the value itself so no digit budget is
    imposed on typing.
    """

    def __init__(self, minimum: float = -1e30, maximum: float = 1e30, parent=None):
        super().__init__(parent)
        self._use_additive_step = False
        self._validator = QDoubleValidator(minimum, maximum, 18, self)
        self._validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
        # A generous internal 'decimals' so Qt's own rounding never clips
        # a typed value; actual validation/formatting is overridden below.
        self.setDecimals(18)
        self.setRange(minimum, maximum)

    def validate(self, text: str, pos: int):
        if not hasattr(self, "_validator"):
            # Called by Qt's own __init__ plumbing before our constructor
            # body has run; defer to the base implementation just this once.
            return super().validate(text, pos)
        suffix = self.suffix()
        numeric_text = text
        if suffix and numeric_text.rstrip().endswith(suffix):
            numeric_text = numeric_text.rstrip()[: -len(suffix)].rstrip()
        if numeric_text.strip() in ("", "-", "+", ".", "-.", "e", "E"):
            return (QValidator.State.Intermediate, text, pos)
        # Allow a trailing 'e'/'e-'/'e+' while the user is still typing the
        # exponent, which QDoubleValidator alone treats as Invalid.
        stripped = numeric_text.rstrip()
        if stripped and stripped[-1] in "eE+-":
            probe = stripped + "1"
            state, _, _ = self._validator.validate(probe, len(probe))
            if state != QValidator.State.Invalid:
                return (QValidator.State.Intermediate, text, pos)
        state, _, _ = self._validator.validate(numeric_text, pos)
        return (state, text, pos)

    def valueFromText(self, text: str) -> float:
        suffix = self.suffix()
        if suffix and text.rstrip().endswith(suffix):
            text = text.rstrip()[: -len(suffix)].rstrip()
        try:
            return float(text)
        except ValueError:
            return self.value()

    def textFromValue(self, value: float) -> str:
        return f"{value:.6g}"

    def stepBy(self, steps: int) -> None:
        if self._use_additive_step:
            self.setValue(self.value() + steps * self.singleStep())
            return
        # Multiplicative stepping is more useful than additive stepping
        # across many orders of magnitude (diffusivities, concentrations).
        factor = 1.1 ** steps
        new_value = self.value() * factor if self.value() != 0 else steps * 1e-12
        self.setValue(new_value)


def _spin(minimum, maximum, decimals, value, step=None, suffix=""):
    box = ScientificDoubleSpinBox(minimum, maximum)
    if step is not None:
        box.setSingleStep(step)
        box._use_additive_step = True
    box.setValue(value)
    if suffix:
        box.setSuffix(" " + suffix)
    return box


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Ward-Tordai Profile Fitting")
        self.resize(1150, 750)

        self.data: Optional[ExperimentalData] = None
        self.last_fit = None
        self.profile_folder = custom_profile_directory()
        self.fitting_profiles = builtin_fitting_profiles()
        self.fitting_profiles.update(load_custom_fitting_profiles(self.profile_folder))
        self.parameter_sets = {
            name: profile["values"]
            for name, profile in self.fitting_profiles.items()
        }
        self._profile_edit_guard = False
        self._base_solute_name = "HTAB"

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self._build_data_group())
        left_layout.addWidget(self._build_solution_group())
        left_layout.addWidget(self._build_actions_group())
        left_layout.addStretch(1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.figure = Figure(figsize=(6, 5), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)
        right_layout.addWidget(self.canvas, stretch=3)
        self.results_box = QPlainTextEdit()
        self.results_box.setReadOnly(True)
        self.results_box.setMaximumHeight(160)
        right_layout.addWidget(self.results_box, stretch=1)
        splitter.addWidget(right)
        splitter.setSizes([600, 850])

        self._redraw_plot()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_data_group(self) -> QGroupBox:
        box = QGroupBox("1. Experimental data")
        layout = QVBoxLayout(box)

        form = QFormLayout()
        self.time_unit_combo = QComboBox()
        self.time_unit_combo.addItems([u.value for u in TimeUnit])
        form.addRow("Time unit:", self.time_unit_combo)

        self.tension_unit_combo = QComboBox()
        self.tension_unit_combo.addItems([u.value for u in TensionUnit])
        form.addRow("Surface tension unit:", self.tension_unit_combo)
        layout.addLayout(form)

        self.paste_edit = QPlainTextEdit()
        self.paste_edit.setPlaceholderText(
            "Paste two columns here (time, surface tension), or load a CSV below."
        )
        self.paste_edit.setMaximumHeight(90)
        layout.addWidget(self.paste_edit)

        btn_row = QHBoxLayout()
        load_csv_btn = QPushButton("Load CSV...")
        load_csv_btn.clicked.connect(self._on_load_csv)
        use_pasted_btn = QPushButton("Use pasted data")
        use_pasted_btn.clicked.connect(self._on_use_pasted)
        use_example_btn = QPushButton("Use example data")
        use_example_btn.clicked.connect(self._on_use_example_data)
        btn_row.addWidget(load_csv_btn)
        btn_row.addWidget(use_pasted_btn)
        btn_row.addWidget(use_example_btn)
        layout.addLayout(btn_row)

        self.data_status_label = QLabel("No data loaded.")
        layout.addWidget(self.data_status_label)
        return box

    def _build_solution_group_legacy(self) -> QGroupBox:
        box = QGroupBox("2. Solution & adsorption isotherm")
        layout = QVBoxLayout(box)
        top_row = QHBoxLayout()

        self.solute_combo = QComboBox()
        self.solute_combo.addItem("Custom")
        self.solute_combo.addItems(sorted(self.parameter_sets))
        self.solute_combo.currentTextChanged.connect(self._on_solute_changed)
        top_row.addLayout(self._labeled_control("Solute:", self.solute_combo))

        self.solvent_combo = QComboBox()
        self.solvent_combo.addItems(["Water", "Custom"])
        self.solvent_combo.currentTextChanged.connect(self._on_solvent_changed)
        self.sigma0_value = _spin(1.0, 200.0, 3, 72.5, suffix="mN/m")
        solvent_control = QWidget()
        solvent_layout = QHBoxLayout(solvent_control)
        solvent_layout.setContentsMargins(0, 0, 0, 0)
        solvent_layout.addWidget(self.solvent_combo)
        solvent_layout.addWidget(self.sigma0_value)
        top_row.addLayout(self._labeled_control("Solvent:", solvent_control))

        self.conc_value = _spin(1e-12, 1e6, 8, 1.0)
        self.conc_unit_combo = QComboBox()
        self.conc_unit_combo.addItems([u.value for u in ConcentrationUnit])
        conc_control = QWidget()
        conc_layout = QHBoxLayout(conc_control)
        conc_layout.setContentsMargins(0, 0, 0, 0)
        conc_layout.addWidget(self.conc_value)
        conc_layout.addWidget(self.conc_unit_combo)
        self.isotherm_combo = QComboBox()
        self.isotherm_combo.addItems(list(ISOTHERM_DISPLAY_NAMES.values()))
        self.isotherm_combo.currentTextChanged.connect(self._on_isotherm_changed)
        top_row.addLayout(self._labeled_control("Concentration:", conc_control))
        top_row.addLayout(self._labeled_control("Isotherm:", self.isotherm_combo))
        layout.addLayout(top_row)

        form = QFormLayout()
        self.a_value = _spin(1e-15, 1e6, 10, 6.62e-6)
        form.addRow("a (characteristic conc., M):", self.a_value)

        self.gamma_inf_value = _spin(1e-6, 1e6, 6, 2.91)
        form.addRow("Gamma_inf (umol/m^2):", self.gamma_inf_value)

        self.k_value = _spin(-100.0, 100.0, 6, 0.0)
        self.k_label = QLabel("k (interaction parameter):")
        form.addRow(self.k_label, self.k_value)

        self.p_value = _spin(1e-6, 100.0, 6, 1.0)
        self.p_label = QLabel("p (generalized exponent):")
        form.addRow(self.p_label, self.p_value)

        self.parameter_panel = QWidget()
        self.parameter_panel.setLayout(form)
        self.parameter_toggle = QToolButton()
        self.parameter_toggle.setText("Isotherm parameters")
        self.parameter_toggle.setCheckable(True)
        self.parameter_toggle.setChecked(True)
        self.parameter_toggle.setArrowType(Qt.ArrowType.DownArrow)
        self.parameter_toggle.toggled.connect(self._on_parameter_panel_toggled)
        layout.addWidget(self.parameter_toggle)
        layout.addWidget(self.parameter_panel)
        self._isotherm_form = form
        self._on_isotherm_changed(self.isotherm_combo.currentText())

        save_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save_parameters)
        restore_btn = QPushButton("Restore defaults")
        restore_btn.clicked.connect(self._on_restore_defaults)
        save_row.addWidget(save_btn)
        save_row.addWidget(restore_btn)
        layout.addLayout(save_row)
        self._on_profile_changed(self.fitting_profile_combo.currentText())
        editable_controls = [
            self.d_last_used, self.temperature_last_used, self.concentration_last_used,
            self.sigma0_last_used, self.time_offset_last_used,
            self.d_lower_exp, self.d_upper_exp, self.d_n_values,
            self.temperature_lower, self.temperature_upper, self.temperature_n_values,
            self.fit_concentration_lower, self.fit_concentration_upper, self.concentration_n_values,
            self.fit_sigma0_lower, self.fit_sigma0_upper, self.sigma0_n_values,
            self.fit_time_offset_lower, self.fit_time_offset_upper, self.time_offset_n_values,
            *self.fit_isotherm_lower.values(), *self.fit_isotherm_upper.values(),
            *self.fit_isotherm_n.values(), *self.fit_isotherm_value.values(),
        ]
        for control in editable_controls:
            signal = getattr(control, "textChanged", None) or getattr(control, "valueChanged", None)
            if signal is not None:
                signal.connect(self._on_profile_edited)
        for control in (
            self.fit_temperature_check, self.fit_concentration_check,
            self.fit_sigma0_check, self.fit_time_offset_check,
            *self.fit_isotherm_checks.values(),
        ):
            control.toggled.connect(self._on_profile_edited)
        self.isotherm_combo.currentTextChanged.connect(self._on_profile_edited)
        return box

    def _build_solution_group(self) -> QGroupBox:
        box = QGroupBox("2. Fitting profile")
        layout = QVBoxLayout(box)

        selectors = QHBoxLayout()
        self.fitting_profile_combo = QComboBox()
        self.fitting_profile_combo.addItems(sorted(self.fitting_profiles))
        self.fitting_profile_combo.currentTextChanged.connect(self._on_profile_changed)
        self.solute_combo = self.fitting_profile_combo
        profile_control = QWidget()
        profile_layout = QHBoxLayout(profile_control)
        profile_layout.setContentsMargins(0, 0, 0, 0)
        profile_layout.addWidget(self.fitting_profile_combo)
        refresh_profiles_btn = QPushButton("Refresh")
        refresh_profiles_btn.clicked.connect(self._reload_profiles)
        profile_layout.addWidget(refresh_profiles_btn)
        selectors.addLayout(self._labeled_control("Fitting profile:", profile_control))
        self.permutation_count_label = QLabel()
        selectors.addWidget(self.permutation_count_label)
        self.isotherm_combo = QComboBox()
        self.isotherm_combo.addItems(list(ISOTHERM_DISPLAY_NAMES.values()))
        self.isotherm_combo.setCurrentText(ISOTHERM_DISPLAY_NAMES["langmuir"])
        self.isotherm_combo.currentTextChanged.connect(self._on_isotherm_changed)
        selectors.addLayout(self._labeled_control("Isotherm:", self.isotherm_combo))
        layout.addLayout(selectors)

        self.d_last_used = QLineEdit("1e-9")
        self.d_last_used.setReadOnly(True)
        self.temperature_last_used = QLineEdit("23.0")
        self.concentration_last_used = QLineEdit("1.0")
        self.sigma0_last_used = QLineEdit("72.5")
        self.time_offset_last_used = QLineEdit("0.0")

        self.fit_temperature_check = QCheckBox()
        self.fit_concentration_check = QCheckBox()
        self.fit_sigma0_check = QCheckBox()
        self.fit_time_offset_check = QCheckBox()
        self.fit_isotherm_checks: dict[str, QCheckBox] = {}
        self.fit_isotherm_lower: dict[str, ScientificDoubleSpinBox] = {}
        self.fit_isotherm_upper: dict[str, ScientificDoubleSpinBox] = {}
        self.fit_isotherm_n: dict[str, QSpinBox] = {}
        self.fit_isotherm_value: dict[str, ScientificDoubleSpinBox] = {}

        table = QGridLayout()
        headers = ("Parameter", "Fit", "Lower bound", "Upper bound", "N values", "Value")
        for column, header in enumerate(headers):
            table.addWidget(QLabel(header), 0, column)

        self.d_lower_exp = _spin(-16.0, -4.0, 1, -13.0, step=0.1)
        self.d_upper_exp = _spin(-16.0, -4.0, 1, -7.0, step=0.1)
        self.d_n_values = QSpinBox()
        self.d_n_values.setRange(2, 1000)
        self.d_n_values.setValue(25)
        self._add_parameter_row(
            table, 1, "D (log10)", None, self.d_lower_exp, self.d_upper_exp,
            self.d_n_values, self.d_last_used, always_fit=True
        )

        self.temperature_lower = _spin(-20.0, 150.0, 2, 20.0, step=0.1, suffix="degC")
        self.temperature_upper = _spin(-20.0, 150.0, 2, 26.0, step=0.1, suffix="degC")
        self.temperature_n_values = QSpinBox()
        self.temperature_n_values.setRange(2, 1000)
        self.temperature_n_values.setValue(9)
        self._add_parameter_row(
            table, 2, "Temperature (degC)", self.fit_temperature_check,
            self.temperature_lower, self.temperature_upper, self.temperature_n_values,
            self.temperature_last_used
        )

        self.fit_concentration_check.setToolTip(
            "Use only when the entered value is a nominal total concentration."
        )
        self.fit_concentration_lower = _spin(0.2, 2.0, 4, 0.2, step=0.1, suffix="mM")
        self.fit_concentration_upper = _spin(0.2, 2.0, 4, 2.0, step=0.1, suffix="mM")
        self.concentration_n_values = QSpinBox()
        self.concentration_n_values.setRange(2, 1000)
        self.concentration_n_values.setValue(9)
        self._add_parameter_row(
            table, 3, "Concentration (mM)", self.fit_concentration_check,
            self.fit_concentration_lower, self.fit_concentration_upper,
            self.concentration_n_values, self.concentration_last_used
        )

        self.fit_sigma0_lower = _spin(65.0, 80.0, 4, 70.0, step=0.1, suffix="mN/m")
        self.fit_sigma0_upper = _spin(65.0, 80.0, 4, 75.0, step=0.1, suffix="mN/m")
        self.sigma0_n_values = QSpinBox()
        self.sigma0_n_values.setRange(2, 1000)
        self.sigma0_n_values.setValue(9)
        self._add_parameter_row(
            table, 4, "Solvent sigma0 (mN/m)", self.fit_sigma0_check,
            self.fit_sigma0_lower, self.fit_sigma0_upper, self.sigma0_n_values,
            self.sigma0_last_used
        )

        self.fit_time_offset_lower = _spin(-10.0, 10.0, 4, -2.0, step=0.1, suffix="s")
        self.fit_time_offset_upper = _spin(-10.0, 10.0, 4, 2.0, step=0.1, suffix="s")
        self.time_offset_n_values = QSpinBox()
        self.time_offset_n_values.setRange(2, 1000)
        self.time_offset_n_values.setValue(9)
        self._add_parameter_row(
            table, 5, "Time offset (s)", self.fit_time_offset_check,
            self.fit_time_offset_lower, self.fit_time_offset_upper,
            self.time_offset_n_values, self.time_offset_last_used
        )
        for checkbox in (
            self.fit_temperature_check,
            self.fit_concentration_check,
            self.fit_sigma0_check,
            self.fit_time_offset_check,
        ):
            checkbox.toggled.connect(self._update_fit_parameter_controls)

        self._isotherm_table = table
        self._isotherm_rows: dict[str, list[QWidget]] = {}
        for row, (name, label, low, high, n, value) in enumerate(
            (
                ("a_mol_per_m3", "a (M)", 1e-6, 1e-3, 9, 6.62e-6),
                ("gamma_inf_mol_per_m2", "Gamma_inf (umol/m2)", 1.0, 10.0, 9, 2.91),
                ("k", "k", -100.0, 100.0, 9, 0.0),
                ("p", "p", 1e-6, 100.0, 9, 1.0),
            ),
            start=6,
        ):
            check = QCheckBox()
            spin_low = _spin(low, high, 8, low, step=0.1)
            spin_high = _spin(low, high, 8, high, step=0.1)
            n_box = QSpinBox()
            n_box.setRange(2, 1000)
            n_box.setValue(n)
            value_box = _spin(low, high, 8, value, step=0.1)
            self.fit_isotherm_checks[name] = check
            self.fit_isotherm_lower[name] = spin_low
            self.fit_isotherm_upper[name] = spin_high
            self.fit_isotherm_n[name] = n_box
            self.fit_isotherm_value[name] = value_box
            row_widgets = [QLabel(label), check, spin_low, spin_high, n_box, value_box]
            self._isotherm_rows[name] = row_widgets
            for column, widget in enumerate(row_widgets):
                table.addWidget(widget, row, column)
            check.toggled.connect(self._update_fit_parameter_controls)

        layout.addLayout(table)
        self._on_isotherm_changed(self.isotherm_combo.currentText())
        self._update_fit_parameter_controls()

        simulate_btn = QPushButton("Simulate exact Value column")
        simulate_btn.clicked.connect(self._on_simulate)
        layout.addWidget(simulate_btn)

        save_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save_parameters)
        restore_btn = QPushButton("Restore defaults")
        restore_btn.clicked.connect(self._on_restore_defaults)
        save_row.addWidget(save_btn)
        save_row.addWidget(restore_btn)
        layout.addLayout(save_row)
        return box

    def _add_parameter_row(
        self, table, row, label, checkbox, lower, upper, n_values, value, always_fit=False
    ):
        table.addWidget(QLabel(label), row, 0)
        table.addWidget(QLabel("always" if always_fit else ""), row, 1)
        if checkbox is not None:
            table.addWidget(checkbox, row, 1)
        table.addWidget(lower, row, 2)
        table.addWidget(upper, row, 3)
        table.addWidget(n_values, row, 4)
        table.addWidget(value, row, 5)

    @staticmethod
    def _labeled_control(label: str, control: QWidget) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.addWidget(QLabel(label))
        layout.addWidget(control)
        return layout

    def _on_parameter_panel_toggled(self, expanded: bool) -> None:
        self.parameter_panel.setVisible(expanded)
        self.parameter_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )

    def _on_solvent_changed(self, name: str) -> None:
        return

    def _refresh_solute_choices(self, selected: Optional[str] = None) -> None:
        self.fitting_profile_combo.blockSignals(True)
        self.fitting_profile_combo.clear()
        self.fitting_profile_combo.addItems(sorted(self.fitting_profiles))
        if selected:
            self.fitting_profile_combo.setCurrentText(selected)
        self.fitting_profile_combo.blockSignals(False)

    def _on_profile_changed(self, name: str) -> None:
        profile = self.fitting_profiles.get(name)
        if profile is None:
            return
        self._profile_edit_guard = True
        self._base_solute_name = profile.get("base_solute", name)
        self.isotherm_combo.setCurrentText(
            ISOTHERM_DISPLAY_NAMES.get(profile.get("isotherm_name", "langmuir"), "Langmuir")
        )
        values = profile["values"]
        self.d_last_used.setText(f"{values['D']:.6g}")
        self.temperature_last_used.setText(f"{values['temperature_C']:.6g}")
        self.concentration_last_used.setText(f"{values['concentration_mM']:.6g}")
        self.sigma0_last_used.setText(f"{values['solvent_sigma0_mN_per_m']:.6g}")
        self.time_offset_last_used.setText(f"{values['time_offset_s']:.1f}")
        for name, field in self.fit_isotherm_value.items():
            field.setValue(values.get({
                "a_mol_per_m3": "a_M",
                "gamma_inf_mol_per_m2": "gamma_inf_umol_per_m2",
            }.get(name, name), field.value()))
        bounds = profile["bounds"]
        self.d_lower_exp.setValue(bounds["D"][0])
        self.d_upper_exp.setValue(bounds["D"][1])
        self.temperature_lower.setValue(bounds["temperature_C"][0])
        self.temperature_upper.setValue(bounds["temperature_C"][1])
        self.fit_concentration_lower.setValue(bounds["concentration_mM"][0])
        self.fit_concentration_upper.setValue(bounds["concentration_mM"][1])
        self.fit_sigma0_lower.setValue(bounds["solvent_sigma0_mN_per_m"][0])
        self.fit_sigma0_upper.setValue(bounds["solvent_sigma0_mN_per_m"][1])
        self.fit_time_offset_lower.setValue(bounds["time_offset_s"][0])
        self.fit_time_offset_upper.setValue(bounds["time_offset_s"][1])
        for name, field in self.fit_isotherm_lower.items():
            key = {"a_mol_per_m3": "a_M", "gamma_inf_mol_per_m2": "gamma_inf_umol_per_m2"}.get(name, name)
            field.setValue(bounds[key][0])
            self.fit_isotherm_upper[name].setValue(bounds[key][1])
        for name, field in self.fit_isotherm_n.items():
            field.setValue(profile["n_values"].get(name, field.value()))
        self.fit_temperature_check.setChecked(profile["fit"].get("temperature", False))
        self.fit_concentration_check.setChecked(profile["fit"].get("concentration", False))
        self.fit_sigma0_check.setChecked(profile["fit"].get("solvent_sigma0", False))
        self.fit_time_offset_check.setChecked(profile["fit"].get("time_offset", False))
        for name, checkbox in self.fit_isotherm_checks.items():
            checkbox.setChecked(profile["fit"].get(name, False))
        self._profile_edit_guard = False
        self._update_fit_parameter_controls()

    def _on_profile_edited(self, *_args) -> None:
        if self._profile_edit_guard:
            return
        self._update_permutation_count()
        current = self.fitting_profile_combo.currentText()
        if current in BUILTIN_PROFILE_NAMES:
            custom_name = self._next_custom_profile_name(self._base_solute_name)
            self.fitting_profiles[custom_name] = self._profile_from_controls()
            self.parameter_sets = {n: p["values"] for n, p in self.fitting_profiles.items()}
            self.fitting_profile_combo.blockSignals(True)
            self.fitting_profile_combo.addItem(custom_name)
            self.fitting_profile_combo.setCurrentText(custom_name)
            self.fitting_profile_combo.blockSignals(False)
        elif current.startswith("Custom ("):
            self.fitting_profiles[current] = self._profile_from_controls()

    def _next_custom_profile_name(self, base_name: str) -> str:
        prefix = f"Custom ({base_name})"
        existing = [name for name in self.fitting_profiles if name.startswith(prefix)]
        if not existing:
            return prefix
        index = 1
        while f"{prefix}({index})" in existing:
            index += 1
        return f"{prefix}({index})"

    def _current_parameter_values(self) -> dict[str, float]:
        return {
            "a_M": self.fit_isotherm_value["a_mol_per_m3"].value(),
            "gamma_inf_umol_per_m2": self.fit_isotherm_value[
                "gamma_inf_mol_per_m2"
            ].value(),
            "k": self.fit_isotherm_value["k"].value(),
            "p": self.fit_isotherm_value["p"].value(),
        }

    def _on_solute_changed(self, name: str) -> None:
        self._on_profile_changed(name)

    def _profile_from_controls(self) -> dict:
        values = {
            "D": self._read_last_used(self.d_last_used, "D"),
            "temperature_C": self._read_last_used(self.temperature_last_used, "temperature"),
            "concentration_mM": self._read_last_used(self.concentration_last_used, "concentration"),
            "solvent_sigma0_mN_per_m": self._read_last_used(self.sigma0_last_used, "solvent sigma0"),
            "time_offset_s": self._read_last_used(self.time_offset_last_used, "time offset"),
            "a_M": self.fit_isotherm_value["a_mol_per_m3"].value(),
            "gamma_inf_umol_per_m2": self.fit_isotherm_value["gamma_inf_mol_per_m2"].value(),
            "k": self.fit_isotherm_value["k"].value(),
            "p": self.fit_isotherm_value["p"].value(),
        }
        bounds = {
            "D": [self.d_lower_exp.value(), self.d_upper_exp.value()],
            "temperature_C": [self.temperature_lower.value(), self.temperature_upper.value()],
            "concentration_mM": [self.fit_concentration_lower.value(), self.fit_concentration_upper.value()],
            "solvent_sigma0_mN_per_m": [self.fit_sigma0_lower.value(), self.fit_sigma0_upper.value()],
            "time_offset_s": [self.fit_time_offset_lower.value(), self.fit_time_offset_upper.value()],
        }
        n_values = {
            "D": self.d_n_values.value(),
            "temperature": self.temperature_n_values.value(),
            "concentration": self.concentration_n_values.value(),
            "solvent_sigma0": self.sigma0_n_values.value(),
            "time_offset": self.time_offset_n_values.value(),
        }
        fit = {
            "temperature": self.fit_temperature_check.isChecked(),
            "concentration": self.fit_concentration_check.isChecked(),
            "solvent_sigma0": self.fit_sigma0_check.isChecked(),
            "time_offset": self.fit_time_offset_check.isChecked(),
        }
        for name in self.fit_isotherm_value:
            key = {"a_mol_per_m3": "a_M", "gamma_inf_mol_per_m2": "gamma_inf_umol_per_m2"}.get(name, name)
            values[key] = self.fit_isotherm_value[name].value()
            bounds[key] = [self.fit_isotherm_lower[name].value(), self.fit_isotherm_upper[name].value()]
            n_values[name] = self.fit_isotherm_n[name].value()
            fit[name] = self.fit_isotherm_checks[name].isChecked()
        return {
            "base_solute": self._base_solute_name,
            "isotherm_name": self._current_isotherm_name(),
            "fit": fit,
            "bounds": bounds,
            "n_values": n_values,
            "values": values,
        }

    def _on_save_parameters(self) -> None:
        current = self.fitting_profile_combo.currentText()
        name = (
            current
            if current.startswith("Custom (")
            else self._next_custom_profile_name(self._base_solute_name)
        )
        suggested_path = self.profile_folder / f"{safe_profile_filename(name)}.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save fitting profile",
            str(suggested_path),
            "JSON profile (*.json)",
        )
        if path:
            selected_path = Path(path)
            self._save_parameter_set(selected_path.stem.strip() or name, selected_path)

    def _on_save_as_new(self) -> None:
        self._on_save_parameters()

    def _save_parameter_set(self, name: str, path: Path) -> None:
        if not name:
            QMessageBox.warning(self, "Name required", "Enter a name for the fitting profile.")
            return
        if name in BUILTIN_PROFILE_NAMES:
            QMessageBox.warning(self, "Built-in profile", "Built-in profiles cannot be overwritten.")
            return
        if name in self.fitting_profiles and name != self.fitting_profile_combo.currentText():
            QMessageBox.warning(self, "Name already saved", f"'{name}' already exists.")
            return
        if path.parent.resolve() != self.profile_folder.resolve():
            QMessageBox.warning(
                self,
                "Invalid profile location",
                f"Custom profiles must be saved in {self.profile_folder}.",
            )
            return
        try:
            profile = self._profile_from_controls()
            save_custom_fitting_profile(path, name, profile)
        except ParameterConfigError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self._reload_profiles(name)

    def _rename_profile(self) -> None:
        current = self.fitting_profile_combo.currentText()
        if not current or current in BUILTIN_PROFILE_NAMES:
            QMessageBox.warning(self, "Built-in profile", "Built-in profiles cannot be renamed.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Rename fitting profile",
            str(self.profile_folder / f"{safe_profile_filename(current)}.json"),
            "JSON profile (*.json)",
        )
        if not path:
            return
        if Path(path).parent.resolve() != self.profile_folder.resolve():
            QMessageBox.warning(
                self,
                "Invalid profile location",
                f"Custom profiles must be saved in {self.profile_folder}.",
            )
            return
        name = Path(path).stem.strip()
        if not name or name in self.fitting_profiles:
            QMessageBox.warning(self, "Name unavailable", "Choose a new, unused profile name.")
            return
        try:
            save_custom_fitting_profile(Path(path), name, self.fitting_profiles[current])
            old_path = self.profile_folder / f"{safe_profile_filename(current)}.json"
            if old_path != Path(path) and old_path.exists():
                old_path.unlink()
        except (OSError, ParameterConfigError) as exc:
            QMessageBox.critical(self, "Rename failed", str(exc))
            return
        self._reload_profiles(name)

    def _delete_custom_profiles(self) -> None:
        answer = QMessageBox.question(
            self, "Delete custom profiles",
            "Delete all custom fitting profiles? Built-in profiles will remain.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for path in self.profile_folder.glob("*.json"):
            try:
                path.unlink()
            except OSError as exc:
                QMessageBox.critical(self, "Delete failed", str(exc))
                return
        self._reload_profiles("Triton X-100")

    def _reload_profiles(self, selected: Optional[str] = None) -> None:
        current = selected or self.fitting_profile_combo.currentText()
        self.fitting_profiles = builtin_fitting_profiles()
        self.fitting_profiles.update(load_custom_fitting_profiles(self.profile_folder))
        self.parameter_sets = {n: p["values"] for n, p in self.fitting_profiles.items()}
        self._refresh_solute_choices(current if current in self.fitting_profiles else "Triton X-100")

    def _on_restore_defaults(self) -> None:
        custom_profiles = sorted(set(self.fitting_profiles) - set(BUILTIN_PROFILE_NAMES))
        lost_profiles = ", ".join(custom_profiles) if custom_profiles else "none"
        answer = QMessageBox.question(
            self,
            "Restore defaults",
            "This will delete all custom profile files and result in the loss of "
            f"{lost_profiles}. Consolidate any profiles that you wish to retain "
            "in the default configuration.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        for path in self.profile_folder.glob("*.json"):
            try:
                path.unlink()
            except OSError as exc:
                QMessageBox.critical(self, "Restore failed", str(exc))
                return
        self._reload_profiles("Triton X-100")

    def _build_conditions_group(self) -> QGroupBox:
        box = QGroupBox("3. Conditions and optional fit parameters")
        layout = QVBoxLayout(box)
        optional_form = QGridLayout()
        optional_form.addWidget(QLabel("Parameter"), 0, 0)
        optional_form.addWidget(QLabel("Fit"), 0, 1)
        optional_form.addWidget(QLabel("Lower bound"), 0, 2)
        optional_form.addWidget(QLabel("Upper bound"), 0, 3)
        optional_form.addWidget(QLabel("N values"), 0, 4)
        optional_form.addWidget(QLabel("Value"), 0, 5)

        self.d_lower_exp = _spin(-16.0, -4.0, 1, -13.0, step=0.1)
        self.d_upper_exp = _spin(-16.0, -4.0, 1, -7.0, step=0.1)
        self.d_n_values = QSpinBox()
        self.d_n_values.setRange(2, 1000)
        self.d_n_values.setValue(25)
        self.d_last_used = QLineEdit("1e-9")
        self.d_last_used.setReadOnly(True)
        optional_form.addWidget(QLabel("D (log10 bounds)"), 1, 0)
        optional_form.addWidget(QLabel("always"), 1, 1)
        optional_form.addWidget(self.d_lower_exp, 1, 2)
        optional_form.addWidget(self.d_upper_exp, 1, 3)
        optional_form.addWidget(self.d_n_values, 1, 4)
        optional_form.addWidget(self.d_last_used, 1, 5)

        self.fit_temperature_check = QCheckBox()
        self.temperature_lower = _spin(-20.0, 150.0, 2, 20.0, step=0.1, suffix="degC")
        self.temperature_upper = _spin(-20.0, 150.0, 2, 26.0, step=0.1, suffix="degC")
        self.temperature_n_values = QSpinBox()
        self.temperature_n_values.setRange(2, 1000)
        self.temperature_n_values.setValue(9)
        self.temperature_last_used = QLineEdit("23.0")
        self.temperature_last_used.setPlaceholderText("degC")
        optional_form.addWidget(QLabel("Temperature (degC)"), 2, 0)
        optional_form.addWidget(self.fit_temperature_check, 2, 1)
        optional_form.addWidget(self.temperature_lower, 2, 2)
        optional_form.addWidget(self.temperature_upper, 2, 3)
        optional_form.addWidget(self.temperature_n_values, 2, 4)
        optional_form.addWidget(self.temperature_last_used, 2, 5)

        self.fit_concentration_check = QCheckBox("Fit concentration")
        self.fit_concentration_check.setToolTip(
            "Use only when the entered value is a nominal total concentration; "
            "the teaching range is restricted to 0.2-2.0 mM."
        )
        self.fit_concentration_lower = _spin(0.2, 2.0, 4, 0.2, step=0.1, suffix="mM")
        self.fit_concentration_upper = _spin(0.2, 2.0, 4, 2.0, step=0.1, suffix="mM")
        self.concentration_n_values = QSpinBox()
        self.concentration_n_values.setRange(2, 1000)
        self.concentration_n_values.setValue(9)
        self.fit_concentration_check.setText("")
        self.concentration_last_used = QLineEdit("1.0")
        optional_form.addWidget(QLabel("Concentration (mM)"), 3, 0)
        optional_form.addWidget(self.fit_concentration_check, 3, 1)
        optional_form.addWidget(self.fit_concentration_lower, 3, 2)
        optional_form.addWidget(self.fit_concentration_upper, 3, 3)
        optional_form.addWidget(self.concentration_n_values, 3, 4)
        optional_form.addWidget(self.concentration_last_used, 3, 5)

        self.fit_sigma0_check = QCheckBox("Fit solvent sigma0")
        self.fit_sigma0_lower = _spin(65.0, 80.0, 4, 70.0, step=0.1, suffix="mN/m")
        self.fit_sigma0_upper = _spin(65.0, 80.0, 4, 75.0, step=0.1, suffix="mN/m")
        self.sigma0_n_values = QSpinBox()
        self.sigma0_n_values.setRange(2, 1000)
        self.sigma0_n_values.setValue(9)
        self.fit_sigma0_check.setText("")
        self.sigma0_last_used = QLineEdit("72.5")
        optional_form.addWidget(QLabel("Solvent sigma0 (mN/m)"), 4, 0)
        optional_form.addWidget(self.fit_sigma0_check, 4, 1)
        optional_form.addWidget(self.fit_sigma0_lower, 4, 2)
        optional_form.addWidget(self.fit_sigma0_upper, 4, 3)
        optional_form.addWidget(self.sigma0_n_values, 4, 4)
        optional_form.addWidget(self.sigma0_last_used, 4, 5)

        self.fit_time_offset_check = QCheckBox("Fit time offset")
        self.fit_time_offset_value = _spin(-10.0, 10.0, 4, 0.0, step=0.1, suffix="s")
        self.fit_time_offset_lower = _spin(-10.0, 10.0, 4, -2.0, step=0.1, suffix="s")
        self.fit_time_offset_upper = _spin(-10.0, 10.0, 4, 2.0, step=0.1, suffix="s")
        self.time_offset_n_values = QSpinBox()
        self.time_offset_n_values.setRange(2, 1000)
        self.time_offset_n_values.setValue(9)
        self.fit_time_offset_check.setText("")
        self.time_offset_last_used = QLineEdit("0.0")
        optional_form.addWidget(QLabel("Time offset (s)"), 5, 0)
        optional_form.addWidget(self.fit_time_offset_check, 5, 1)
        optional_form.addWidget(self.fit_time_offset_lower, 5, 2)
        optional_form.addWidget(self.fit_time_offset_upper, 5, 3)
        optional_form.addWidget(self.time_offset_n_values, 5, 4)
        optional_form.addWidget(self.time_offset_last_used, 5, 5)
        optional_form.addWidget(
            QLabel("D is always profiled; checked rows use bounds, unchecked rows use Value."),
            6, 0, 1, 6,
        )
        self.fit_temperature_check.toggled.connect(self._update_fit_parameter_controls)
        self.fit_concentration_check.toggled.connect(self._update_fit_parameter_controls)
        self.fit_sigma0_check.toggled.connect(self._update_fit_parameter_controls)
        self.fit_time_offset_check.toggled.connect(self._update_fit_parameter_controls)
        self._update_fit_parameter_controls()
        layout.addLayout(optional_form)
        return box

    def _update_fit_parameter_controls(self) -> None:
        controls = (
            (self.fit_temperature_check, self.temperature_lower, self.temperature_upper, self.temperature_n_values, self.temperature_last_used),
            (self.fit_concentration_check, self.fit_concentration_lower, self.fit_concentration_upper, self.concentration_n_values, self.concentration_last_used),
            (self.fit_sigma0_check, self.fit_sigma0_lower, self.fit_sigma0_upper, self.sigma0_n_values, self.sigma0_last_used),
            (self.fit_time_offset_check, self.fit_time_offset_lower, self.fit_time_offset_upper, self.time_offset_n_values, self.time_offset_last_used),
        )
        for checkbox, lower, upper, n_values, last_used in controls:
            enabled = checkbox.isChecked()
            lower.setEnabled(enabled)
            upper.setEnabled(enabled)
            n_values.setEnabled(enabled)
            last_used.setReadOnly(enabled)
            last_used.setEnabled(True)
        for name, checkbox in self.fit_isotherm_checks.items():
            enabled = checkbox.isChecked()
            self.fit_isotherm_lower[name].setEnabled(enabled)
            self.fit_isotherm_upper[name].setEnabled(enabled)
            self.fit_isotherm_n[name].setEnabled(enabled)
            self.fit_isotherm_value[name].setReadOnly(enabled)
            self.fit_isotherm_value[name].setEnabled(True)
        self.d_n_values.setEnabled(True)
        self._update_permutation_count()

    def _update_permutation_count(self) -> None:
        if not hasattr(self, "permutation_count_label"):
            return
        optional_counts = [
            self.temperature_n_values.value()
            for checkbox in (self.fit_temperature_check,)
            if checkbox.isChecked()
        ]
        optional_counts += [
            self.concentration_n_values.value()
            for checkbox in (self.fit_concentration_check,)
            if checkbox.isChecked()
        ]
        optional_counts += [
            self.sigma0_n_values.value()
            for checkbox in (self.fit_sigma0_check,)
            if checkbox.isChecked()
        ]
        optional_counts += [
            self.time_offset_n_values.value()
            for checkbox in (self.fit_time_offset_check,)
            if checkbox.isChecked()
        ]
        optional_counts += [
            self.fit_isotherm_n[name].value()
            for name, checkbox in self.fit_isotherm_checks.items()
            if checkbox.isChecked()
        ]
        outer_permutations = 1 + sum(3 * count + 2 for count in optional_counts)
        d_evaluations = outer_permutations * self.d_n_values.value()
        self.permutation_count_label.setText(
            f"Fit permutations: {outer_permutations} "
            f"(D evaluations: {d_evaluations})"
        )

    def _build_actions_group(self) -> QGroupBox:
        box = QGroupBox("3. Run & export")
        layout = QVBoxLayout(box)

        plot_form = QFormLayout()
        self.plot_title_value = QLineEdit()
        self.plot_title_value.setPlaceholderText("Optional plot title")
        self.experimental_legend_value = QLineEdit("Experimental")
        self.model_legend_value = QLineEdit("Ward-Tordai")
        plot_form.addRow("Plot title:", self.plot_title_value)
        plot_form.addRow("Experimental points:", self.experimental_legend_value)
        plot_form.addRow("Ward-Tordai line:", self.model_legend_value)
        layout.addLayout(plot_form)
        self.plot_title_value.textChanged.connect(self._on_plot_labels_changed)
        self.experimental_legend_value.textChanged.connect(self._on_plot_labels_changed)
        self.model_legend_value.textChanged.connect(self._on_plot_labels_changed)

        run_row = QHBoxLayout()
        fit_btn = QPushButton("Fit D / selected parameters")
        fit_btn.clicked.connect(self._on_fit)
        run_row.addWidget(fit_btn)
        layout.addLayout(run_row)
        self.fit_progress = QProgressBar()
        self.fit_progress.setRange(0, 1)
        self.fit_progress.setValue(0)
        self.fit_progress.setFormat("Fit progress")
        layout.addWidget(self.fit_progress)

        export_row = QHBoxLayout()
        export_summary_btn = QPushButton("Export fit summary...")
        export_summary_btn.clicked.connect(self._on_export_fit_summary)
        export_png_btn = QPushButton("Export plot PNG...")
        export_png_btn.clicked.connect(self._on_export_png)
        self.simulation_point_count = QSpinBox()
        self.simulation_point_count.setRange(2, 100000)
        self.simulation_point_count.setValue(100)
        export_row.addWidget(QLabel("Simulation points:"))
        export_row.addWidget(self.simulation_point_count)
        export_row.addWidget(export_summary_btn)
        export_row.addWidget(export_png_btn)
        layout.addLayout(export_row)
        return box

    # ------------------------------------------------------------------
    # UI event handlers (gather state, delegate to pure functions)
    # ------------------------------------------------------------------
    def _on_isotherm_changed(self, display_name: str) -> None:
        if not hasattr(self, "_isotherm_rows"):
            return
        name = {v: k for k, v in ISOTHERM_DISPLAY_NAMES.items()}[display_name]
        visible = {
            "a_mol_per_m3": True,
            "gamma_inf_mol_per_m2": name != "henry",
            "k": name in ("frumkin", "generalized_frumkin"),
            "p": name == "generalized_frumkin",
        }
        for parameter, widgets in self._isotherm_rows.items():
            for widget in widgets:
                widget.setVisible(visible[parameter])
        self._update_fit_parameter_controls()

    def _current_isotherm_name(self) -> str:
        return {v: k for k, v in ISOTHERM_DISPLAY_NAMES.items()}[self.isotherm_combo.currentText()]

    def _build_isotherm_params(self) -> dict:
        name = self._current_isotherm_name()
        a_mol_per_m3 = self.fit_isotherm_value["a_mol_per_m3"].value() * 1000.0
        gamma_inf_mol_per_m2 = self.fit_isotherm_value["gamma_inf_mol_per_m2"].value() * 1e-6
        if name == "henry":
            return {"a_mol_per_m3": a_mol_per_m3, "gamma_inf_mol_per_m2": gamma_inf_mol_per_m2}
        if name == "langmuir":
            return {"a_mol_per_m3": a_mol_per_m3, "gamma_inf_mol_per_m2": gamma_inf_mol_per_m2}
        if name == "frumkin":
            return {
                "a_mol_per_m3": a_mol_per_m3,
                "gamma_inf_mol_per_m2": gamma_inf_mol_per_m2,
                "k": self.fit_isotherm_value["k"].value(),
            }
        if name == "generalized_frumkin":
            return {
                "a_mol_per_m3": a_mol_per_m3,
                "gamma_inf_mol_per_m2": gamma_inf_mol_per_m2,
                "k": self.fit_isotherm_value["k"].value(),
                "p": self.fit_isotherm_value["p"].value(),
            }
        raise IsothermError(f"Unknown isotherm: {name}")

    def _build_settings(self) -> FitSettings:
        return FitSettings(
            isotherm_name=self._current_isotherm_name(),
            isotherm_params=self._build_isotherm_params(),
            bulk_concentration_mol_per_m3=self._read_last_used(
                self.concentration_last_used, "concentration"
            ),
            temperature_K=celsius_to_kelvin(
                self._read_last_used(self.temperature_last_used, "temperature")
            ),
            solvent_sigma0_N_per_m=tension_to_N_per_m(
                self._read_last_used(self.sigma0_last_used, "solvent sigma0"),
                TensionUnit.MILLINEWTON_PER_METER,
            ),
            diffusion_coefficient_m2_per_s=self._read_last_used(self.d_last_used, "D"),
        )

    def _on_load_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load CSV", "", "CSV files (*.csv)")
        if not path:
            return
        self._load_csv_path(Path(path))

    def _load_csv_path(self, path: Path) -> None:
        try:
            self.data = load_csv(
                str(path),
                time_unit=TimeUnit(self.time_unit_combo.currentText()),
                tension_unit=TensionUnit(self.tension_unit_combo.currentText()),
            )
        except DataLoadError as exc:
            QMessageBox.critical(self, "Data load failed", str(exc))
            return
        self.data_status_label.setText(f"Loaded {len(self.data)} points from {path}")
        self._redraw_plot()

    def _on_use_example_data(self) -> None:
        candidates = (
            Path.cwd() / "experimental_data.csv",
            Path.cwd() / "examples" / "sample_data.csv",
            Path(__file__).resolve().parents[2] / "experimental_data.csv",
        )
        example_path = next((path for path in candidates if path.is_file()), None)
        if example_path is None:
            QMessageBox.warning(
                self,
                "Example data unavailable",
                "Could not find experimental_data.csv or examples/sample_data.csv.",
            )
            return
        self.time_unit_combo.setCurrentText(TimeUnit.SECONDS.value)
        self.tension_unit_combo.setCurrentText(TensionUnit.MILLINEWTON_PER_METER.value)
        self._load_csv_path(example_path)
        if "Triton X-100" in self.fitting_profiles:
            self.fitting_profile_combo.setCurrentText("Triton X-100")

    def _on_use_pasted(self) -> None:
        text = self.paste_edit.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "No data", "Paste two columns of data first.")
            return
        try:
            self.data = parse_text_columns(
                text,
                time_unit=TimeUnit(self.time_unit_combo.currentText()),
                tension_unit=TensionUnit(self.tension_unit_combo.currentText()),
            )
        except DataLoadError as exc:
            QMessageBox.critical(self, "Data parse failed", str(exc))
            return
        self.data_status_label.setText(f"Loaded {len(self.data)} points from pasted text")
        self._redraw_plot()

    def _require_data(self) -> Optional[ExperimentalData]:
        if self.data is None or len(self.data) == 0:
            QMessageBox.warning(self, "No data", "Load or paste experimental data first.")
            return None
        return self.data

    def _simulation_grid_data(self, data: ExperimentalData) -> ExperimentalData:
        count = self.simulation_point_count.value()
        if data.time_s[0] == data.time_s[-1]:
            times = np.full(count, data.time_s[0], dtype=float)
        else:
            times = np.geomspace(data.time_s[0], data.time_s[-1], count)
        return ExperimentalData(times, np.zeros(count, dtype=float))

    def _on_simulate(self) -> None:
        data = self._require_data()
        if data is None:
            return
        try:
            settings = self._build_settings()
            result = simulate(settings, self._simulation_grid_data(data))
        except (IsothermError, ValueError) as exc:
            QMessageBox.critical(self, "Simulation failed", str(exc))
            return
        self.last_fit = None
        self._last_simulation = result
        self._redraw_plot(result)
        if result.converged:
            self._log(self._format_simulation_text(settings, result))
        else:
            self._log(f"=== Simulate ===\nSimulation failed to converge: {result.message}")

    def _update_fit_progress(self, completed: int, total: int) -> None:
        self.fit_progress.setRange(0, max(total, 1))
        self.fit_progress.setValue(completed)
        self.fit_progress.setFormat(f"Fit progress: {completed}/{total}")
        QApplication.processEvents()

    def _on_fit(self) -> None:
        data = self._require_data()
        if data is None:
            return
        try:
            settings = self._build_settings()
            if not self.fit_temperature_check.isChecked():
                settings = dataclasses.replace(
                    settings,
                    temperature_K=celsius_to_kelvin(self._read_last_used(self.temperature_last_used, "temperature")),
                )
            if not self.fit_concentration_check.isChecked():
                settings = dataclasses.replace(
                    settings,
                    bulk_concentration_mol_per_m3=self._read_last_used(
                        self.concentration_last_used, "concentration"
                    ),
                )
            if not self.fit_sigma0_check.isChecked():
                settings = dataclasses.replace(
                    settings,
                    solvent_sigma0_N_per_m=tension_to_N_per_m(
                        self._read_last_used(self.sigma0_last_used, "solvent sigma0"),
                        TensionUnit.MILLINEWTON_PER_METER,
                    ),
                )
            fixed_time_offset = (
                self._read_last_used(self.time_offset_last_used, "time offset")
                if not self.fit_time_offset_check.isChecked()
                else 0.0
            )
            bounds = (self.d_lower_exp.value(), self.d_upper_exp.value())
            isotherm_bounds = {}
            isotherm_counts = {}
            for name, checkbox in self.fit_isotherm_checks.items():
                if not checkbox.isChecked():
                    continue
                scale = 1.0
                if name == "a_mol_per_m3":
                    scale = 1000.0
                elif name == "gamma_inf_mol_per_m2":
                    scale = 1e-6
                isotherm_bounds[name] = (
                    self.fit_isotherm_lower[name].value() * scale,
                    self.fit_isotherm_upper[name].value() * scale,
                )
                isotherm_counts[name] = self.fit_isotherm_n[name].value()
            fit_result = fit_profiled_parameters(
                settings,
                data,
                fit_concentration=self.fit_concentration_check.isChecked(),
                concentration_bounds_mol_per_m3=(
                    self.fit_concentration_lower.value(),
                    self.fit_concentration_upper.value(),
                ),
                fit_solvent_sigma0=self.fit_sigma0_check.isChecked(),
                solvent_sigma0_bounds_N_per_m=(
                    self.fit_sigma0_lower.value() / 1000.0,
                    self.fit_sigma0_upper.value() / 1000.0,
                ),
                fit_temperature=self.fit_temperature_check.isChecked(),
                temperature_bounds_K=(
                    celsius_to_kelvin(self.temperature_lower.value()),
                    celsius_to_kelvin(self.temperature_upper.value()),
                ),
                fixed_temperature_K=settings.temperature_K,
                fit_time_offset=self.fit_time_offset_check.isChecked(),
                time_offset_bounds_s=(
                    self.fit_time_offset_lower.value(),
                    self.fit_time_offset_upper.value(),
                ),
                initial_time_offset_s=fixed_time_offset,
                fit_isotherm_params=isotherm_bounds,
                d_n_values=self.d_n_values.value(),
                n_values={
                    "bulk_concentration_mol_per_m3": self.concentration_n_values.value(),
                    "solvent_sigma0_N_per_m": self.sigma0_n_values.value(),
                    "temperature_K": self.temperature_n_values.value(),
                    "time_offset_s": self.time_offset_n_values.value(),
                    **isotherm_counts,
                },
                progress_callback=self._update_fit_progress,
                log10_D_bounds=bounds,
            )
        except (IsothermError, ValueError) as exc:
            self.fit_progress.setFormat("Fit failed")
            QMessageBox.critical(self, "Fit failed", str(exc))
            return
        self.last_fit = fit_result
        display_simulation = fit_result.simulation
        if fit_result.success:
            display_settings = fit_result.optimized_settings or settings
            display_simulation = simulate(
                display_settings, self._simulation_grid_data(data)
            )
        self._last_simulation = display_simulation
        self._redraw_plot(display_simulation)
        if fit_result.success:
            # Reflect the fitted D back into the input field so the user
            # can see/reuse it, and immediately re-simulate with it so the
            # displayed "D used" matches the field.
            fitted = fit_result.fitted_parameters
            self.d_last_used.setText(f"{fit_result.fitted_D_m2_per_s:.6g}")
            self.temperature_last_used.setText(
                f"{fitted['temperature_K'] - 273.15:.6g}"
            )
            self.concentration_last_used.setText(
                f"{fitted['bulk_concentration_mol_per_m3']:.6g}"
            )
            self.sigma0_last_used.setText(
                f"{fitted['solvent_sigma0_N_per_m'] * 1000.0:.6g}"
            )
            self.time_offset_last_used.setText(f"{fitted['time_offset_s']:.6g}")
            for name in self.fit_isotherm_checks:
                if name not in fitted:
                    continue
                value = fitted[name]
                if name == "a_mol_per_m3":
                    value /= 1000.0
                elif name == "gamma_inf_mol_per_m2":
                    value /= 1e-6
                self.fit_isotherm_value[name].setValue(value)
        self._log(self._format_fit_text(settings, fit_result))

    @staticmethod
    def _read_last_used(field: QLineEdit, name: str) -> float:
        try:
            value = float(field.text().strip())
        except ValueError as exc:
            raise ValueError(f"Enter a numeric Last used value for {name}.") from exc
        if not value == value or value in (float("inf"), float("-inf")):
            raise ValueError(f"Last used value for {name} must be finite.")
        return value

    def _format_simulation_text(self, settings: FitSettings, result) -> str:
        lines = [
            "=== Simulate ===",
            f"Isotherm: {ISOTHERM_DISPLAY_NAMES[settings.isotherm_name]}  "
            f"params: {settings.isotherm_params}",
            f"D used: {settings.diffusion_coefficient_m2_per_s:.4e} m^2/s",
            f"n observations: {len(self.data)}",
        ]
        if result.equilibrium_gamma_mol_per_m2 is not None:
            lines.append(
                f"Equilibrium Gamma: {result.equilibrium_gamma_mol_per_m2:.4e} mol/m^2, "
                f"Equilibrium sigma: {result.equilibrium_sigma_N_per_m*1000:.3f} mN/m"
            )
        return "\n".join(lines)

    def _format_fit_text(self, settings: FitSettings, fit_result) -> str:
        if not fit_result.success:
            return f"=== Fit D ===\nFit failed: {fit_result.message}"
        lines = [
            "=== Fit D ===",
            f"Isotherm: {ISOTHERM_DISPLAY_NAMES[settings.isotherm_name]}  "
            f"params: {settings.isotherm_params}",
            f"Fitted apparent D: {fit_result.fitted_D_m2_per_s:.4e} m^2/s  "
            f"(D field updated to this value)",
            f"Fit quality: RMSE = {fit_result.rmse_N_per_m*1000:.4f} mN/m, "
            f"R^2 = {fit_result.r_squared:.5f}",
            f"n observations: {fit_result.n_observations}",
        ]
        if fit_result.time_offset_s:
            lines.append(f"Time offset applied: {fit_result.time_offset_s:.4g} s")
        for name, value in fit_result.fitted_parameters.items():
            if name == "bulk_concentration_mol_per_m3":
                lines.append(f"Fitted concentration: {value:.4g} mol/m^3")
            elif name == "solvent_sigma0_N_per_m":
                lines.append(f"Fitted solvent sigma0: {value * 1000:.4g} mN/m")
            elif name == "temperature_K":
                lines.append(f"Fitted temperature: {value - 273.15:.4g} degC")
            elif name == "a_mol_per_m3":
                lines.append(f"Fitted a: {value / 1000.0:.4g} M")
            elif name == "gamma_inf_mol_per_m2":
                lines.append(f"Fitted Gamma_inf: {value * 1e6:.4g} umol/m^2")
            elif name in ("k", "p"):
                lines.append(f"Fitted {name}: {value:.4g}")
        if fit_result.parameter_profile_rmse_span_N_per_m:
            lines.append("Profile RMSE change near optimum:")
            for name, span in fit_result.parameter_profile_rmse_span_N_per_m.items():
                lines.append(f"  {name}: +/-10% range changes RMSE by {span * 1000:.4g} mN/m")
        sim = fit_result.simulation
        if sim is not None and sim.equilibrium_gamma_mol_per_m2 is not None:
            lines.append(
                f"Equilibrium Gamma: {sim.equilibrium_gamma_mol_per_m2:.4e} mol/m^2, "
                f"Equilibrium sigma: {sim.equilibrium_sigma_N_per_m*1000:.3f} mN/m"
            )
        lines.append(
            "Note: D is an 'apparent' diffusion coefficient under the selected "
            "isotherm model, not a directly measured molecular diffusivity."
        )
        return "\n".join(lines)

    def _log(self, text: str) -> None:
        """Append an entry to the results/log panel (never overwrites history)."""
        if self.results_box.toPlainText():
            self.results_box.appendPlainText("")
        self.results_box.appendPlainText(text)
        self.results_box.verticalScrollBar().setValue(
            self.results_box.verticalScrollBar().maximum()
        )

    def _on_plot_labels_changed(self, _text: str) -> None:
        self._redraw_plot(getattr(self, "_last_simulation", None))

    def _redraw_plot(self, simulation=None) -> None:
        title = self.plot_title_value.text() if hasattr(self, "plot_title_value") else ""
        experimental_label = (
            self.experimental_legend_value.text()
            if hasattr(self, "experimental_legend_value")
            else "Experimental"
        )
        model_label = (
            self.model_legend_value.text()
            if hasattr(self, "model_legend_value")
            else "Ward-Tordai"
        )
        if self.data is not None:
            new_fig = plot_sigma_vs_time(
                self.data,
                simulation,
                title=title,
                experimental_label=experimental_label,
                model_label=model_label,
            )
        else:
            new_fig = Figure(figsize=(6, 5), dpi=100)
            new_fig.patch.set_facecolor("white")
            ax = new_fig.add_subplot(111)
            ax.set_facecolor("white")
            ax.set_title(title or "Load experimental data to begin")
        self.figure = new_fig
        self.canvas.figure = new_fig
        self.canvas.draw_idle()

    def _on_export_fit_summary(self) -> None:
        if self.last_fit is None or self.data is None:
            QMessageBox.warning(self, "Nothing to export", "Run Fit D first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export fit summary",
            "fit_summary.xlsx",
            "Excel Workbook (*.xlsx)",
        )
        if not path:
            return
        try:
            export_fit_summary_workbook(
                path,
                self.data,
                self.last_fit,
                self._build_settings(),
                self.simulation_point_count.value(),
            )
        except (OSError, ValueError, ImportError) as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _on_export_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export plot", "plot.png", "PNG (*.png)")
        if not path:
            return
        try:
            save_figure_png(self.figure, path)
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))


def run() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
