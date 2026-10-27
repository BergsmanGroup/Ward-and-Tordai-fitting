"""Persistence for user-saved surfactant isotherm parameters."""
from __future__ import annotations

import json
import math
import os
import shutil
import sys
import re
from pathlib import Path
from typing import Mapping


if getattr(sys, "frozen", False):
    bundle_directory = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    app_data_directory = Path(
        os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
    )
    CONFIG_DIRECTORY = app_data_directory / "Ward and Tordai Fitting"
    DEFAULT_CONFIG_PATH = bundle_directory / "config" / "surfactant_parameters.default.json"
else:
    bundle_directory = Path(__file__).resolve().parents[2]
    CONFIG_DIRECTORY = Path(__file__).resolve().parents[2] / "config"
    DEFAULT_CONFIG_PATH = CONFIG_DIRECTORY / "surfactant_parameters.default.json"

DEFAULT_PROFILES_DIRECTORY = bundle_directory / "config" / "default_profiles"

LIVE_CONFIG_PATH = CONFIG_DIRECTORY / "surfactant_parameters.json"
PARAMETER_KEYS = ("a_M", "gamma_inf_umol_per_m2", "k", "p")
DEFAULT_PROFILE_NAME = "Triton X-100 (Planar)"
BUILTIN_PROFILE_NAMES = (
    "HTAB (Planar)",
    "HTAB (Spherical)",
    "Octanol (Planar)",
    "Octanol (Spherical)",
    "Triton X-100 (Planar)",
    "Triton X-100 (Spherical)",
)
CUSTOM_PROFILE_FOLDER_NAME = "custom_profiles"
BUILTIN_SOLUTE_PARAMETERS = {
    "Triton X-100": {
        "a_M": 6.62e-6,
        "gamma_inf_umol_per_m2": 2.91,
        "k": 0.0,
        "p": 1.0,
    },
    "HTAB": {
        "a_M": 3.70e-4,
        "gamma_inf_umol_per_m2": 8.0,
        "k": 0.0,
        "p": 1.0,
    },
    "Octanol": {
        "a_M": 5.57e-4,
        "gamma_inf_umol_per_m2": 8.95,
        "k": 0.0,
        "p": 1.0,
    },
}


class ParameterConfigError(ValueError):
    """Raised when a surfactant parameter configuration is invalid."""


