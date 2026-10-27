# Ward-Tordai Profile Fitting

A small desktop application for fitting dynamic surface-tension, sigma(t),
data (e.g. from a SITA DynoTester maximum-bubble-pressure tensiometer) to
the planar Ward-Tordai diffusion-controlled adsorption model, to extract
an **apparent diffusion coefficient D** for a chosen adsorption isotherm
and known equilibrium parameters.

This implements only the "profile-fit for D" task from the lab handout
(Treatment of Results, item 2). It does **not** implement the handout's
other tasks (standalone experimental plots across all solutions,
half-coverage/characteristic-time calculations, or early-/long-time
linear extrapolation methods).

## Installation (Windows)

1. Ensure Python 3.10+ is installed and on `PATH`.
2. From this folder, run:

   ```bat
   setup.bat
   ```

   This creates a `.venv` virtual environment and installs the
   `ward_tordai` package and its dependencies (NumPy, SciPy, pandas,
   Matplotlib, openpyxl, PySide6, pytest) into it.

## Launching

```bat
run.bat
```

This always uses `.venv\Scripts\python.exe` directly, avoiding any
ambiguity with a system Python/pip installation.

## Building a standalone desktop application

Run `python package.py` from this folder on the target operating system. The
script creates `.venv` if needed, installs the PyInstaller build dependency,
and packages the application:

- Windows creates `dist\WardTordai.exe`.
- macOS creates `dist/WardTordai.app`.

PyInstaller does not cross-compile Windows and macOS applications. To build
both packages while working on Windows, push the branch to GitHub and run
the **Package desktop applications** workflow from the Actions tab. It uses
native Windows and macOS runners and publishes `WardTordai-windows` and
`WardTordai-macos` artifacts. Alternatively, run
`.\package-all.ps1` from PowerShell (with the GitHub CLI installed and
authenticated) to dispatch that workflow for the current branch. The built
applications include their Python dependencies and bundled default-profile
JSON files, so Python is not required on student computers. On Windows,
`build.bat` remains a convenience wrapper around the local Windows build.

The macOS `.app` is for Mac students. iOS/iPadOS uses `.ipa` packages and
cannot run this PySide6 desktop application; producing an iOS app would
require a separate mobile UI/application implementation.

## Workflow

1. **Load data.** Load a CSV (two columns: surface age and surface
   tension) or paste two columns of data directly. Choose the time unit
   (s or ms) and surface-tension unit (mN/m or dyn/cm — numerically
   identical) matching your data. Data is validated (no missing/
   non-finite values, no non-positive times) and sorted by time;
   duplicate/replicate measurements are kept, not averaged.
2. **Fitting profile.** Select a fitting
   profile (Triton X-100, HTAB, or Octanol) or a
   custom profile, and select the isotherm. The single parameter table contains D,
   temperature, concentration, solvent surface tension, time offset, and the
   parameters applicable to the selected isotherm. Henry shows `a`; Langmuir
   shows `a` and `Gamma_inf`; Frumkin additionally shows `k`; and Generalized
   Frumkin additionally shows `p`. The solvent baseline defaults to 72.5
   mN/m. Selecting one of the built-in solutes sets the Langmuir parameters
   and matching suggested conditions.
   The **Save** action stores the complete Step 2 table (including bounds,
   N-values, Value fields, fit checkboxes, and isotherm) in
   as a JSON file in a `custom_profiles` folder under the program's current
   working directory. Built-in profiles are stored as JSON files in the
   bundled `config/default_profiles` folder and cannot
   be overwritten. Editing a built-in creates a `Custom (SOLUTE)` profile,
   with numbered suffixes when needed. The **Refresh** button rereads that
   folder, and custom profiles may be renamed or deleted in the save dialog.
   All numeric fields accept plain decimals or scientific notation
   (e.g. `7e-11`, `7E-11`) and arbitrary digit counts (e.g. typing extra
   trailing zeros will not be rejected).
3. **Simulate** runs the forward model with the entered D, without
   fitting, on the selected number of logarithmically spaced simulation
   points (100 by default). **Fit D / selected parameters** always fits D
   first. Optional
   checkboxes can enable bounded profile fits for bulk concentration
   (0.2-2.0 mM), temperature (20-26 degC by default), solvent surface
   tension, time offset, and the selected isotherm parameters. D is always
   fitted. For each optional row, checking
   Fit enables the bounds and locks Value; clearing Fit disables the
   bounds and uses the editable Value field as a fixed input. An N values
   control sets how many values are tested between each selected bound. The Value
   column stores the initial guesses before the first fit and is updated
   after each fit.
   Every trial value of an optional parameter runs a complete D fit, so D
   remains the primary reported estimate. Fit bounds on `log10(D)` and the
   optional parameters are editable. On success, fitted values are written
   back into the input fields and an entry is appended to the results/log
   panel below the plot. The log also reports a local RMSE-profile
   diagnostic for each optional parameter; a small profile change indicates
   weak uniqueness.
