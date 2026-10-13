# Copilot implementation prompt: Ward–Tordai profile-fitting application

## Objective
Build a **small, working Python desktop application** for a chemical engineering teaching lab. Its sole assignment-specific task is **Treatment of Results, item 2**:

> Attempt a profile-fit of surface tension, σ(t), for each concentration studied using Ward–Tordai analysis. Determine the apparent diffusion coefficient D giving the best fit in each case, using the given equilibrium adsorption parameters.

Do not implement the assignment's other tasks (standalone experimental plots for all solutions, half-coverage / characteristic-time calculations, or early-/long-time linear extrapolation methods). A plot showing the experimental data and fitted model **within the fitting window** is essential.

Students measure dynamic surface tension with a **SITA DynoTester handheld maximum bubble-pressure tensiometer**. The essential measured fields are **bubble lifetime (surface age)** and **surface tension**; temperature can be optional metadata. Do not require raw bubble-pressure traces.

Prioritize numerical correctness, an intuitive workflow, and a modest codebase. Avoid re-creating the legacy Excel workbook's large interface or supporting every historical option.

## Required user workflow
1. Load a CSV with time/bubble lifetime and surface tension, or paste two columns of experimental data. Allow explicit time units (ms or s) and surface-tension units (mN/m or dyn/cm). Sort by time, reject nonpositive time values for log plotting, preserve duplicate measurements, and validate missing/nonfinite values.
2. Select surfactant preset (**Triton X-100**, **HTAB**, or **octanol**) or a custom solution. Enter **bulk surfactant concentration**, with clearly displayed units and conversion to SI internally.
3. Select **Henry**, **Langmuir**, **Frumkin**, or **Generalized Frumkin** adsorption isotherm. Enter or confirm its equilibrium adsorption parameters. The presets below are **Langmuir** parameters; do not represent them as independently validated Frumkin/generalized Frumkin parameters. For non-Langmuir models, allow explicit parameter input, or use the Langmuir parameters only as clearly labeled initial/reference values when mathematically appropriate.
4. Specify solvent surface tension and temperature (23 °C is the handout reference temperature). Enter an initial apparent diffusion coefficient D, or accept a physically reasonable, clearly labeled starting guess.
5. Click **Fit D**. Keep bulk concentration, temperature, solvent surface tension, and isotherm parameters **fixed**; optimize **D only** by minimizing the unweighted sum of squared surface-tension residuals at the measured surface ages. Provide sensible, editable positive D bounds and fit failure messages. Also provide a **Simulate** action that uses the entered D without fitting.
6. Plot measured σ(t) as points and predicted σ(t) as a curve on the same axes, with **logarithmic time** and surface tension in mN/m. Report fitted D (m²/s), RMSE (mN/m), number of observations, and equilibrium surface tension/coverage when those quantities are meaningful and numerically determined. Display the parameters actually used.
7. Export model-predicted data and fit summary to CSV, and export the plot as PNG. A simple Windows-oriented local installation/launcher is sufficient; no web service or database.

## Presets provided by the lab handout
At **23 °C**, for solutions in pure water:

| Surfactant | Langmuir Γ∞ (µmol/m²) | Langmuir a (M = mol/L) |
|---|---:|---:|
| Triton X-100 | 2.91 | 6.62e-7 |
| HTAB | 8.00 | 3.70e-4 |
| Octanol | 8.95 | 5.57e-4 |

The legacy workbook writes the Langmuir relation as **Γ = Γ∞ C/(a + C)**. Consistently convert concentrations between M and mol/m³; convert Γ∞ between µmol/m² and mol/m². Do not confuse `a` (a concentration) with the reciprocal Langmuir equilibrium constant. Do not silently assume the experimental bulk concentration equals the preset `a`.

**Scientific caveat:** HTAB is ionic, whereas the supplied Li et al. numerical paper focuses on nonionic diffusion-controlled adsorption. Keep the result labeled **apparent D under the selected model**, rather than implying a direct molecular diffusion measurement. The model assumes instantaneous adsorption equilibrium at the interface.

## Numerical requirements
- Solve the **planar** Ward–Tordai equation for diffusion-controlled adsorption; **spherical curvature, micelle breakup, post-CMC modeling, and the original advanced numerical-tweaking controls are out of scope**.
- Support all four requested isotherms, including their matching equations of state used to convert Γ(t) to σ(t). Refer to the attached legacy VBA source and its README for the **exact conventions** of Henry, Langmuir, Frumkin, and generalized Frumkin (including sign and exponent conventions), and to Li et al. for the numerical method. Do **not** infer that the paper itself includes generalized Frumkin—it is from the workbook.
- Keep the isotherm math, its parameter validation, subsurface concentration c(Γ), and surface equation of state separate from the time-integration code. Make adding an isotherm possible without editing the GUI, solver, or fitter beyond registration.
- Use a robust quadrature/time-stepping method and bounded root solving. Address the Ward–Tordai kernel's integrable endpoint singularity explicitly and document the method. Do not simply evaluate 1/sqrt(t−τ) at τ=t. Detect nonconvergence and invalid physical states (e.g., Γ outside [0, Γ∞) for saturating models) and fail visibly rather than returning a convincing-looking curve.
- Predict surface tension at the **actual measured times** (directly or through reliable interpolation). Do not reproduce the legacy VBA approach of matching each observation to the next time-grid point without interpolation.
- Prefer optimizing **log10(D)** over raw D to keep D positive and well-scaled. Start with a bounded scalar optimizer (`scipy.optimize.minimize_scalar`) since only D is fitted. Mark a failed forward solve as an invalid objective and handle optimizer failure gracefully.
- Use consistent SI units within computation, explicit unit conversions at I/O boundaries, and tests for each conversion.
- Fit raw replicate measurements individually unless the user explicitly chooses to average them. Never silently drop replicates.
- No arbitrary hard-coded claims of physical suitability for default parameter values; clearly label illustrative defaults.

