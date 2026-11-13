"""
Baseline vs ring protocol, one figure per swept input, from results/<camera>/<param>{,_ring,_ring_only}.json.
Writes to figures/.

    python plot_compare.py                                   # DG2, misalignment and E0
    python plot_compare.py --camera DG3_YAG --params misalignment
"""
import argparse
import json
import os
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

HERE = Path(__file__).resolve().parent
TOLERANCE_UM = 10
BEFORE, BASELINE, RING, RING_ONLY = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6"  # reference palette slots 1-3, 7
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
AXES = {"misalignment": ("lens misalignment (µm)", lambda v: v * 1e6, 50),
        "E0": ("photon energy E0 (keV)", lambda v: v / 1e3, 9.5),
        "seed": ("seed (hidden offsets)", lambda v: v, 3),
        "N": ("wavefront grid N", lambda v: v, 256)}


def medians(path, tx):
    if not os.path.exists(path):
        return None
    runs = json.load(open(path))
    xs = sorted({r["value"] for r in runs})
    pick = lambda key: np.array([np.median([r[key] for r in runs if r["value"] == v]) for v in xs])  # noqa: E731
    return np.array([tx(v) for v in xs]), pick("before_um"), pick("after_um")


parser = argparse.ArgumentParser(description="Plot baseline vs ring protocol sweeps.")
parser.add_argument("--camera", default="DG2_YAG")
parser.add_argument("--params", nargs="+", default=["misalignment", "E0"], choices=list(AXES))
args = parser.parse_args()
short = args.camera.split("_")[0]

for param in args.params:
    xlabel, tx, base = AXES[param]
    baseline = medians(HERE / "results" / args.camera / f"{param}.json", tx)
    ring = medians(HERE / "results" / args.camera / f"{param}_ring.json", tx)
    ring_only = medians(HERE / "results" / args.camera / f"{param}_ring_only.json", tx)  # ablation, optional
    if baseline is None or ring is None:
        print(f"skip {param}: missing results")
        continue
    fig, ax = plt.subplots(figsize=(10, 5.6), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.plot(baseline[0], baseline[1], "--", color=BEFORE, lw=2, marker="o", ms=8, mfc="white", mew=2,
            label="before (start)")
    ax.plot(baseline[0], baseline[2], "-", color=BASELINE, lw=2, marker="o", ms=8, mec="white",
            label="after baseline (centroid)")
    ax.plot(ring[0], ring[2], "-", color=RING, lw=2, marker="s", ms=8, mec="white", label="after ring method")
    if ring_only is not None:
        ax.plot(ring_only[0], ring_only[2], "-.", color=RING_ONLY, lw=2, marker="^", ms=9, mec="white",
                label="after ring only (no centroid finish)")
    ax.axhline(TOLERANCE_UM, color=INK2, lw=1, ls=":", label=f"{TOLERANCE_UM} µm tolerance")
    ax.axvline(base, color=INK2, lw=0.8, alpha=0.5, label="base point")
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(ticker.FixedLocator([0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500,
                                                    1000, 2000, 5000]))
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_formatter(ticker.NullFormatter())
    ax.set_xlabel(xlabel, color=INK2)
    ax.set_ylabel("worst lens offset (µm)", color=INK2)
    ax.grid(color=GRID, lw=0.8)
    ax.tick_params(colors=INK2)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    fig.suptitle(f"Ring method vs baseline: vary {param}, {short} camera", color=INK, fontsize=16,
                 fontweight="bold", x=0.02, ha="left")
    fig.text(0.02, 0.01, "Base point DigitalTwin(9500, N=256, misalignment=5e-5, seed=3), only this input varied; "
             "median of 3 camera-noise repeats.", color=INK2, fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    out = HERE / "figures" / f"compare_{short}_{param}.png"
    fig.savefig(out, dpi=110, facecolor=SURFACE)
    print(f"saved {out}")