4. The plot shows measured sigma(t) as points and the model sigma(t) as a
   curve, with logarithmic time and surface tension in mN/m. The log
   panel reports the fitted/used D, fit quality (RMSE in mN/m and
   R-squared), number of observations, and the equilibrium surface
   excess/surface tension when numerically determined. Each Simulate/Fit
   D action appends a new entry rather than replacing the log.
5. **Plot and export.** Set an optional plot title and custom legend labels
   for experimental points and the Ward-Tordai line. **Export fit summary**
   writes an Excel workbook containing the fit summary, measured-time
   predictions, and a logarithmically spaced simulation dataset from the
   plotted time bounds (1000 points by default). **Export plot PNG** writes
   a white-background image at 330 DPI.

## Units

All computation is done internally in SI units (seconds, mol/m^3,
mol/m^2, N/m, m^2/s, K); conversions to/from display units (ms, M, mN/m,
dyn/cm, umol/m^2, degC) happen only at the I/O boundary (see
`src/ward_tordai/units.py`).

## Interpreting the fitted D

The reported `D` is an **apparent** diffusion coefficient under the
selected adsorption-isotherm model and the planar, diffusion-controlled
Ward-Tordai framework — it assumes instantaneous adsorption equilibrium
between the sub-surface and the interface, and it is only as physically
meaningful as that assumption and the chosen isotherm parameters are for
your system. In particular:

- **HTAB is ionic**, while the underlying numerical method (Li, Shaw,
  Evans & Stevenson, 2010) is derived for non-ionic, diffusion-controlled
  adsorption. Treat any HTAB "D" as an apparent fit parameter, not a
  direct measurement of molecular diffusivity.
- Spherical/curved-interface effects, micelle breakup, and post-CMC
  behavior are **not modeled**; fitting data taken above the CMC, or with
  significant bubble curvature effects, is outside this tool's scope.
- Generalized Frumkin is a workbook-specific extension (not present in
  the Li et al. 2010 paper); it is implemented here exactly as in the
  legacy VBA workbook and verified to reduce to ordinary Frumkin at its
  exponent `p = 1` (see `tests/test_isotherms.py`).

## Numerical method (summary)

The planar Ward-Tordai equation is solved by marching forward in time,
with the back-diffusion convolution integral discretized via the
trapezoidal rule after the substitution `u = sqrt(t - tau)`, which
eliminates the integral's endpoint singularity analytically (rather than
evaluating `1/sqrt(t-tau)` at `tau = t`, or truncating the upper limit as
a numerical workaround). At each time step, the (otherwise implicit)
surface excess is found by a bounded root solve (`scipy.optimize.brentq`)
with physically sensible brackets, matching the robust bisection approach
recommended by Li et al. (2010). See the `solver.py` module docstring for
the full derivation, and `tests/test_solver.py` for:

- a direct, independent re-implementation of the legacy VBA workbook's
  own recursion, cross-checked against this solver on the same time grid;
- the published Langmuir validation case from Li et al. (2010) (Section
  5: Gamma_inf = 1.8e-6 mol/m^2, K_L = 1838 m^3/mol, D = 5e-10 m^2/s,
  cb = 5.44e-3 mol/m^3);
- grid-refinement convergence;
- agreement with the diffusion-limited short-time asymptote
  `Gamma(t) -> 2*cb*sqrt(D*t/pi)`.

D-fitting uses `scipy.optimize.minimize_scalar` (bounded) on `log10(D)`;
a non-convergent forward solve is treated as an invalid (infinite)
objective value rather than crashing the optimizer.

## Example data

`examples/sample_data.csv` is **synthetic** data generated by this
package's own solver (Langmuir isotherm, Triton X-100-like parameters,
D = 6.0e-10 m^2/s, 1e-5 M bulk concentration, 23 degC) with added
Gaussian noise, intended only to demonstrate the workflow. It is not
real experimental data.

## Geometry and known limitations

- The default is the planar Ward-Tordai geometry. A fixed-radius spherical
  diffusion model is also available in the fitting profile. Radius is shown
  in millimetres and may be enabled as a bounded secondary parameter; D
  remains the primary fitting parameter.
- The spherical model does not represent a moving bubble radius, pressure
  coupling, gas flow, or changing bubble shape.
- D is always fitted. The supplied isotherm parameters and temperature remain
  fixed; concentration, solvent tension, and effective time offset may be
  enabled as bounded teaching-oriented profile parameters.
- Replicates are fit individually by default (each data point
  contributes its own residual); there is no built-in replicate-averaging
  option beyond pre-averaging the input data yourself.

## Running the tests

```bat
.venv\Scripts\python.exe -m pytest
```
