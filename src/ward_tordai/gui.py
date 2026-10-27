"""PySide6 GUI: presentation and orchestration only.

No mathematical expressions or optimizer calls live in button callbacks;
they only gather UI state into dataclasses and delegate to
``solver``/``fitting``/``io``/``plotting``.
"""
from __future__ import annotations

import dataclasses
import sys
from typing import Optional

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
    DEFAULT_CONFIG_PATH,
    ParameterConfigError,
    ensure_live_config,
    load_parameter_sets,
    restore_default_config,
    save_parameter_set,
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
        self.parameter_sets = ensure_live_config()

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
        btn_row.addWidget(load_csv_btn)
        btn_row.addWidget(use_pasted_btn)
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
        return box

    def _build_solution_group(self) -> QGroupBox:
        box = QGroupBox("2. Fitting parameters for a given Isotherm and Solute")
        layout = QVBoxLayout(box)

        selectors = QHBoxLayout()
        self.solute_combo = QComboBox()
        self.solute_combo.addItem("Custom")
        self.solute_combo.addItems(sorted(self.parameter_sets))
        self.solute_combo.currentTextChanged.connect(self._on_solute_changed)
        selectors.addLayout(self._labeled_control("Solute:", self.solute_combo))
        self.isotherm_combo = QComboBox()
        self.isotherm_combo.addItems(list(ISOTHERM_DISPLAY_NAMES.values()))
        self.isotherm_combo.currentTextChanged.connect(self._on_isotherm_changed)
        selectors.addLayout(self._labeled_control("Isotherm:", self.isotherm_combo))
        layout.addLayout(selectors)

        self.sigma0_value = _spin(1.0, 200.0, 3, 72.5, step=0.1, suffix="mN/m")
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

        self._isotherm_table = table
        self._isotherm_rows: dict[str, list[QWidget]] = {}
        for row, (name, label, low, high, n, value) in enumerate(
            (
                ("a_mol_per_m3", "a (M)", 1e-3, 1.0, 9, 6.62e-3),
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
        self.solute_combo.blockSignals(True)
        self.solute_combo.clear()
        self.solute_combo.addItem("Custom")
        self.solute_combo.addItems(sorted(self.parameter_sets))
        if selected:
            self.solute_combo.setCurrentText(selected)
        self.solute_combo.blockSignals(False)

    def _current_parameter_values(self) -> dict[str, float]:
        return {
            "a_M": self.fit_isotherm_value["a_mol_per_m3"].value() / 1000.0,
            "gamma_inf_umol_per_m2": self.fit_isotherm_value[
                "gamma_inf_mol_per_m2"
            ].value(),
            "k": self.fit_isotherm_value["k"].value(),
            "p": self.fit_isotherm_value["p"].value(),
        }

    def _on_solute_changed(self, name: str) -> None:
        if name not in self.parameter_sets or not hasattr(self, "fit_isotherm_value"):
            return
        params = self.parameter_sets[name]
        self.fit_isotherm_value["a_mol_per_m3"].setValue(params["a_M"] * 1000.0)
        self.fit_isotherm_value["gamma_inf_mol_per_m2"].setValue(
            params["gamma_inf_umol_per_m2"]
        )
        self.fit_isotherm_value["k"].setValue(params["k"])
        self.fit_isotherm_value["p"].setValue(params["p"])

        preset = SURFACTANT_PRESETS.get(name)
        if preset is not None:
            self.isotherm_combo.setCurrentText(ISOTHERM_DISPLAY_NAMES["langmuir"])
            if preset.suggested_bulk_conc_M is not None:
                self.concentration_last_used.setText(
                    f"{preset.suggested_bulk_conc_M * 1000.0:.6g}"
                )
            if preset.suggested_D_m2_per_s is not None:
                if hasattr(self, "d_last_used"):
                    self.d_last_used.setText(f"{preset.suggested_D_m2_per_s:.6g}")
            if preset.suggested_temperature_C is not None:
                if hasattr(self, "temperature_last_used"):
                    self.temperature_last_used.setText(f"{preset.suggested_temperature_C:.6g}")
            if preset.suggested_sigma0_mN_per_m is not None:
                if hasattr(self, "sigma0_last_used"):
                    self.sigma0_last_used.setText(f"{preset.suggested_sigma0_mN_per_m:.6g}")
            if preset.suggested_bulk_conc_M is not None and hasattr(self, "concentration_last_used"):
                self.concentration_last_used.setText(f"{preset.suggested_bulk_conc_M * 1000.0:.6g}")

    def _on_save_parameters(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Save parameter set")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Select a saved solute to overwrite, or save as new:"))
        solute_list = QListWidget()
        solute_list.addItems(sorted(self.parameter_sets))
        if solute_list.count():
            solute_list.setCurrentRow(0)
        layout.addWidget(solute_list)

        buttons = QHBoxLayout()
        save_selected_btn = QPushButton("Save")
        save_new_btn = QPushButton("Save as new")
        cancel_btn = QPushButton("Cancel")
        save_selected_btn.setEnabled(solute_list.count() > 0)
        buttons.addWidget(save_selected_btn)
        buttons.addWidget(save_new_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)
        save_selected_btn.clicked.connect(dialog.accept)
        save_new_btn.clicked.connect(lambda: dialog.done(2))
        cancel_btn.clicked.connect(dialog.reject)

        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted and solute_list.currentItem():
            name = solute_list.currentItem().text()
            answer = QMessageBox.question(
                self,
                "Confirm overwrite",
                f"This will overwrite the existing save for {name}, are you sure?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._save_parameter_set(name)
        elif result == 2:
            self._on_save_as_new()

    def _on_save_as_new(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Save as new parameter set")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Name:"))
        name_field = QLineEdit()
        layout.addWidget(name_field)
        buttons = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)
        save_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = name_field.text().strip()
        if not name:
            QMessageBox.warning(self, "Name required", "Enter a name for the parameter set.")
            return
        if name in self.parameter_sets:
            QMessageBox.warning(
                self, "Name already saved", f"'{name}' already exists. Select it to overwrite."
            )
            return
        self._save_parameter_set(name)

    def _save_parameter_set(self, name: str) -> None:
        try:
            self.parameter_sets = save_parameter_set(
                name, self._current_parameter_values()
            )
        except ParameterConfigError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self._refresh_solute_choices(name)

    def _on_restore_defaults(self) -> None:
        try:
            default_sets = load_parameter_sets(DEFAULT_CONFIG_PATH)
        except ParameterConfigError as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
            return
        missing_solutes = sorted(set(self.parameter_sets) - set(default_sets))
        lost_solutes = ", ".join(missing_solutes) if missing_solutes else "none"
        answer = QMessageBox.question(
            self,
            "Restore defaults",
            "This will overwrite all current saved parameters in the live config file, "
            "and will result in the loss of "
            f"{lost_solutes}. Consolidate any parameter sets that you wish to retain "
            "in the default configuration.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        try:
            self.parameter_sets = restore_default_config()
        except ParameterConfigError as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
            return
        self._refresh_solute_choices(next(iter(self.parameter_sets), "Custom"))
        self._on_solute_changed(self.solute_combo.currentText())

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

    def _build_actions_group(self) -> QGroupBox:
        box = QGroupBox("4. Run & export")
        layout = QVBoxLayout(box)

        plot_form = QFormLayout()
        self.plot_title_value = QLineEdit()
        self.plot_title_value.setPlaceholderText("Optional plot title")
        self.experimental_legend_value = QLineEdit("Experimental")
        self.model_legend_value = QLineEdit("Ward-Tordai")
        plot_form.addRow("Plot title:", self.plot_title_value)
        plot_form.addRow("Legend text for experimental data:", self.experimental_legend_value)
        plot_form.addRow("Legend text for Ward-Tordai fit:", self.model_legend_value)
        layout.addLayout(plot_form)
        self.plot_title_value.textChanged.connect(self._on_plot_labels_changed)
        self.experimental_legend_value.textChanged.connect(self._on_plot_labels_changed)
        self.model_legend_value.textChanged.connect(self._on_plot_labels_changed)

        run_row = QHBoxLayout()
        simulate_btn = QPushButton("Simulate")
        simulate_btn.clicked.connect(self._on_simulate)
        fit_btn = QPushButton("Fit D / selected parameters")
        fit_btn.clicked.connect(self._on_fit)
        run_row.addWidget(simulate_btn)
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
        a_mol_per_m3 = self.fit_isotherm_value["a_mol_per_m3"].value()
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
        try:
            self.data = load_csv(
                path,
                time_unit=TimeUnit(self.time_unit_combo.currentText()),
                tension_unit=TensionUnit(self.tension_unit_combo.currentText()),
            )
        except DataLoadError as exc:
            QMessageBox.critical(self, "Data load failed", str(exc))
            return
        self.data_status_label.setText(f"Loaded {len(self.data)} points from {path}")
        self._redraw_plot()

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

    def _on_simulate(self) -> None:
        data = self._require_data()
        if data is None:
            return
        try:
            settings = self._build_settings()
            result = simulate(settings, data)
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
        self._last_simulation = fit_result.simulation
        self._redraw_plot(fit_result.simulation)
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
