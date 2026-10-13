import numpy as np
import pytest

from ward_tordai import units


def test_time_conversions():
    assert units.time_to_seconds(1000.0, units.TimeUnit.MILLISECONDS) == pytest.approx(1.0)
    assert units.time_to_seconds(2.5, units.TimeUnit.SECONDS) == pytest.approx(2.5)
    assert units.seconds_to_time(1.0, units.TimeUnit.MILLISECONDS) == pytest.approx(1000.0)


def test_tension_conversions_mNm_and_dyncm_identical():
    v_mNm = units.tension_to_N_per_m(72.0, units.TensionUnit.MILLINEWTON_PER_METER)
    v_dyncm = units.tension_to_N_per_m(72.0, units.TensionUnit.DYNE_PER_CM)
    assert v_mNm == pytest.approx(v_dyncm)
    assert v_mNm == pytest.approx(0.072)
    assert units.N_per_m_to_mN_per_m(0.072) == pytest.approx(72.0)


def test_concentration_conversions_roundtrip():
    for unit in units.ConcentrationUnit:
        value = 3.3
        si = units.concentration_to_mol_per_m3(value, unit)
        back = units.mol_per_m3_to_concentration(si, unit)
        assert back == pytest.approx(value)


def test_molar_to_mol_per_m3():
    assert units.concentration_to_mol_per_m3(1.0, units.ConcentrationUnit.MOLAR) == pytest.approx(1000.0)


def test_gamma_inf_conversion_roundtrip():
    for unit in units.GammaInfUnit:
        value = 4.2
        si = units.gamma_inf_to_mol_per_m2(value, unit)
        back = units.mol_per_m2_to_gamma_inf(si, unit)
        assert back == pytest.approx(value)


def test_umol_per_m2_conversion():
    assert units.gamma_inf_to_mol_per_m2(2.91, units.GammaInfUnit.MICROMOL_PER_M2) == pytest.approx(2.91e-6)


def test_celsius_kelvin_roundtrip():
    assert units.kelvin_to_celsius(units.celsius_to_kelvin(23.0)) == pytest.approx(23.0)
    assert units.celsius_to_kelvin(0.0) == pytest.approx(273.15)
