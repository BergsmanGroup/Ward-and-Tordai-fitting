"""Pure plotting functions: no fitting logic, no GUI code.

Each function accepts already-computed arrays/results and returns a
Matplotlib ``Figure``; callers decide how to display or save it.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from matplotlib.figure import Figure

from .models import ExperimentalData, SimulationResult
from .units import N_per_m_to_mN_per_m


def plot_sigma_vs_time(
    data: ExperimentalData,
    simulation: Optional[SimulationResult] = None,
    title: str = "",
) -> Figure:
    """Plot measured sigma(t) as points and predicted sigma(t) as a curve.

    X-axis is logarithmic surface age (time); Y-axis is surface tension in
    mN/m, matching the SITA DynoTester's native reporting units.
    """
    fig = Figure(figsize=(7.0, 5.0), dpi=120)
    ax = fig.add_subplot(111)

    ax.scatter(
        data.time_s,
        N_per_m_to_mN_per_m(data.sigma_N_per_m),
        s=22,
        color="tab:blue",
        label="Experimental",
        zorder=3,
    )

    if simulation is not None and simulation.converged:
        order = np.argsort(simulation.time_s)
        ax.plot(
            simulation.time_s[order],
            N_per_m_to_mN_per_m(simulation.sigma_N_per_m)[order],
            color="tab:red",
            linewidth=1.8,
            label="Model (Ward-Tordai)",
            zorder=2,
        )

    ax.set_xscale("log")
    ax.set_xlabel("Surface age, t (s)")
    ax.set_ylabel(r"Surface tension, $\sigma$ (mN/m)")
    if title:
        ax.set_title(title)
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    return fig


def save_figure_png(fig: Figure, path: str, dpi: int = 150) -> None:
    fig.savefig(path, dpi=dpi, format="png")
