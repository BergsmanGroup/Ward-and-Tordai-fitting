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
   Matplotlib, PySide6, pytest) into it.

## Launching

```bat
run.bat
```

This always uses `.venv\Scripts\python.exe` directly, avoiding any
ambiguity with a system Python/pip installation.

## Workflow

1. **Load data.** Load a CSV (two columns: surface age and surface
   tension) or paste two columns of data directly. Choose the time unit
   (s or ms) and surface-tension unit (mN/m or dyn/cm — numerically
   identical) matching your data. Data is validated (no missing/
   non-finite values, no non-positive times) and sorted by time;
   duplicate/replicate measurements are kept, not averaged.
2. **Surfactant & concentration.** Pick a preset (Triton X-100, HTAB,
   Octanol) or "Custom", and enter the bulk surfactant concentration with
   its unit. Preset values are the lab handout's **Langmuir** equilibrium
   parameters (23 degC, water) and are **not** independently validated
   Frumkin/Generalized-Frumkin parameters; for those isotherms, treat the
   preset numbers as reference/initial values only, or enter your own.
3. **Isotherm.** Choose Henry, Langmuir, Frumkin, or Generalized Frumkin
   and set/confirm its parameters (`a`, `Gamma_inf`, and, for
   Frumkin/Generalized Frumkin, the interaction parameter `k` and, for
   Generalized Frumkin, the exponent `p`).
4. **Conditions.** Set the solvent surface tension (default 72.5 mN/m for
   water), temperature (handout reference: 23 degC), and an initial guess
   for D (order 1e-9 to 1e-10 m^2/s is typical for small surfactants in
   water; this is only a labeled starting guess, not a validated default).
5. **Simulate** runs the forward model with the entered D, without
   fitting. **Fit D** holds concentration, temperature, solvent tension,
   and isotherm parameters fixed and optimizes `D` only (via
   `log10(D)`, bounded) to minimize the unweighted sum of squared
   surface-tension residuals at the measured surface ages. Fit bounds on
   `log10(D)` are editable.
6. The plot shows measured sigma(t) as points and the model sigma(t) as a
   curve, with logarithmic time and surface tension in mN/m. The results
   panel reports the fitted/used D, RMSE (mN/m), number of observations,
   and the equilibrium surface excess/surface tension when numerically
   determined.
7. **Export** model predictions and the fit summary to CSV, and the plot
   to PNG.

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

## Known limitations

- Only the planar geometry is supported (no spherical/curved-interface
  correction, no micelle-breakup/post-CMC model).
- Only D is fitted; isotherm parameters, concentration, temperature, and
  solvent tension must be supplied and are held fixed during fitting.
- Replicates are fit individually by default (each data point
  contributes its own residual); there is no built-in replicate-averaging
  option beyond pre-averaging the input data yourself.

## Running the tests

```bat
.venv\Scripts\python.exe -m pytest
```
