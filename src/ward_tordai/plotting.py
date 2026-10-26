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
    experimental_label: str = "Experimental",
    model_label: str = "Model (Ward-Tordai)",
) -> Figure:
    """Plot measured sigma(t) as points and predicted sigma(t) as a curve.

    X-axis is logarithmic surface age (time); Y-axis is surface tension in
    mN/m, matching the SITA DynoTester's native reporting units.
    """
    fig = Figure(figsize=(7.0, 5.0), dpi=120)
    fig.patch.set_facecolor("white")
    ax = fig.add_subplot(111)
    ax.set_facecolor("white")

    ax.scatter(
        data.time_s,
        N_per_m_to_mN_per_m(data.sigma_N_per_m),
        s=22,
        color="tab:blue",
        label=experimental_label or "_nolegend_",
        zorder=3,
    )

    if simulation is not None and simulation.converged:
        order = np.argsort(simulation.time_s)
        ax.plot(
            simulation.time_s[order],
            N_per_m_to_mN_per_m(simulation.sigma_N_per_m)[order],
            color="tab:red",
            linewidth=1.8,
            label=model_label or "_nolegend_",
            zorder=2,
        )

    ax.set_xscale("log")
    ax.set_xlabel("Surface age, t (s)")
    ax.set_ylabel(r"Surface tension, $\sigma$ (mN/m)")
    if title:
        ax.set_title(title)
    ax.grid(True, which="both", alpha=0.3)
    handles, labels = ax.get_legend_handles_labels()
    if labels:
        ax.legend(handles, labels, loc="best")
    fig.tight_layout()
    return fig


def save_figure_png(fig: Figure, path: str, dpi: int = 330) -> None:
    fig.savefig(
        path,
        dpi=dpi,
        format="png",
        facecolor="white",
        edgecolor="white",
        transparent=False,
    )
