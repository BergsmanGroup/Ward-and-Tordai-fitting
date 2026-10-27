import json

from ward_tordai.config import (
    builtin_fitting_profiles,
    ensure_live_config,
    load_parameter_sets,
    restore_default_config,
    save_parameter_set,
)


def test_builtin_fitting_profiles_are_available():
    profiles = builtin_fitting_profiles()

    assert set(profiles) == {"Triton X-100", "HTAB", "Octanol"}


def test_live_config_is_initialized_as_exact_default_copy(tmp_path):
    defaults = tmp_path / "defaults.json"
    live = tmp_path / "live.json"
    defaults.write_text(
        json.dumps(
            {
                "solutes": {
                    "Test solute": {
                        "a_M": 1e-4,
                        "gamma_inf_umol_per_m2": 3.0,
                        "k": 0.0,
                        "p": 1.0,
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = ensure_live_config(live, defaults)

    assert live.read_bytes() == defaults.read_bytes()
    assert result == load_parameter_sets(defaults)


def test_saving_new_parameter_set_and_restoring_defaults(tmp_path):
    defaults = tmp_path / "defaults.json"
    live = tmp_path / "live.json"
    defaults.write_text(
        '{"solutes":{"Default":{"a_M":1.0,"gamma_inf_umol_per_m2":2.0,"k":0.0,"p":1.0}}}',
        encoding="utf-8",
    )
    ensure_live_config(live, defaults)

    saved = save_parameter_set(
        "New solute",
        {"a_M": 3.0, "gamma_inf_umol_per_m2": 4.0, "k": 0.5, "p": 1.5},
        live,
    )
    assert saved["New solute"]["k"] == 0.5
    assert "New solute" in load_parameter_sets(live)

    restored = restore_default_config(live, defaults)
    assert restored == load_parameter_sets(defaults)
    assert live.read_bytes() == defaults.read_bytes()
