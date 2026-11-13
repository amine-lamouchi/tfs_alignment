"""
Plot results/<camera>/<param>.json (baseline runs of sweep.py): one panel per swept input,
worst lens offset before and after the baseline protocol, crashes marked. Writes to figures/.

    python plot_sweep.py                                   # DG2_YAG, all 4 inputs: sweep_baseline_DG2.png
    python plot_sweep.py --camera DG3_YAG                  # sweep_baseline_DG3.png
    python plot_sweep.py --params misalignment             # one input: sweep_baseline_DG2_misalignment.png
"""
import argparse
import json
import os
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

HERE = Path(__file__).resolve().parent
TOLERANCE_UM = 10  # "works" if every lens ends within this
BEFORE, AFTER, CRASH = "#2a78d6", "#eb6834", "#d03b3b"  # reference palette slots 1-2, status critical
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

PANELS = [  # param, x label, x transform
    ("misalignment", "lens misalignment (µm)", lambda v: v * 1e6),
    ("E0", "photon energy E0 (keV)", lambda v: v / 1e3),
    ("seed", "seed (hidden offsets)", lambda v: v),
    ("N", "wavefront grid N", lambda v: v),
]
BASE = {"misalignment": 50, "E0": 9.5, "seed": 3, "N": 256}  # base point, in plotted units
XMIN = {"N": 96}  # smallest swept value to plot (raw units)
UNIT = {"misalignment": " µm", "E0": " keV", "seed": "", "N": ""}  # for panel titles


def load(param):
    path = HERE / "results" / CAMERA / f"{param}.json"
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def panel(ax, param, xlabel, tx):
    runs = [r for r in load(param) if r["value"] >= XMIN.get(param, -np.inf)]
    ax.set_title(f"vary {param} (others fixed)", color=INK, fontsize=11, loc="left")
    if not runs:
        ax.text(0.5, 0.5, "no results yet", ha="center", transform=ax.transAxes, color=INK2)
        return
    xs = sorted({r["value"] for r in runs})
    x = np.array([tx(v) for v in xs])
    before = np.array([np.median([r["before_um"] for r in runs if r["value"] == v]) for v in xs])
    after = np.array([np.median([r["after_um"] for r in runs if r["value"] == v]) for v in xs])

    crashed = np.array([np.mean([r["crash"] is not None for r in runs if r["value"] == v]) > 0.5 for v in xs])

    ax.plot(x, before, "--", color=BEFORE, lw=2, marker="o", ms=8, mfc="white", mew=2, label="before (start)")
    ax.plot(x, after, "-", color=AFTER, lw=2, marker="o", ms=8, mec="white", label="after baseline (median)")
    ax.plot(x[crashed], after[crashed], "x", ms=11, color=CRASH, mew=2.5, zorder=3)  # most runs crashed
    if param == "N":
        ax.set_xscale("log", base=2)
        ax.xaxis.set_major_locator(ticker.FixedLocator(x))
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.xaxis.set_minor_locator(ticker.NullLocator())
    ax.axhline(TOLERANCE_UM, color=INK2, lw=1, ls=":")
    ax.text(x.min(), TOLERANCE_UM * 1.15, f"{TOLERANCE_UM} µm tolerance", color=INK2, fontsize=8, va="bottom")

    failing = [tx(v) for v in xs if any(r["after_um"] > TOLERANCE_UM for r in runs if r["value"] == v)]
    if param == "misalignment" and failing:
        first = min(failing)
        ok = [xi for xi in x if xi < first]
        edge = (max(ok) + first) / 2 if ok else first
        ax.axvspan(edge, x.max() * 1.05, color=CRASH, alpha=0.06, lw=0)
        verdict = f"breaks between {max(ok):.0f} and {first:.0f} µm" if ok else f"breaks at {first:.0f} µm"
    elif failing:
        verdict = "fails at " + ", ".join(f"{f:g}" for f in failing) + UNIT[param]
    else:
        verdict = "never fails"
    ax.set_title(f"vary {param} (others fixed): {verdict}", color=INK, fontsize=11, loc="left")
    ax.axvline(BASE[param], color=INK2, lw=0.8, alpha=0.5)
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(ticker.FixedLocator([0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500,
                                                    1000, 2000, 5000, 10000]))
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_formatter(ticker.NullFormatter())
    if param == "seed":
        ax.xaxis.set_major_locator(ticker.MultipleLocator(2))
    ax.set_xlabel(xlabel, color=INK2)
    ax.set_ylabel("worst lens offset (µm)", color=INK2)
    ax.grid(color=GRID, lw=0.8)
    ax.tick_params(colors=INK2)
    for spine in ax.spines.values():
        spine.set_color(GRID)


names = [p for p, _, _ in PANELS]
parser = argparse.ArgumentParser(description="Plot the baseline parameter sweeps.")
parser.add_argument("--camera", default="DG2_YAG", help="camera the sweeps used (default DG2_YAG)")
parser.add_argument("--params", nargs="+", default=names, choices=names,
                    help="panels to plot, in order: all 4 -> 2x2 grid, fewer -> one column")
args = parser.parse_args()
CAMERA = args.camera
SHORT = CAMERA.split("_")[0]  # DG2_YAG -> DG2
panels = [next(p for p in PANELS if p[0] == name) for name in args.params]
grid = len(panels) == 4

if grid:
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), facecolor="#fcfcfb")
else:
    fig, axes = plt.subplots(len(panels), 1, figsize=(10, 4.3 * len(panels) + 1.4), facecolor="#fcfcfb")
for ax, (param, xlabel, tx) in zip(np.atleast_1d(axes).flat, panels):
    ax.set_facecolor("#fcfcfb")
    panel(ax, param, xlabel, tx)
handles = [
    plt.Line2D([], [], color=BEFORE, ls="--", lw=2, marker="o", mfc="white", mew=2, ms=8, label="before (start)"),
    plt.Line2D([], [], color=AFTER, lw=2, marker="o", mec="white", ms=8, label="after baseline (median of noise repeats)"),
    plt.Line2D([], [], color=CRASH, ls="", marker="x", mew=2.5, ms=11, label="crash (most runs raised an error)"),
    plt.Line2D([], [], color=INK2, ls=":", lw=1, label=f"{TOLERANCE_UM} µm tolerance"),
    plt.Line2D([], [], color=INK2, lw=0.8, alpha=0.5, label="base point"),
]
height = fig.get_figheight()  # one column: fixed margins in inches, so 1 or 2 panels both fit
fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.03 if grid else 0.42 / height),
           ncol=5 if grid else 3, frameon=False, fontsize=9)
fig.suptitle(f"Baseline lens centering: parameter sweep, {SHORT} camera", color=INK, fontsize=17,
             fontweight="bold", x=0.02, ha="left")
fig.text(0.02, 0.01 if grid else 0.06 / height,
         "Base point DigitalTwin(9500, N=256, misalignment=5e-5, seed=3), one input varied per panel."
         + (" " if grid else "\n")
         + f"center_lenses with the camera on {SHORT}; worst lens offset before vs after.", color=INK2, fontsize=9)
fig.tight_layout(rect=(0, 0.07, 1, 0.95) if grid else (0, 1.1 / height, 1, 1 - 0.55 / height))
name = f"sweep_baseline_{SHORT}.png" if grid else f"sweep_baseline_{SHORT}_{'_'.join(args.params)}.png"
out = HERE / "figures" / name
fig.savefig(out, dpi=110, facecolor=fig.get_facecolor())
print(f"saved {out}")
