"""
Does find_ring find the ring? One lens in at a time (aligned twin), moved 0..450 um in x, DG2 camera
with noise. Draws the fitted circle on each image.

    python show_find_ring.py      # writes figures/ring_detection_DG2.png (~10 s)
"""
import contextlib
import io
import logging
from pathlib import Path

logging.getLogger("tfs").setLevel(logging.CRITICAL)

import matplotlib.pyplot as plt
import numpy as np

from protocols.center_rings import find_ring
from tfs_twin import DigitalTwin, SimCamera

HERE = Path(__file__).resolve().parent
OFFSETS_UM = [0, 150, 300, 450]

twin = DigitalTwin(9500, N=256, misalignment=0)
tfs = twin.tfs
with contextlib.redirect_stdout(io.StringIO()):
    tfs.focus_at(energy_eV=9500, wait=True)
names = [twin._name(lens) for lens in tfs.tfs_lenses if lens.inserted]
for name in names:
    getattr(tfs, name).remove(wait=True)

fig, axes = plt.subplots(len(names), len(OFFSETS_UM), figsize=(3.6 * len(OFFSETS_UM), 3.8 * len(names)),
                         facecolor="#fcfcfb")
for row, name in zip(axes, names):
    lens = getattr(tfs, name)
    lens.insert(wait=True)
    camera = SimCamera(twin, "DG2_YAG", noise=True, seed=0)
    for ax, offset in zip(row, OFFSETS_UM):
        lens.x.mv(offset * 1e-3)
        with np.errstate(all="ignore"):
            image = camera.get_image()
        ring = find_ring(image)
        ax.imshow(image, cmap="gnuplot")
        label = "no ring"
        if ring is not None:
            ax.add_patch(plt.Circle(ring[:2], ring[2], fill=False, color="lime", lw=1.5))
            ax.plot(*ring[:2], "+", color="lime", ms=12, mew=2)
            label = f"ring centre x = {ring[0]:.0f} px"
        ax.set_xlim(0, image.shape[1])
        ax.set_ylim(image.shape[0], 0)
        ax.set_title(f"{name}, x {offset:+d} µm: {label}", fontsize=9)
        ax.axis("off")
        print(f"{name} x {offset:+4d} um: {label}")
    lens.x.mv(0)
    lens.remove(wait=True)
fig.suptitle("Ring detection on DG2: one lens in, moved in x", fontsize=14, fontweight="bold", x=0.02, ha="left")
fig.text(0.02, 0.005, "Green: circle fitted by find_ring (protocols/center_rings.py). Aligned twin, 9.5 keV, "
         "camera noise on. tfs_02's opening (1400 µm) is larger than the beam, so its ring only appears far off.",
         fontsize=8, color="#52514e")
fig.tight_layout(rect=(0, 0.02, 1, 0.96))
fig.savefig(HERE / "figures" / "ring_detection_DG2.png", dpi=70, facecolor=fig.get_facecolor())
print("saved figures/ring_detection_DG2.png")
