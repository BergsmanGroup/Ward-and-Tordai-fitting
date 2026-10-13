"""PySide6 GUI: presentation and orchestration only.

No mathematical expressions or optimizer calls live in button callbacks;
they only gather UI state into dataclasses and delegate to
``solver``/``fitting``/``io``/``plotting``.
"""
from __future__ import annotations

import sys
from typing import Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .fitting import fit_diffusivity, simulate
from .io import DataLoadError, export_fit_summary_csv, export_predictions_csv, load_csv, parse_text_columns
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


def _spin(minimum, maximum, decimals, value, step=None, suffix=""):
    box = QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(decimals)
    box.setValue(value)
    if step is not None:
        box.setSingleStep(step)
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

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self._build_data_group())
        left_layout.addWidget(self._build_surfactant_group())
        left_layout.addWidget(self._build_isotherm_group())
        left_layout.addWidget(self._build_conditions_group())
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
        splitter.setSizes([430, 720])

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

    def _build_surfactant_group(self) -> QGroupBox:
        box = QGroupBox("2. Surfactant & bulk concentration")
        form = QFormLayout(box)

        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Custom")
        self.preset_combo.addItems(list(SURFACTANT_PRESETS))
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        form.addRow("Preset:", self.preset_combo)

        self.conc_value = _spin(1e-12, 1e6, 8, 1.0)
        self.conc_unit_combo = QComboBox()
        self.conc_unit_combo.addItems([u.value for u in ConcentrationUnit])
        conc_row = QHBoxLayout()
        conc_row.addWidget(self.conc_value)
        conc_row.addWidget(self.conc_unit_combo)
        form.addRow("Bulk concentration:", conc_row)
        return box

    def _build_isotherm_group(self) -> QGroupBox:
        box = QGroupBox("3. Adsorption isotherm")
        layout = QVBoxLayout(box)

        self.isotherm_combo = QComboBox()
        self.isotherm_combo.addItems(list(ISOTHERM_DISPLAY_NAMES.values()))
        self.isotherm_combo.currentTextChanged.connect(self._on_isotherm_changed)
        layout.addWidget(self.isotherm_combo)

        form = QFormLayout()
        self.a_value = _spin(1e-15, 1e6, 10, 6.62e-7)
        form.addRow("a (characteristic conc., M):", self.a_value)

        self.gamma_inf_value = _spin(1e-6, 1e6, 6, 2.91)
        form.addRow("Gamma_inf (umol/m^2):", self.gamma_inf_value)

        self.k_value = _spin(-100.0, 100.0, 6, 0.0)
        self.k_label = QLabel("k (interaction parameter):")
        form.addRow(self.k_label, self.k_value)

        self.p_value = _spin(1e-6, 100.0, 6, 1.0)
        self.p_label = QLabel("p (generalized exponent):")
        form.addRow(self.p_label, self.p_value)

        layout.addLayout(form)
        self._isotherm_form = form
        self._on_isotherm_changed(self.isotherm_combo.currentText())
        return box

    def _build_conditions_group(self) -> QGroupBox:
        box = QGroupBox("4. Solvent, temperature, and diffusivity")
        form = QFormLayout(box)

        self.sigma0_value = _spin(1.0, 200.0, 3, 72.5, suffix="mN/m")
        form.addRow("Solvent surface tension:", self.sigma0_value)

        self.temperature_value = _spin(-20.0, 150.0, 2, 23.0, suffix="degC")
        form.addRow("Temperature:", self.temperature_value)

        self.d_guess_value = _spin(1e-14, 1e-5, 14, 1.0e-9)
        form.addRow("Diffusion coefficient D (illustrative initial guess, m^2/s):", self.d_guess_value)

        bounds_row = QHBoxLayout()
        self.d_lower_exp = _spin(-16.0, -4.0, 1, -13.0)
        self.d_upper_exp = _spin(-16.0, -4.0, 1, -7.0)
        bounds_row.addWidget(QLabel("log10(D) bounds:"))
        bounds_row.addWidget(self.d_lower_exp)
        bounds_row.addWidget(self.d_upper_exp)
        form.addRow(bounds_row)
        return box

    def _build_actions_group(self) -> QGroupBox:
        box = QGroupBox("5. Run & export")
        layout = QVBoxLayout(box)

        run_row = QHBoxLayout()
        simulate_btn = QPushButton("Simulate")
        simulate_btn.clicked.connect(self._on_simulate)
        fit_btn = QPushButton("Fit D")
        fit_btn.clicked.connect(self._on_fit)
        run_row.addWidget(simulate_btn)
        run_row.addWidget(fit_btn)
        layout.addLayout(run_row)

        export_row = QHBoxLayout()
        export_pred_btn = QPushButton("Export predictions CSV...")
        export_pred_btn.clicked.connect(self._on_export_predictions)
        export_summary_btn = QPushButton("Export fit summary CSV...")
        export_summary_btn.clicked.connect(self._on_export_summary)
        export_png_btn = QPushButton("Export plot PNG...")
        export_png_btn.clicked.connect(self._on_export_png)
        export_row.addWidget(export_pred_btn)
        export_row.addWidget(export_summary_btn)
        export_row.addWidget(export_png_btn)
        layout.addLayout(export_row)
        return box

    # ------------------------------------------------------------------
    # UI event handlers (gather state, delegate to pure functions)
    # ------------------------------------------------------------------
    def _on_preset_changed(self, name: str) -> None:
        if name not in SURFACTANT_PRESETS:
            return
        preset = SURFACTANT_PRESETS[name]
        self.conc_unit_combo.setCurrentText(ConcentrationUnit.MOLAR.value)
        self.a_value.setValue(preset.a_M)
        self.gamma_inf_value.setValue(preset.gamma_inf_umol_per_m2)
        if self.isotherm_combo.currentText() != "Langmuir":
            QMessageBox.information(
                self,
                "Preset applied",
                "Preset values are Langmuir equilibrium parameters from the lab "
                "handout. For non-Langmuir isotherms these are reference/initial "
                "values only, not independently validated parameters for that model.",
            )

    def _on_isotherm_changed(self, display_name: str) -> None:
        name = {v: k for k, v in ISOTHERM_DISPLAY_NAMES.items()}[display_name]
        show_gamma_inf = name != "henry"
        show_k = name in ("frumkin", "generalized_frumkin")
        show_p = name == "generalized_frumkin"
        self.gamma_inf_value.setVisible(show_gamma_inf)
        self._isotherm_form.labelForField(self.gamma_inf_value).setVisible(show_gamma_inf)
        self.k_value.setVisible(show_k)
        self.k_label.setVisible(show_k)
        self.p_value.setVisible(show_p)
        self.p_label.setVisible(show_p)

    def _current_isotherm_name(self) -> str:
        return {v: k for k, v in ISOTHERM_DISPLAY_NAMES.items()}[self.isotherm_combo.currentText()]

    def _build_isotherm_params(self) -> dict:
        name = self._current_isotherm_name()
        a_mol_per_m3 = concentration_to_mol_per_m3(self.a_value.value(), ConcentrationUnit.MOLAR)
        gamma_inf_mol_per_m2 = gamma_inf_to_mol_per_m2(
            self.gamma_inf_value.value(), GammaInfUnit.MICROMOL_PER_M2
        )
        if name == "henry":
            return {"a_mol_per_m3": a_mol_per_m3, "gamma_inf_mol_per_m2": gamma_inf_mol_per_m2}
        if name == "langmuir":
            return {"a_mol_per_m3": a_mol_per_m3, "gamma_inf_mol_per_m2": gamma_inf_mol_per_m2}
        if name == "frumkin":
            return {
                "a_mol_per_m3": a_mol_per_m3,
                "gamma_inf_mol_per_m2": gamma_inf_mol_per_m2,
                "k": self.k_value.value(),
            }
        if name == "generalized_frumkin":
            return {
                "a_mol_per_m3": a_mol_per_m3,
                "gamma_inf_mol_per_m2": gamma_inf_mol_per_m2,
                "k": self.k_value.value(),
                "p": self.p_value.value(),
            }
        raise IsothermError(f"Unknown isotherm: {name}")

    def _build_settings(self) -> FitSettings:
        return FitSettings(
            isotherm_name=self._current_isotherm_name(),
            isotherm_params=self._build_isotherm_params(),
            bulk_concentration_mol_per_m3=concentration_to_mol_per_m3(
                self.conc_value.value(), ConcentrationUnit(self.conc_unit_combo.currentText())
            ),
            temperature_K=celsius_to_kelvin(self.temperature_value.value()),
            solvent_sigma0_N_per_m=tension_to_N_per_m(
                self.sigma0_value.value(), TensionUnit.MILLINEWTON_PER_METER
            ),
            diffusion_coefficient_m2_per_s=self.d_guess_value.value(),
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
            self._set_results_text(self._format_simulation_text(settings, result))
        else:
            self._set_results_text(f"Simulation failed to converge: {result.message}")

    def _on_fit(self) -> None:
        data = self._require_data()
        if data is None:
            return
        try:
            settings = self._build_settings()
            bounds = (self.d_lower_exp.value(), self.d_upper_exp.value())
            fit_result = fit_diffusivity(settings, data, log10_D_bounds=bounds)
        except (IsothermError, ValueError) as exc:
            QMessageBox.critical(self, "Fit failed", str(exc))
            return
        self.last_fit = fit_result
        self._last_simulation = fit_result.simulation
        self._redraw_plot(fit_result.simulation)
        self._set_results_text(self._format_fit_text(settings, fit_result))

    def _format_simulation_text(self, settings: FitSettings, result) -> str:
        lines = [
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
            return f"Fit failed: {fit_result.message}"
        lines = [
            f"Isotherm: {ISOTHERM_DISPLAY_NAMES[settings.isotherm_name]}  "
            f"params: {settings.isotherm_params}",
            f"Fitted apparent D: {fit_result.fitted_D_m2_per_s:.4e} m^2/s",
            f"RMSE: {fit_result.rmse_N_per_m*1000:.4f} mN/m",
            f"n observations: {fit_result.n_observations}",
        ]
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

    def _set_results_text(self, text: str) -> None:
        self.results_box.setPlainText(text)

    def _redraw_plot(self, simulation=None) -> None:
        if self.data is not None:
            new_fig = plot_sigma_vs_time(self.data, simulation)
        else:
            new_fig = Figure(figsize=(6, 5), dpi=100)
            new_fig.add_subplot(111).set_title("Load experimental data to begin")
        self.figure = new_fig
        self.canvas.figure = new_fig
        self.canvas.draw_idle()

    def _on_export_predictions(self) -> None:
        if self.data is None or getattr(self, "_last_simulation", None) is None:
            QMessageBox.warning(self, "Nothing to export", "Run Simulate or Fit D first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export predictions", "predictions.csv", "CSV (*.csv)")
        if not path:
            return
        export_predictions_csv(path, self.data, self._last_simulation)

    def _on_export_summary(self) -> None:
        if self.last_fit is None:
            QMessageBox.warning(self, "Nothing to export", "Run Fit D first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export fit summary", "fit_summary.csv", "CSV (*.csv)")
        if not path:
            return
        export_fit_summary_csv(path, self.last_fit, self._build_settings())

    def _on_export_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export plot", "plot.png", "PNG (*.png)")
        if not path:
            return
        save_figure_png(self.figure, path)


def run() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
