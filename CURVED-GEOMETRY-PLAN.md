# Fixed-Radius Spherical Model Implementation Plan

## Objective

Add an optional fixed-radius spherical diffusion model alongside the existing
planar Ward-Tordai model. The spherical model will use a user-supplied,
constant bubble radius and will remain compatible with the existing
isotherms, D-primary fitting workflow, simulations, profile persistence, and
exports.

The first version will **not** model bubble expansion/contraction, gas flow,
pressure dynamics, or a time-dependent radius. It will not fit the radius by
default.

## Scope and non-goals

### Included

- Planar and fixed-radius spherical geometry choices.
- A fixed bubble-radius input in SI-backed GUI units.
- Spherical diffusion with the existing adsorption isotherm boundary
  condition.
- Reuse of the existing D-fitting and optional-parameter infrastructure.
- A curvature diagnostic based on diffusion length divided by radius.
- Numerical validation against known limits and manufactured cases.
- Profile save/load support for geometry and radius.

### Excluded

- Moving bubble radius `R(t)`.
- Coupling to gas pressure, gas volume, flow rate, or capillary pressure.
- Bubble shape deformation or non-spherical geometry.
- Fitting radius as a routine nuisance parameter.
- Micelle kinetics, adsorption kinetics, ionic corrections, or other HTAB
  chemistry changes.

## Physical formulation

For a fixed spherical interface of radius `R`, solve the liquid-side radial
diffusion equation:

```text
∂c/∂t = D / r² * ∂/∂r(r² ∂c/∂r),  r >= R
```

with:

- `c(R,t) = c_s(t)` at the interface;
- `c(r,t) -> c_b` sufficiently far from the interface;
- initial condition `c(r,0) = c_b`;
- adsorption isotherm relation `c_s = isotherm.c_subsurface(Gamma)`;
- interfacial mass balance:

```text
dGamma/dt = D * ∂c/∂r at r = R
```

The sign convention must be verified against a simple adsorption case before
being used in production. Surface tension continues to be computed from the
existing isotherm and `FitSettings` temperature/solvent baseline.

The spherical solver should use the excess concentration

```text
u(r,t) = c(r,t) - c_b
```

so the far-field boundary is `u = 0`. A transformed variable

```text
w(r,t) = r * u(r,t)
```

may be used because it reduces the spherical diffusion equation away from
the moving interface to a one-dimensional diffusion equation. The
implementation should choose the formulation that provides the clearest
mass-conservative boundary treatment; the direct finite-volume formulation
is the baseline choice.

## Numerical design

### Solver API

Extend `FitSettings` in [`src/ward_tordai/models.py`](./src/ward_tordai/models.py)
with:

```python
geometry: Literal["planar", "spherical"] = "planar"
radius_m: float | None = None
```

Validation rules:

- planar geometry ignores `radius_m`;
- spherical geometry requires finite `radius_m > 0`;
- radius is stored internally in metres;
- the GUI should display radius in millimetres.

Keep the public solver entry point compatible:

```python
solve(settings, time_s) -> SimulationResult
```

Dispatch internally:

```python
if settings.geometry == "planar":
    return solve_planar(settings, time_s)
if settings.geometry == "spherical":
    return solve_spherical(settings, time_s)
```

The existing planar implementation should be moved or renamed only as
needed. Its numerical behavior and tests must remain unchanged.

### Spatial domain

Use a finite radial domain `[R, R + L]` with a zero excess-concentration
condition at the outer boundary. Choose `L` from the maximum diffusion
length:

```text
L = max(L_min, safety_factor * sqrt(D * t_max))
```

Recommended initial values:

- `safety_factor = 8`;
- `L_min = 10 * R` only when needed to prevent the outer boundary from
  being too close;
- enforce a minimum outer radius of `R + L`.

The implementation must document this choice and expose grid controls only
internally at first. The default grid should prioritize reliable teaching
results over minimum runtime.

### Radial discretization

Use a finite-volume radial grid with cell faces in `r` and cell-centered
concentrations. This naturally accounts for the spherical shell area
`4*pi*r²` and supports a conservative flux balance.

At each time step:

1. Evaluate the radial diffusion fluxes.
2. Apply the interface flux to the adsorption mass balance.
3. Use the isotherm to relate interfacial concentration and surface excess.
4. Advance the concentration field and `Gamma`.
5. Interpolate or record the result at requested surface ages.

The first implementation may use `scipy.integrate.solve_ivp` with a
carefully defined semi-discrete system if the interface condition can be
represented cleanly. If that produces excessive overhead during D fitting,
replace it with an implicit finite-volume time stepper. The solver must
remain deterministic for repeated fit evaluations.

### Time integration

Use an implicit method suitable for diffusion stiffness, initially
`BDF` or `Radau` through `solve_ivp`. Supply tolerances explicitly and
reject non-converged integrations with a descriptive `SimulationResult`
message.

The solver should integrate on the requested time range and return only the
requested times, while allowing internal adaptive time steps. The existing
simulation grid behavior for smooth display curves remains outside the
physics solver.

