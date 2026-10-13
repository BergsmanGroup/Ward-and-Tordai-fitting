import numpy as np
import pytest

from ward_tordai.isotherms import (
    FrumkinIsotherm,
    GeneralizedFrumkinIsotherm,
    HenryIsotherm,
    IsothermError,
    LangmuirIsotherm,
    build_isotherm,
)
from ward_tordai.units import GAS_CONSTANT_R

GAMMA_INF = 3.0e-6
A = 5.0e-4


def test_langmuir_equilibrium_matches_forward_isotherm():
    iso = LangmuirIsotherm(a_mol_per_m3=A, gamma_inf_mol_per_m2=GAMMA_INF)
    c = 2.0e-3
    gamma_eq = iso.equilibrium_gamma(c)
    # Forward isotherm check: Gamma = Gamma_inf * c / (a + c)
    expected = GAMMA_INF * c / (A + c)
    assert gamma_eq == pytest.approx(expected, rel=1e-6)
    # Inverse must round-trip.
    assert iso.c_subsurface(gamma_eq) == pytest.approx(c, rel=1e-6)


def test_henry_isotherm_linear_and_c_subsurface_inverts_forward():
    iso = HenryIsotherm(a_mol_per_m3=A, gamma_inf_mol_per_m2=GAMMA_INF)
    kh = iso.henry_constant
    c = 1.0e-5
    gamma = kh * c
    assert iso.c_subsurface(gamma) == pytest.approx(c, rel=1e-9)


def test_henry_surface_tension_linear_in_gamma():
    iso = HenryIsotherm(a_mol_per_m3=A, gamma_inf_mol_per_m2=GAMMA_INF)
    T = 296.15
    sigma0 = 0.072
    gamma = 1.0e-6
    sigma = iso.surface_tension(gamma, T, sigma0)
    assert sigma == pytest.approx(sigma0 - GAS_CONSTANT_R * T * gamma)


def test_frumkin_reduces_to_langmuir_at_k_zero():
    langmuir = LangmuirIsotherm(a_mol_per_m3=A, gamma_inf_mol_per_m2=GAMMA_INF)
    frumkin = FrumkinIsotherm(a_mol_per_m3=A, gamma_inf_mol_per_m2=GAMMA_INF, k=0.0)
    gamma = np.linspace(1e-8, GAMMA_INF * 0.999, 25)
    np.testing.assert_allclose(frumkin.c_subsurface(gamma), langmuir.c_subsurface(gamma))
    np.testing.assert_allclose(
        frumkin.surface_tension(gamma, 298.15, 0.072),
        langmuir.surface_tension(gamma, 298.15, 0.072),
    )


def test_generalized_frumkin_reduces_to_frumkin_at_p_one():
    frumkin = FrumkinIsotherm(a_mol_per_m3=A, gamma_inf_mol_per_m2=GAMMA_INF, k=1.4)
    gen = GeneralizedFrumkinIsotherm(a_mol_per_m3=A, gamma_inf_mol_per_m2=GAMMA_INF, k=1.4, p=1.0)
    gamma = np.linspace(1e-8, GAMMA_INF * 0.999, 25)
    np.testing.assert_allclose(gen.c_subsurface(gamma), frumkin.c_subsurface(gamma))
    np.testing.assert_allclose(
        gen.surface_tension(gamma, 298.15, 0.072),
        frumkin.surface_tension(gamma, 298.15, 0.072),
    )


@pytest.mark.parametrize(
    "isotherm_cls,params",
    [
        (LangmuirIsotherm, {"a_mol_per_m3": A, "gamma_inf_mol_per_m2": GAMMA_INF}),
        (FrumkinIsotherm, {"a_mol_per_m3": A, "gamma_inf_mol_per_m2": GAMMA_INF, "k": 1.0}),
        (
            GeneralizedFrumkinIsotherm,
            {"a_mol_per_m3": A, "gamma_inf_mol_per_m2": GAMMA_INF, "k": 1.0, "p": 1.5},
        ),
    ],
)
def test_gibbs_consistency_numeric(isotherm_cls, params):
    """dsigma/dGamma must equal -R*T*Gamma*d(ln c)/dGamma (Gibbs adsorption eqn)."""
    iso = isotherm_cls(**params)
    T = 298.15
    sigma0 = 0.072
    rt = GAS_CONSTANT_R * T
    gammas = np.linspace(GAMMA_INF * 0.05, GAMMA_INF * 0.9, 8)
    h = GAMMA_INF * 1e-6
    for g in gammas:
        dsigma_dgamma = (
            iso.surface_tension(g + h, T, sigma0) - iso.surface_tension(g - h, T, sigma0)
        ) / (2 * h)
        dlnc_dgamma = (
            np.log(iso.c_subsurface(g + h)) - np.log(iso.c_subsurface(g - h))
        ) / (2 * h)
        expected = -rt * g * dlnc_dgamma
        assert dsigma_dgamma == pytest.approx(expected, rel=1e-4, abs=1e-6)


def test_validate_gamma_rejects_out_of_range():
    iso = LangmuirIsotherm(a_mol_per_m3=A, gamma_inf_mol_per_m2=GAMMA_INF)
    with pytest.raises(IsothermError):
        iso.validate_gamma(GAMMA_INF * 1.5)
    with pytest.raises(IsothermError):
        iso.validate_gamma(-1.0)


def test_invalid_parameters_raise():
    with pytest.raises(IsothermError):
        LangmuirIsotherm(a_mol_per_m3=-1.0, gamma_inf_mol_per_m2=GAMMA_INF)
    with pytest.raises(IsothermError):
        LangmuirIsotherm(a_mol_per_m3=A, gamma_inf_mol_per_m2=-1.0)


def test_build_isotherm_registry():
    iso = build_isotherm("langmuir", {"a_mol_per_m3": A, "gamma_inf_mol_per_m2": GAMMA_INF})
    assert isinstance(iso, LangmuirIsotherm)
    with pytest.raises(IsothermError):
        build_isotherm("not_a_real_isotherm", {})
