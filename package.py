"""Build a native desktop package for the current operating system.

Windows:
    python package.py
    -> dist/WardTordai.exe

macOS:
    python3 package.py
    -> dist/WardTordai.app

Packaging must be run on the target operating system. PyInstaller does not
cross-compile Windows and macOS applications.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENVIRONMENT = ROOT / ".venv"
PACKAGE_NAME = "WardTordai"


def environment_python() -> Path:
    if os.name == "nt":
        return ENVIRONMENT / "Scripts" / "python.exe"
    return ENVIRONMENT / "bin" / "python"


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        raise SystemExit(
            f"Unsupported packaging platform: {system}. "
            "Run this script on Windows or macOS."
        )

    python = environment_python()
    if not python.exists():
        print(f"Creating virtual environment: {ENVIRONMENT}")
        venv.EnvBuilder(with_pip=True).create(ENVIRONMENT)

    run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(python), "-m", "pip", "install", "-e", ".[build]"])

    data_separator = ";" if system == "Windows" else ":"
    data_argument = (
        f"config{os.sep}default_profiles"
        f"{data_separator}config{os.sep}default_profiles"
    )
    command = [
        str(python),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        PACKAGE_NAME,
        "--paths",
        "src",
        "--add-data",
        data_argument,
    ]

    if system == "Windows":
        command.append("--onefile")
    else:
        # A macOS .app bundle is produced by the onedir windowed build.
        command.append("--onedir")
    command.append("launcher.py")
    run(command)

    artifact = (
        ROOT / "dist" / f"{PACKAGE_NAME}.exe"
        if system == "Windows"
        else ROOT / "dist" / f"{PACKAGE_NAME}.app"
    )
    print(f"\nBuild complete: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