def load_parameter_sets(path: Path) -> dict[str, dict[str, float]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ParameterConfigError(f"Could not read parameter configuration '{path}': {exc}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("solutes"), dict):
        raise ParameterConfigError(
            f"Parameter configuration '{path}' must contain a 'solutes' object"
        )

    parameter_sets: dict[str, dict[str, float]] = {}
    for name, params in raw["solutes"].items():
        if not isinstance(name, str) or not name.strip() or not isinstance(params, dict):
            raise ParameterConfigError(f"Invalid solute entry in '{path}': {name!r}")
        if any(key not in params for key in PARAMETER_KEYS):
            raise ParameterConfigError(
                f"Solute '{name}' in '{path}' must define {', '.join(PARAMETER_KEYS)}"
            )
        try:
            values = {key: float(params[key]) for key in PARAMETER_KEYS}
        except (TypeError, ValueError) as exc:
            raise ParameterConfigError(
                f"Solute '{name}' in '{path}' has non-numeric parameters"
            ) from exc
        if any(not math.isfinite(value) for value in values.values()):
            raise ParameterConfigError(f"Solute '{name}' in '{path}' has non-finite parameters")
        if values["a_M"] <= 0 or values["gamma_inf_umol_per_m2"] <= 0 or values["p"] <= 0:
            raise ParameterConfigError(
                f"Solute '{name}' in '{path}' must have positive a, gamma_inf, and p"
            )
        parameter_sets[name] = values
    return parameter_sets


def ensure_live_config(
    live_path: Path = LIVE_CONFIG_PATH,
    defaults_path: Path = DEFAULT_CONFIG_PATH,
) -> dict[str, dict[str, float]]:
    if not live_path.exists():
        try:
            live_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(defaults_path, live_path)
        except OSError as exc:
            raise ParameterConfigError(
                f"Could not initialize live parameter configuration '{live_path}': {exc}"
            ) from exc
    return load_parameter_sets(live_path)


def save_parameter_set(
    name: str,
    parameters: Mapping[str, float],
    path: Path = LIVE_CONFIG_PATH,
) -> dict[str, dict[str, float]]:
    normalized_name = name.strip()
    if not normalized_name:
        raise ParameterConfigError("A solute name is required")
    sets = load_parameter_sets(path)
    values = {key: float(parameters[key]) for key in PARAMETER_KEYS}
    if (
        any(not math.isfinite(value) for value in values.values())
        or values["a_M"] <= 0
        or values["gamma_inf_umol_per_m2"] <= 0
        or values["p"] <= 0
    ):
        raise ParameterConfigError("Parameters must be finite and a, gamma_inf, and p positive")
    sets[normalized_name] = values
    document = json.dumps({"solutes": sets}, indent=2) + "\n"
    try:
        path.write_text(document, encoding="utf-8")
    except OSError as exc:
        raise ParameterConfigError(f"Could not save parameter configuration '{path}': {exc}") from exc
    return sets


def restore_default_config(
    live_path: Path = LIVE_CONFIG_PATH,
    defaults_path: Path = DEFAULT_CONFIG_PATH,
) -> dict[str, dict[str, float]]:
    try:
        shutil.copyfile(defaults_path, live_path)
    except OSError as exc:
        raise ParameterConfigError(
            f"Could not restore default parameter configuration: {exc}"
        ) from exc
    return load_parameter_sets(live_path)


def default_fitting_profile(name: str, parameters: Mapping[str, float]) -> dict:
    """Create a complete teaching profile from legacy solute parameters."""
    suggested = {
        "D": 1.0e-9,
        "temperature_C": 23.0,
        "concentration_mM": 1.0,
    }
    return {
        "base_solute": name,
        "isotherm_name": "langmuir",
        "fit": {
            "temperature": False,
            "concentration": False,
            "solvent_sigma0": False,
            "time_offset": False,
            "a_mol_per_m3": False,
            "gamma_inf_mol_per_m2": False,
            "k": False,
            "p": False,
        },
        "bounds": {
            "D": [-13.0, -7.0],
            "temperature_C": [20.0, 26.0],
            "concentration_mM": [0.2, 2.0],
            "solvent_sigma0_mN_per_m": [70.0, 75.0],
            "time_offset_s": [-2.0, 2.0],
            "a_M": [1e-6, 1e-3],
            "gamma_inf_umol_per_m2": [1.0, 10.0],
            "k": [-100.0, 100.0],
            "p": [1e-6, 100.0],
        },
        "n_values": {
            "D": 25,
            "temperature": 9,
            "concentration": 9,
            "solvent_sigma0": 9,
            "time_offset": 9,
            "a_mol_per_m3": 9,
            "gamma_inf_mol_per_m2": 9,
            "k": 9,
            "p": 9,
        },
        "values": {
            "D": suggested["D"],
            "temperature_C": suggested["temperature_C"],
            "concentration_mM": suggested["concentration_mM"],
            "solvent_sigma0_mN_per_m": 72.5,
            "time_offset_s": 0.0,
            "a_M": parameters["a_M"],
            "gamma_inf_umol_per_m2": parameters["gamma_inf_umol_per_m2"],
            "k": parameters["k"],
            "p": parameters["p"],
        },
    }


def load_fitting_profiles(
    path: Path,
    defaults_path: Path,
) -> dict[str, dict]:
    """Load complete profiles, migrating legacy ``solutes`` files in memory."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ParameterConfigError(f"Could not read parameter configuration '{path}': {exc}") from exc
    if isinstance(raw, dict) and isinstance(raw.get("profiles"), dict):
        return raw["profiles"]
    legacy = load_parameter_sets(path)
    return {name: default_fitting_profile(name, params) for name, params in legacy.items()}


def save_fitting_profiles(
    profiles: Mapping[str, Mapping],
    path: Path = LIVE_CONFIG_PATH,
) -> dict[str, dict]:
    try:
        document = json.dumps({"profiles": profiles}, indent=2) + "\n"
        path.write_text(document, encoding="utf-8")
    except (OSError, TypeError, ValueError) as exc:
        raise ParameterConfigError(f"Could not save fitting profiles '{path}': {exc}") from exc
    return dict(profiles)


def custom_profile_directory(root: Path | None = None) -> Path:
    base = root or Path.cwd()
    directory = base if base.name == CUSTOM_PROFILE_FOLDER_NAME else base / CUSTOM_PROFILE_FOLDER_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def default_profile_directory() -> Path:
    return DEFAULT_PROFILES_DIRECTORY


def load_default_fitting_profiles() -> dict[str, dict]:
    profiles: dict[str, dict] = {}
    for path in sorted(default_profile_directory().glob("*.json")):
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ParameterConfigError(
                f"Could not read default fitting profile '{path}': {exc}"
            ) from exc
        if not isinstance(profile, dict) or not isinstance(profile.get("values"), dict):
            raise ParameterConfigError(
                f"Default fitting profile '{path}' must contain a values object"
            )
        name = str(profile.get("name") or path.stem).strip()
        if name in BUILTIN_PROFILE_NAMES:
            profiles[name] = profile
    if set(profiles) != set(BUILTIN_PROFILE_NAMES):
        missing = ", ".join(sorted(set(BUILTIN_PROFILE_NAMES) - set(profiles)))
        raise ParameterConfigError(
            f"Missing default fitting profile JSON files: {missing}"
        )
    return profiles


def builtin_fitting_profiles() -> dict[str, dict]:
    return load_default_fitting_profiles()


def save_default_fitting_profile(name: str, profile: Mapping) -> dict:
    """Overwrite one bundled default profile after explicit GUI confirmation."""
    if name not in BUILTIN_PROFILE_NAMES:
        raise ParameterConfigError(f"Unknown default fitting profile '{name}'")
    path = default_profile_directory() / f"{safe_profile_filename(name)}.json"
    document = dict(profile)
    document["name"] = name
    try:
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    except (OSError, TypeError, ValueError) as exc:
        raise ParameterConfigError(f"Could not save default fitting profile '{path}': {exc}") from exc
    return document


def load_custom_fitting_profiles(directory: Path | None = None) -> dict[str, dict]:
    folder = custom_profile_directory(directory)
    profiles: dict[str, dict] = {}
    for path in sorted(folder.glob("*.json")):
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(profile, dict) or not isinstance(profile.get("values"), dict):
            continue
        name = str(profile.get("name") or path.stem).strip()
        if name and name not in BUILTIN_PROFILE_NAMES:
            profiles[name] = profile
    return profiles


def save_custom_fitting_profile(
    path: Path,
    name: str,
    profile: Mapping,
) -> dict:
    if path.suffix.lower() != ".json":
        path = path.with_suffix(".json")
    document = dict(profile)
    document["name"] = name
    try:
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    except (OSError, TypeError, ValueError) as exc:
        raise ParameterConfigError(f"Could not save fitting profile '{path}': {exc}") from exc
    return document


def safe_profile_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name).strip().rstrip(".")
    return cleaned or "Custom profile"
