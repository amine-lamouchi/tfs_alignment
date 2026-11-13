"""
The steps of find_ring on one DG2 image (only tfs_06 in, moved +150 um), for protocols/README.md:
camera image, closing, closing - image, ring pixels + fitted circle, and a lineout through the ring.
Uses the same steps and default parameters as protocols/center_rings.find_ring.

    python show_ring_steps.py      # writes figures/ring_detection_steps.png (~2 s)
"""
import contextlib
import io
import logging
from pathlib import Path

logging.getLogger("tfs").setLevel(logging.CRITICAL)

import matplotlib.pyplot as plt
import numpy as np
from scipy import ndimage

from protocols.center_rings import find_ring
from tfs_twin import DigitalTwin, SimCamera

HERE = Path(__file__).resolve().parent
LINE_WIDTH, CONTRAST = 9, 0.3  # find_ring defaults

twin = DigitalTwin(9500, N=256, misalignment=0)
tfs = twin.tfs
with contextlib.redirect_stdout(io.StringIO()):
    tfs.focus_at(energy_eV=9500, wait=True)
for lens in tfs.tfs_lenses:  # only tfs_06 in, as when the protocol centers it
    if lens.inserted and twin._name(lens) != "tfs_06":
        lens.remove(wait=True)
tfs.tfs_06.x.mv(0.15)
with np.errstate(all="ignore"):
    image = SimCamera(twin, "DG2_YAG", noise=True, seed=0).get_image()

# the steps of find_ring
smooth = ndimage.gaussian_filter(image, 1.0)
closed = ndimage.grey_closing(smooth, size=LINE_WIDTH)
inside = closed > 0.1 * closed.max()
filled = closed - smooth
mask = inside & (filled > CONTRAST * closed)
ring = find_ring(image)

fig = plt.figure(figsize=(14, 8.6), facecolor="#fcfcfb")
grid = fig.add_gridspec(2, 4, height_ratios=[1, 0.75])
panels = [
    (smooth, "1. camera image (lightly smoothed)", "gnuplot"),
    (closed, "2. closing: thin dark lines filled in", "gnuplot"),
    (filled, "3. closing − image: bright only on the ring", "magma"),
]
row = image.shape[0] // 2
for k, (data, title, cmap) in enumerate(panels):
    ax = fig.add_subplot(grid[0, k])
    ax.imshow(data, cmap=cmap)
    ax.axhline(row, color="white", lw=0.8, ls="--")
    ax.set_title(title, fontsize=10)
    ax.axis("off")
ax = fig.add_subplot(grid[0, 3])
ax.imshow(smooth, cmap="gray")
ys, xs = np.nonzero(mask)
ax.plot(xs, ys, ",", color="#1baf7a")
ax.add_patch(plt.Circle(ring[:2], ring[2], fill=False, color="#eb6834", lw=2))
ax.plot(*ring[:2], "+", color="#eb6834", ms=14, mew=2.5)
ax.set_title(f"4. ring pixels (green) + fitted circle\ncentre ({ring[0]:.0f}, {ring[1]:.0f}) px, radius {ring[2]:.0f} px",
             fontsize=10)
ax.set_xlim(0, image.shape[1])
ax.set_ylim(image.shape[0], 0)
ax.axis("off")

ax = fig.add_subplot(grid[1, :])
x = np.arange(image.shape[1])
ax.plot(x, smooth[row], color="#2a78d6", lw=2, label="camera image (step 1)")
ax.plot(x, closed[row], color="#eb6834", lw=2, ls="--", label="after closing (step 2)")
dips = mask[row]
ax.fill_between(x, smooth[row], closed[row], where=dips, color="#1baf7a", alpha=0.5,
                label=f"kept as ring: filled in by > {CONTRAST:.0%} (step 3)")
ax.set_xlabel("pixel along the dashed line")
ax.set_ylabel("counts")
ax.set_title("Along the dashed line: the ring's dip is filled in; the beam's outer edges (left and right) are not",
             fontsize=10, loc="left")
ax.legend(frameon=False, fontsize=9, loc="upper right")
ax.grid(color="#e4e3df", lw=0.8)
for spine in ax.spines.values():
    spine.set_color("#e4e3df")

fig.suptitle("How find_ring detects the aperture ring", fontsize=15, fontweight="bold", x=0.02, ha="left")
fig.text(0.02, 0.01, "DG2, only tfs_06 in and moved +150 µm, 9.5 keV, camera noise on. Same steps and parameters "
         "as protocols/center_rings.find_ring.", fontsize=8.5, color="#52514e")
fig.tight_layout(rect=(0, 0.03, 1, 0.95))
fig.savefig(HERE / "figures" / "ring_detection_steps.png", dpi=90, facecolor=fig.get_facecolor())
print("saved figures/ring_detection_steps.png;", f"{mask.sum()} ring pixels, circle {np.round(ring, 1)}")
