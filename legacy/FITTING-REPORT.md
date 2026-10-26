# D-Primary Profile Fitting Report

## Summary

The fitting workflow now keeps the supplied Langmuir `a` and
`Gamma_inf` values fixed for the three teaching solutes (1-octanol, HTAB,
and Triton X-100). Diffusion coefficient `D` remains the primary fitted
parameter. Students may optionally select bounded profile fits for:

- bulk concentration, restricted to 0.2-2.0 mM;
- solvent surface tension, restricted by default to 70-75 mN/m;
- temperature, restricted by default to 20-26 degC;
- an effective time offset, restricted by default to -2 to +2 s.

The optional parameters are not fitted simultaneously with an unconstrained
optimizer. Each trial value is evaluated by running a complete D-only fit.
This keeps the interpretation of D clear and makes the computation
predictable for a teaching application.

## Why these parameters were selected

### Bulk concentration

The Ward-Tordai equation uses the bulk concentration as the source
concentration for diffusion, and the same concentration determines the
equilibrium surface excess through the Langmuir relation. A concentration
fit is therefore physically meaningful when the entered value is a nominal
total concentration but the free/monomer concentration is uncertain, for
example near a micellar concentration range.

The fit is deliberately limited to 0.2-2.0 mM because that is the intended
teaching range. This is not a general concentration estimator.

### Solvent surface tension

The solvent surface tension is the vertical reference of the equation of
state. It should normally be measured or taken from a temperature table,
not freely fitted. The optional narrow range is intended to absorb a small
calibration or solvent-preparation offset only.

### Effective time offset

The instrument-reported bubble lifetime may differ from the effective
surface age by a small fixed delay. The optional offset evaluates the model
at `t + offset`, while plots remain on the reported time axis. The narrow
default range prevents this control from becoming an arbitrary shape
parameter.

## Parameters intentionally not fitted

- `a` and `Gamma_inf` remain the supplied solute constants.
- Temperature remains fixed to the measured experimental temperature.
- Frumkin `k` and generalized exponent `p` are not part of the standard
  Langmuir teaching fit. Activating them would change the adsorption model,
  rather than refine the same Langmuir model.
- The ionic HTAB correction, adsorption kinetics, micelle partitioning, and
  spherical bubble geometry are model extensions, not scalar nuisance
  parameters. In particular, HTAB should continue to be reported as an
  apparent diffusion fit under the current planar model.

## Profile and uniqueness diagnostic

After the selected outer parameters are optimized, the program evaluates
each one at nearby values (approximately +/-10% of its allowed range) and
re-fits D. The results panel reports the increase in RMSE in mN/m. A small
increase means that the optional parameter is weakly identifiable from that
dataset; its fitted value should not be presented as precise. D remains the
primary estimate and is always reported separately.

## GUI behavior

The Conditions panel now contains:

1. D initial guess, editable `log10(D)` bounds, and a read-only last-used D;
2. rows for temperature, concentration, solvent baseline, and time offset;
3. checkboxes and finite lower/upper bounds for each optional parameter;
4. an editable Value field whenever a parameter is not selected for fitting.
5. an N values field controlling the number of grid values tested between
   each selected lower and upper bound.

The **Fit D / selected parameters** button performs the nested profile fit.
On success, selected fitted values are written back to the corresponding
input controls, and the results log records the fitted values and profile
RMSE changes.

Bounds and Value are mutually exclusive: a checked row enables its bounds and
locks Value; an unchecked row disables its bounds and uses the editable Value
as a fixed input. D has no checkbox because it is always fitted. The Value
column also stores the initial guesses before the first fit.

The solution selector, isotherm selector, and fitting table are now combined
in Step 2, titled **Fitting parameters for a given Isotherm and Solute**.
The solvent selector was removed; solvent surface tension is represented by
the table Value field and defaults to 72.5 mN/m. Isotherm rows are dynamic:
Henry exposes `a`, Langmuir exposes `a` and `Gamma_inf`, Frumkin adds `k`,
and Generalized Frumkin adds `p`. The `a` bounds are restricted to
1e-6-1e-3 M and the `Gamma_inf` bounds to 1-10 umol/m2 for this teaching
application.

The selector is now a **Fitting profile** selector rather than a solute-only
selector. Profiles contain the complete Step 2 state: solute identity,
isotherm, Value fields, bounds, N-values, and fit flags. Existing legacy JSON
The three named teaching solutes are
built-in and protected from overwrite. Editing a built-in changes the
selection to `Custom (SOLUTE)`; additional custom profiles receive
`Custom (SOLUTE)(1)`, `Custom (SOLUTE)(2)`, and so on. The Save button opens
a normal Windows JSON save dialog immediately in a
`custom_profiles` folder under the program's current working directory.
The **Refresh** button rereads that folder. Custom profiles can be renamed,
and a confirmation-protected action deletes all custom profile JSON files.
Built-in defaults are separate JSON files in the bundled
`config/default_profiles` folder.

Simulation is available directly in Step 2 and reads the Value column
without invoking the fitter. It evaluates a logarithmically spaced grid with
the selected simulation-point count (100 by default), rather than reusing
the experimental timestamps, which produces a smooth curve.

The progress bar in Step 4 reports the exact number of D evaluations planned
for the selected profile search. This includes the initial candidate, three
coordinate-refinement passes, and the two local profile evaluations used for
the uniqueness diagnostic. D itself is evaluated on the requested N-point
log10 grid for every candidate outer parameter combination. Step 2 displays
both the number of outer fit permutations and the resulting D-evaluation
count, and updates those counts as Fit checkboxes or N-values change.

The optional mM, mN/m, and seconds controls now use additive 0.1-unit
spinner steps. Their validators strip the displayed suffix before checking
the numeric value, so typed values such as `1.2 mM`, `72.4 mN/m`, and
`-0.5 s` are accepted. Each bound row also displays the value used by the
most recent fit.

## Validation

The existing fitting, solver, isotherm, and GUI tests remain passing. A new
regression test verifies that the profiled fitter recovers a synthetic
diffusion coefficient while preserving the D-primary workflow and emitting a
profile diagnostic.