### Mass conservation

Add a diagnostic during development:

```text
adsorbed_mass_per_area + integrated_liquid_excess
```

must agree with the total diffusive mass delivered through the far-field
boundary within a documented tolerance. This is especially important because
curvature errors can otherwise look like plausible changes in D.

## GUI changes

In the Step 2 **Fitting profile** table:

1. Add a `Geometry` selector with:
   - `Planar`;
   - `Spherical (fixed radius)`.
2. Add a `Bubble radius (mm)` field.
3. Enable the radius field only for spherical geometry.
4. Display a curvature diagnostic:

```text
Curvature scale: sqrt(D * t_max) / R = ...
```

Use the current Value-column D and the loaded data maximum time. Explain
briefly:

- values well below `0.1`: planar approximation likely adequate;
- values around `0.1-0.3`: compare both geometries;
- values above `0.3`: curvature may materially affect the fit.

These are screening thresholds, not claims of universal error bounds.

The Fit button must continue to fit D first. Geometry and radius are fixed
inputs in the first version and are not optional fitting parameters.

## Profile and export changes

Add the following fields to the profile JSON:

```json
{
  "geometry": "planar",
  "radius_mm": 1.0
}
```

For existing built-in profiles, use `"planar"` as the default. Custom
profiles should preserve the selected geometry and radius.

Include geometry and radius in:

- fit summary output;
- results log;
- exported workbook metadata;
- any prediction CSV metadata that already records model settings.

## Fitting behavior

The current D-primary fitter can be reused because it calls the forward
solver through `FitSettings`. Each D candidate will invoke either the planar
or spherical backend based on the profile.

Required safeguards:

- use the same D bounds for both geometries initially;
- reject spherical configurations with invalid radius;
- report solver failure rather than silently falling back to planar;
- do not automatically switch geometry after a failed fit;
- show the geometry and radius used in the fit summary.

The optional concentration, temperature, solvent-baseline, time-offset, and
isotherm-parameter profile searches should work unchanged after the solver
dispatch is implemented.

## Validation and tests

### Unit tests

Add tests for:

1. `FitSettings` geometry/radius validation.
2. Planar settings producing the existing planar results.
3. Spherical settings rejecting missing, zero, negative, and non-finite
   radius.
4. Spherical concentration remaining finite and non-negative.
5. Spherical `Gamma(t)` being non-decreasing for a standard adsorption case.
6. Spherical mass-balance residual staying below the selected tolerance.
7. Spherical solver failure returning `converged=False` with a useful message.

### Limiting-case tests

The most important regression is the planar limit:

1. Fix a representative `D`, concentration, isotherm, temperature, and
   solvent baseline.
2. Run the spherical solver with progressively larger radii.
3. Verify that the spherical surface-tension curve approaches the planar
   curve.
4. Record the radius/grid settings and establish a practical relative-error
   threshold for the teaching application.

Also test that reducing radius increases the difference from the planar
solution in the expected direction for a simple synthetic case.

### Integration tests

Add GUI tests for:

- switching between planar and spherical geometry;
- radius enabled/disabled state;
- profile round-trip persistence;
- curvature diagnostic update;
- simulation and fitting using spherical settings;
- export metadata showing geometry and radius.

## Performance and acceptance criteria

The spherical solver will be called many times during fitting, so acceptance
criteria should be explicit:

- a default spherical simulation completes in a reasonable classroom
  workflow time;
- a D-only spherical fit on the example dataset completes without freezing
  the GUI beyond the existing progress-update behavior;
- repeated runs with the same settings are numerically reproducible;
- the planar test suite remains unchanged and passing;
- the spherical solver does not silently reduce spatial or temporal
  resolution when a fit is running.

If the initial adaptive PDE implementation is too slow, optimize only after
the mass-balance and planar-limit tests pass. Potential optimizations include
reusing the radial grid, caching geometry-dependent matrices, or replacing
`solve_ivp` with a dedicated implicit finite-volume stepper.

## Implementation sequence

1. Add geometry/radius fields to `FitSettings` with validation.
2. Refactor the current solver into an explicit planar backend without
   changing its results.
3. Implement a standalone fixed-radius spherical solver.
4. Add spherical unit, conservation, and planar-limit tests.
5. Add solver dispatch through `solve`.
6. Add GUI controls and curvature diagnostic.
7. Add geometry/radius to profile persistence and exports.
8. Run planar regression tests and spherical integration tests.
9. Benchmark D-only and profile fits.
10. Document the spherical model and its radius requirements in
    [`README.md`](./README.md) and [`FITTING-REPORT.md`](./FITTING-REPORT.md).

## Definition of done

The feature is complete when:

- planar behavior is unchanged;
- fixed-radius spherical simulations converge for representative teaching
  inputs;
- spherical results pass conservation and planar-limit tests;
- geometry and radius are visible in the GUI and saved profiles;
- D fitting works with spherical geometry without special-case fitting code;
- exports identify the selected geometry and radius;
- failures are explicit and actionable;
- the README clearly states that moving-radius and iOS/mobile modeling are
  not included.
