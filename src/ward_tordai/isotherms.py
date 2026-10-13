"""Adsorption isotherms and their conjugate surface equations of state.

Conventions follow (and are verified against) two independent sources:

1. Li, Shaw, Evans & Stevenson (2010), *Computers & Chemical Engineering*
   34, 146-153 - Henry and Langmuir isotherms/equations of state (their
   Eqs. 5-12), including the Frumkin interaction parameter ``A``.
2. The legacy "Ward and Tordai (Langmuir)" VBA workbook (``EqAdsorb.bas``),
   which additionally defines a "Generalized Frumkin" isotherm with an
   exponent ``pL`` (not present in the Li et al. paper - the prompt that
   commissioned this program explicitly notes this is a workbook-only
   extension, not a peer-reviewed form).

All isotherms here are parameterized by:

- ``a``  : surface activity / characteristic concentration, mol/m^3
           (equivalent to ``1/K`` for the corresponding Langmuir-type
           equilibrium constant; NOT the reciprocal of the Henry constant).
- ``gamma_inf`` : saturation (monolayer) surface excess, mol/m^2
           (``None``/unused for Henry, which has no saturation limit).
- ``k``  : dimensionless surface interaction parameter (Frumkin / Generalized
           Frumkin only). ``k = 0`` must reproduce the Langmuir isotherm.
- ``p``  : dimensionless generalized-Frumkin exponent. ``p = 1`` must
           reproduce the ordinary Frumkin isotherm.

Every isotherm implements the common ``Isotherm`` protocol:

- ``c_subsurface(gamma)``: the inverse isotherm ``c = c(Gamma)``, i.e. the
  sub-surface concentration in equilibrium with a given surface excess.
  This is exactly the form the Ward-Tordai solver needs (it marches
  forward in Gamma and needs the corresponding c at each step).
- ``surface_tension(gamma, temperature_K, sigma0_N_per_m)``: the
  corresponding equation of state, sigma(Gamma).
- ``equilibrium_gamma(bulk_conc_mol_per_m3)``: solves the *forward*
  isotherm Gamma(c) at equilibrium (used for reporting, not for the
  solver's time marching).
- ``validate_gamma(gamma)``: raises ``IsothermError`` for physically
  invalid surface excess (e.g. Gamma outside [0, Gamma_inf) for a
  saturating isotherm).

Thermodynamic self-consistency (Gibbs adsorption equation,
``d(sigma) = -Gamma * R * T * d(ln c)``) between each ``c_subsurface`` and
``surface_tension`` pair has been verified analytically and is also
exercised numerically in ``tests/test_isotherms.py``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional, Type

import numpy as np
from scipy.optimize import brentq

from .units import GAS_CONSTANT_R


class IsothermError(ValueError):
    """Raised for invalid isotherm parameters or an invalid surface state."""


class Isotherm(ABC):
    """Common interface implemented by every adsorption isotherm model."""

    name: str = "base"
    #: Number of dissociated ions per surfactant molecule. Fixed at 1
    #: throughout (see Li et al. Eq. 7): the Ward-Tordai / isotherm
    #: formulation used here is only intended for non-ionic surfactants.
    n_ions: int = 1

    def __init__(self, gamma_inf_mol_per_m2: float | None = None):
        self.gamma_inf = gamma_inf_mol_per_m2
        self.validate_parameters()

    @abstractmethod
    def validate_parameters(self) -> None:
        """Raise IsothermError if the stored parameters are unphysical."""

    @abstractmethod
    def c_subsurface(self, gamma: np.ndarray | float) -> np.ndarray | float:
        """Inverse isotherm: sub-surface concentration c(Gamma), mol/m^3."""

    @abstractmethod
    def surface_tension(
        self, gamma: np.ndarray | float, temperature_K: float, sigma0_N_per_m: float
    ) -> np.ndarray | float:
        """Equation of state: surface tension sigma(Gamma), N/m."""

    def validate_gamma(self, gamma: np.ndarray | float) -> None:
        gamma_arr = np.atleast_1d(np.asarray(gamma, dtype=float))
        if np.any(gamma_arr < -1e-300) or np.any(~np.isfinite(gamma_arr)):
            raise IsothermError("Gamma must be finite and non-negative")
        if self.gamma_inf is not None and np.any(gamma_arr >= self.gamma_inf):
            raise IsothermError(
                f"Gamma must be strictly less than Gamma_inf ({self.gamma_inf} mol/m^2)"
            )

    def equilibrium_gamma(
        self, bulk_conc_mol_per_m3: float, gamma_upper: float | None = None
    ) -> float:
        """Solve the forward isotherm Gamma(c) for the equilibrium surface excess.

        Uses bounded root-finding on ``c_subsurface(Gamma) - c_bulk = 0``,
        which is valid for every isotherm implemented here (all are
        monotonically increasing in Gamma).
        """
        if bulk_conc_mol_per_m3 <= 0:
            raise IsothermError("bulk_conc_mol_per_m3 must be positive")

        def residual(gamma: float) -> float:
            return self.c_subsurface(gamma) - bulk_conc_mol_per_m3

        lower = 0.0
        if self.gamma_inf is not None:
            upper = gamma_upper if gamma_upper is not None else self.gamma_inf * (1 - 1e-12)
        else:
            # Henry: no saturation limit, expand the bracket until it brackets the root.
            upper = 1e-6
            while residual(upper) < 0:
                upper *= 10.0
                if upper > 1e6:
                    raise IsothermError(
                        "Could not bracket equilibrium Gamma for Henry isotherm"
                    )
        if residual(lower) > 0:
            raise IsothermError("Equilibrium Gamma bracketing failed at Gamma=0")
        return brentq(residual, lower, upper, xtol=1e-18, rtol=1e-12, maxiter=200)


class HenryIsotherm(Isotherm):
    """Henry's law isotherm: Gamma = K_H * c, with K_H = Gamma_inf / a.

    There is no saturation limit; ``gamma_inf`` here is used purely to set
    the (dimensionless) slope and is not a physical monolayer capacity.
    """

    name = "henry"

    def __init__(self, a_mol_per_m3: float, gamma_inf_mol_per_m2: float):
        self.a = a_mol_per_m3
        super().__init__(gamma_inf_mol_per_m2=None)
        self._gamma_inf_param = gamma_inf_mol_per_m2  # used only to define K_H
        self.validate_parameters()

    def validate_parameters(self) -> None:
        if self.a is not None and self.a <= 0:
            raise IsothermError("Henry isotherm: a must be positive")
        if hasattr(self, "_gamma_inf_param") and self._gamma_inf_param <= 0:
            raise IsothermError("Henry isotherm: gamma_inf must be positive")

    @property
    def henry_constant(self) -> float:
        """K_H = Gamma_inf / a, units m (so that Gamma = K_H * c)."""
        return self._gamma_inf_param / self.a

    def c_subsurface(self, gamma):
        return np.asarray(gamma, dtype=float) / self.henry_constant

    def surface_tension(self, gamma, temperature_K, sigma0_N_per_m):
        self.validate_gamma(gamma)
        rt = GAS_CONSTANT_R * temperature_K
        return sigma0_N_per_m - self.n_ions * rt * np.asarray(gamma, dtype=float)


class LangmuirIsotherm(Isotherm):
    """Langmuir isotherm: Gamma = Gamma_inf * c / (a + c).

    Here ``a`` is the characteristic concentration (equal to ``1/K_L``
    in the Li et al. notation), matching the lab handout's preset table.
    """

    name = "langmuir"

    def __init__(self, a_mol_per_m3: float, gamma_inf_mol_per_m2: float):
        self.a = a_mol_per_m3
        super().__init__(gamma_inf_mol_per_m2=gamma_inf_mol_per_m2)

    def validate_parameters(self) -> None:
        if self.a <= 0:
            raise IsothermError("Langmuir isotherm: a must be positive")
        if self.gamma_inf is None or self.gamma_inf <= 0:
            raise IsothermError("Langmuir isotherm: gamma_inf must be positive")

    def c_subsurface(self, gamma):
        gamma_arr = np.asarray(gamma, dtype=float)
        return self.a * gamma_arr / (self.gamma_inf - gamma_arr)

    def surface_tension(self, gamma, temperature_K, sigma0_N_per_m):
        self.validate_gamma(gamma)
        rt = GAS_CONSTANT_R * temperature_K
        x = np.asarray(gamma, dtype=float) / self.gamma_inf
        return sigma0_N_per_m + self.n_ions * rt * self.gamma_inf * np.log(1 - x)


class FrumkinIsotherm(Isotherm):
    """Frumkin isotherm with interaction parameter k (k=0 reduces to Langmuir).

    c(Gamma) = a * exp(-k * Gamma/Gamma_inf) * Gamma / (Gamma_inf - Gamma)
    sigma(Gamma) = sigma0 + n*R*T*Gamma_inf * [ln(1 - x) + 0.5*k*x^2],  x = Gamma/Gamma_inf

    Verified thermodynamically self-consistent with the Gibbs adsorption
    equation, and matches both Li et al. (2010) Eqs. (11)-(12) (with their
    "A" equal to this module's "k") and the legacy VBA workbook's ``kL``.
    """

    name = "frumkin"

    def __init__(self, a_mol_per_m3: float, gamma_inf_mol_per_m2: float, k: float):
        self.a = a_mol_per_m3
        self.k = k
        super().__init__(gamma_inf_mol_per_m2=gamma_inf_mol_per_m2)

    def validate_parameters(self) -> None:
        if self.a <= 0:
            raise IsothermError("Frumkin isotherm: a must be positive")
        if self.gamma_inf is None or self.gamma_inf <= 0:
            raise IsothermError("Frumkin isotherm: gamma_inf must be positive")
        if not np.isfinite(self.k):
            raise IsothermError("Frumkin isotherm: k must be finite")

    def c_subsurface(self, gamma):
        gamma_arr = np.asarray(gamma, dtype=float)
        x = gamma_arr / self.gamma_inf
        return self.a * np.exp(-self.k * x) * gamma_arr / (self.gamma_inf - gamma_arr)

    def surface_tension(self, gamma, temperature_K, sigma0_N_per_m):
        self.validate_gamma(gamma)
        rt = GAS_CONSTANT_R * temperature_K
        x = np.asarray(gamma, dtype=float) / self.gamma_inf
        return sigma0_N_per_m + self.n_ions * rt * self.gamma_inf * (
            np.log(1 - x) + 0.5 * self.k * x**2
        )


class GeneralizedFrumkinIsotherm(Isotherm):
    """Generalized Frumkin isotherm with exponent p (p=1 reduces to Frumkin).

    c(Gamma) = a * exp(-k * (Gamma/Gamma_inf)^p) * Gamma / (Gamma_inf - Gamma)
    sigma(Gamma) = sigma0 + n*R*T*Gamma_inf * [ln(1-x) + (p/(p+1))*k*x^(p+1)]

    This form is specific to the legacy VBA workbook (``EqAdsorb.bas``,
    Mode 4) and is **not** present in Li et al. (2010); it is reproduced
    here exactly as implemented in that workbook. Thermodynamic
    self-consistency with the Gibbs adsorption equation has been verified
    analytically for general p, and p=1 is verified to exactly reproduce
    the ordinary Frumkin isotherm above.
    """

    name = "generalized_frumkin"

    def __init__(
        self, a_mol_per_m3: float, gamma_inf_mol_per_m2: float, k: float, p: float
    ):
        self.a = a_mol_per_m3
        self.k = k
        self.p = p
        super().__init__(gamma_inf_mol_per_m2=gamma_inf_mol_per_m2)

    def validate_parameters(self) -> None:
        if self.a <= 0:
            raise IsothermError("Generalized Frumkin isotherm: a must be positive")
        if self.gamma_inf is None or self.gamma_inf <= 0:
            raise IsothermError("Generalized Frumkin isotherm: gamma_inf must be positive")
        if not np.isfinite(self.k):
            raise IsothermError("Generalized Frumkin isotherm: k must be finite")
        if self.p <= 0:
            raise IsothermError("Generalized Frumkin isotherm: p must be positive")

    def c_subsurface(self, gamma):
        gamma_arr = np.asarray(gamma, dtype=float)
        x = gamma_arr / self.gamma_inf
        return (
            self.a
            * np.exp(-self.k * x**self.p)
            * gamma_arr
            / (self.gamma_inf - gamma_arr)
        )

    def surface_tension(self, gamma, temperature_K, sigma0_N_per_m):
        self.validate_gamma(gamma)
        rt = GAS_CONSTANT_R * temperature_K
        x = np.asarray(gamma, dtype=float) / self.gamma_inf
        return sigma0_N_per_m + self.n_ions * rt * self.gamma_inf * (
            np.log(1 - x) + (self.p / (self.p + 1)) * self.k * x ** (self.p + 1)
        )


#: Registry mapping isotherm name -> class, enabling new isotherms to be
#: added without touching the GUI, solver, or fitter beyond registration.
ISOTHERM_REGISTRY: Dict[str, Type[Isotherm]] = {
    HenryIsotherm.name: HenryIsotherm,
    LangmuirIsotherm.name: LangmuirIsotherm,
    FrumkinIsotherm.name: FrumkinIsotherm,
    GeneralizedFrumkinIsotherm.name: GeneralizedFrumkinIsotherm,
}


def build_isotherm(name: str, params: dict) -> Isotherm:
    """Construct a registered isotherm by name from a parameter dict."""
    try:
        cls = ISOTHERM_REGISTRY[name]
    except KeyError as exc:
        raise IsothermError(
            f"Unknown isotherm '{name}'. Available: {sorted(ISOTHERM_REGISTRY)}"
        ) from exc
    return cls(**params)


@dataclass(frozen=True)
class SurfactantPreset:
    """Langmuir equilibrium parameters from the lab handout (23 degC, water).

    These are Langmuir parameters only; they are NOT independently
    validated Frumkin/Generalized Frumkin parameters (see module docstring
    of ``gui.py`` for how non-Langmuir isotherms use these as reference
    values only).

    Optional ``suggested_*`` fields provide convenience starting values for
    an associated known dataset (e.g. the "Test" preset below); they are
    left as ``None`` for the three handout presets, which are not tied to
    a specific concentration or D.
    """

    display_name: str
    gamma_inf_umol_per_m2: float
    a_M: float  # mol/L
    suggested_bulk_conc_M: Optional[float] = None
    suggested_D_m2_per_s: Optional[float] = None
    suggested_temperature_C: Optional[float] = None
    suggested_sigma0_mN_per_m: Optional[float] = None
    note: str = ""


SURFACTANT_PRESETS: Dict[str, SurfactantPreset] = {
    # NOTE on the Triton X-100 "a" value: the lab handout table originally
    # supplied for this program listed a = 6.62e-7 M. Cross-validating
    # against the legacy "000_Ward Tordai Fitting Program (KBC).xlsm"
    # workbook's own saved Console state (Gamma_eq = 2.8827e-10 mol/cm^2,
    # sigma_eq = 38.8087 dyne/cm, for Co = 7e-7 mol/cm^3 at 25 degC) shows
    # those equilibrium values are reproduced exactly only with
    # a = 6.62e-9 mol/cm^3 = 6.62e-6 M (one decade higher), with
    # Gamma_inf = 2.91e-10 mol/cm^2 = 2.91 umol/m^2 matching as given.
    # Using this corrected value resolves fits that previously failed to
    # converge to a sensible D for this preset.
    "Triton X-100": SurfactantPreset("Triton X-100", 2.91, 6.62e-6),
    "HTAB": SurfactantPreset("HTAB", 8.00, 3.70e-4),
    "Octanol": SurfactantPreset("Octanol", 8.95, 5.57e-4),
    # Known-good Langmuir parameters recovered from the KBC workbook's own
    # saved/converged Console state for the data in "experimental_data.csv"
    # (also labeled, inconsistently, "HTAB" and "Octanol" in different
    # cells of that workbook) - the true chemical identity of this sample
    # is not established, hence "Test" rather than a surfactant name.
    "Test (unknown surfactant)": SurfactantPreset(
        "Test (unknown surfactant)",
        gamma_inf_umol_per_m2=2.91,
        a_M=6.62e-6,
        suggested_bulk_conc_M=7.0e-4,
        suggested_D_m2_per_s=4.0e-10,
        suggested_temperature_C=25.0,
        suggested_sigma0_mN_per_m=72.5,
        note=(
            "Parameters recovered from the legacy workbook's own converged "
            "fit of experimental_data.csv (Langmuir isotherm, 25 degC, "
            "72.5 mN/m solvent tension). Chemical identity uncertain; use "
            "only to validate this program's numerics against that known "
            "result (RMSE ~1.0 mN/m, R^2 ~0.994 with D re-fit)."
        ),
    ),
}
