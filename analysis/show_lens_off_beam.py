"""
DG2 with tfs_06 moved 0, +500 and +1000 um in x (base twin of the sweeps): the lens's ring slides off
the beam while the beam centroid hardly moves, which is why the baseline cannot tell "centered" from
"out of the beam".

    python show_lens_off_beam.py      # writes figures/tfs06_x_0_500_1000um_DG2.png (~5 s)
"""
import contextlib
import io
import logging
from pathlib import Path

logging.getLogger("tfs").setLevel(logging.CRITICAL)

import matplotlib.pyplot as plt
import numpy as np

from tfs_twin import DigitalTwin
from tfs_twin.geometry import aperture

HERE = Path(__file__).resolve().parent

twin = DigitalTwin(9500, N=256, misalignment=5e-5, seed=3)
tfs = twin.tfs
with contextlib.redirect_stdout(io.StringIO()):
    tfs.focus_at(energy_eV=9500, wait=True)
print("tfs_06 aperture diameter:", round(aperture("tfs_06", tfs.tfs_06.radius) * 1e6), "um")

x0 = tfs.tfs_06.x.position
fig, axes = plt.subplots(1, 3, figsize=(15, 5.2), facecolor="#fcfcfb")
for ax, shift in zip(axes, [0, 500, 1000]):
    tfs.tfs_06.x.mv(x0 + shift * 1e-3)
    with np.errstate(all="ignore"):
        twin.propagate()
    ppm = twin.beamline.DG2_YAG
    extent = np.array([ppm.x.min(), ppm.x.max(), ppm.y.min(), ppm.y.max()]) * 1e6
    ax.imshow(np.flipud(ppm.profile), extent=extent, cmap="gnuplot")
    dx = twin.lens_offsets()["tfs_06"][0] * 1e6
    ax.set_title(f"tfs_06 moved {shift:+d} µm (true dx {dx:+.0f} µm)", fontsize=11)
    ax.set_xticks([-500, -250, 0, 250, 500])
    ax.set_yticks([-500, -250, 0, 250, 500])
    ax.set_xlabel("x on DG2 (µm)")
    ax.set_ylabel("y on DG2 (µm)")
    print(f"shift {shift:+5d} um: DG2 centroid x {ppm.cx * 1e6:+7.1f} um, total intensity {ppm.profile.sum():.3g}")
tfs.tfs_06.x.mv(x0)
fig.suptitle("DG2 as tfs_06 is moved off the beam in x (9.5 keV, tfs_02 and tfs_09 also in)", fontsize=13,
             fontweight="bold", x=0.02, ha="left")
fig.tight_layout(rect=(0, 0, 1, 0.93))
fig.savefig(HERE / "figures" / "tfs06_x_0_500_1000um_DG2.png", dpi=90, facecolor=fig.get_facecolor(),
            bbox_inches="tight")
print("saved figures/tfs06_x_0_500_1000um_DG2.png")
