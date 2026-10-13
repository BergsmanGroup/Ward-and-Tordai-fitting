"""Entry point: ``python -m ward_tordai`` launches the GUI."""
from __future__ import annotations


def main() -> None:
    from .gui import run

    run()


if __name__ == "__main__":
    main()