## Modular architecture (important)
Use a lightweight installable Python package under `src/ward_tordai/` with small, typed, independently testable modules. Suggested layout (adjust names if there is a good reason):

```text
ward-tordai-fit/
  pyproject.toml
  requirements.txt                 # optional convenience, in sync with pyproject
  README.md
  setup.bat
  run.bat
  examples/
    sample_data.csv
  src/ward_tordai/
    __init__.py
    models.py                     # dataclasses: experimental data, settings, results
    units.py                      # unit conversions, no UI code
    isotherms.py                 # model protocol/ABC + registry + 4 isotherms
    solver.py                     # planar Ward–Tordai forward solution only
    fitting.py                    # optimize D only, objective and metrics
    io.py                         # CSV input/output
    plotting.py                   # pure plotting functions
    gui.py                        # PySide6 presentation/controller
    __main__.py                   # python -m ward_tordai
  tests/
    test_units.py
    test_isotherms.py
    test_solver.py
    test_fitting.py
    test_io.py
```

**Design contracts:**
- `solve(settings, time_s: np.ndarray) -> SimulationResult` is pure/deterministic and usable without a GUI.
- `fit_diffusivity(settings, observations) -> FitResult` invokes the same solver and returns optimized D, predictions, metrics, convergence/diagnostic information.
- Isotherms implement a common interface for `c_subsurface(gamma)`, `surface_tension(gamma, temperature, sigma_0)`, parameter validation, and (if available) equilibrium calculation; explicitly define unit conventions.
- Plotting functions accept arrays/results and return a Matplotlib figure; no fitting logic in plotting.
- GUI imports and orchestrates functions; do not put mathematical expressions or the optimizer inside button callbacks.
- No global mutable numerical state. Prefer dataclasses, type hints, clear exceptions, and docstrings. Keep dependency choices modest: NumPy, SciPy, pandas (if actually helpful), Matplotlib, PySide6, pytest.
- Make new analysis features (e.g. half-coverage, early-/long-time methods), additional model parameters, batch processing, and new isotherms possible later by **adding modules**, not restructuring the numerical core. Do **not implement** these extensions now.

## Validation and deliverables
1. Unit tests for parameter/unit handling, each isotherm and its equation of state, equilibrium consistency, basic physical bounds, data loading, and failures.
2. Verify **Frumkin at interaction parameter zero reproduces Langmuir** when their shared parameters are matched; verify generalized Frumkin reduces to ordinary Frumkin for the appropriate exponent.
3. Compare the numerical solver to at least one published example in Li et al. or reproducible output from the working VBA workbook, with tolerances documented; test time-grid refinement. Do not assert accuracy based solely on smooth plots.
4. Synthetic fitting test: generate data using the solver with a known D, then recover D within a stated tolerance.
5. An example CSV with *clearly synthetic* data and a README explaining installation, launch, units, fit/simulate, interpretation of apparent D, and known model limitations.
6. `setup.bat` creates `.venv` and installs the local package and dependencies; `run.bat` launches it using `.venv\Scripts\python.exe` to avoid ambiguous system Python/pip environments.

## Implementation sequence
**First working milestone:** package skeleton, isotherms, solver, tests, CSV input, single-dataset GUI, basic σ-vs-log(t) overlay plot, and manually supplied D (`Simulate`).

**Second milestone:** reliable D-only optimizer, fit metrics, CSV/PNG export, and tests.

Implement both milestones for the requested first version, but prioritize a validated forward solver over interface polish. Keep the UI minimal and avoid speculative enhancements.

## Reference materials I will provide
- Li, Shaw, Evans, and Stevenson (2010), *A simple numerical solution to the Ward–Tordai equation for the adsorption of non-ionic surfactants* (PDF).
- The paper's supplementary C++ implementation.
- The old Ward–Tordai VBA workbook / exported VBA module ZIP (for generalized Frumkin and comparison with historical behavior).
- The workbook's 2013 README (historical student workflow).
- SITA DynoTester brochure (instrument data format and measurement range).

Inspect these sources before implementing the physical equations. If any specific equation or parameter convention cannot be verified, state the uncertainty rather than inventing it.
