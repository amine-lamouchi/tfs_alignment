"""
Ablation of find_ring's ring-pixel step, on DG2 images of one lens at a time moved 0..450 um in x:

  current  closing (max then min, 9x9) - image     ring = filled in by > 30 %
  A        max (9x9) - image                         ring = raised by > 30 %
  B        max (9x9) - min (9x9) of the image        ring = range > 30 % of the max

Same smoothing, beam mask, minimum pixel count and circle fit for all three. A good detector gives a
ring centre that moves in a straight line with the lens, starts at the beam centre (~128 px) when the lens
is centered, and a constant radius.

    python ablation_find_ring.py      # prints the table, writes figures/ablation_find_ring.png (~15 s)
"""
import contextlib
import io
import logging
from pathlib import Path

logging.getLogger("tfs").setLevel(logging.CRITICAL)

import matplotlib.pyplot as plt
import numpy as np
from scipy import ndimage

from tfs_twin import DigitalTwin, SimCamera

HERE = Path(__file__).resolve().parent
OFFSETS_UM = [0, 75, 150, 225, 300, 375, 450]
SIZE, CONTRAST, MIN_PIXELS = 9, 0.3, 40  # find_ring defaults


def ring_pixels(image, variant):
    smooth = ndimage.gaussian_filter(image.astype(float), 1.0)
    brightest = ndimage.grey_dilation(smooth, size=SIZE)  # image 2
    if variant == "current":
        reference = ndimage.grey_erosion(brightest, size=SIZE)  # image 3 (= grey_closing)
        difference = reference - smooth
    elif variant == "A":
        reference = brightest
        difference = brightest - smooth
    else:  # B
        reference = brightest
        difference = brightest - ndimage.grey_erosion(smooth, size=SIZE)
    inside = reference > 0.1 * reference.max()
    return inside & (difference > CONTRAST * reference)


def fit_circle(mask):
    rows, cols = np.nonzero(mask)
    if len(rows) < MIN_PIXELS:
        return None
    A = np.column_stack([cols, rows, np.ones_like(cols)])
    b = -(cols.astype(float) ** 2 + rows.astype(float) ** 2)
    (D, E, F), *_ = np.linalg.lstsq(A, b, rcond=None)
    c, r = -D / 2, -E / 2
    return np.array([c, r, np.sqrt(max(c ** 2 + r ** 2 - F, 0))])


twin = DigitalTwin(9500, N=256, misalignment=0)
tfs = twin.tfs
with contextlib.redirect_stdout(io.StringIO()):
    tfs.focus_at(energy_eV=9500, wait=True)
names = [twin._name(lens) for lens in tfs.tfs_lenses if lens.inserted]
for name in names:
    getattr(tfs, name).remove(wait=True)

images = {}
for name in names:
    lens = getattr(tfs, name)
    lens.insert(wait=True)
    camera = SimCamera(twin, "DG2_YAG", noise=True, seed=0)
    for offset in OFFSETS_UM:
        lens.x.mv(offset * 1e-3)
        with np.errstate(all="ignore"):
            images[name, offset] = camera.get_image()
    lens.x.mv(0)
    lens.remove(wait=True)

VARIANTS = ["current", "A", "B"]
print(f"{'variant':8s} {'lens':7s} {'found':>6s} {'centre at 0':>12s} {'slope px/um':>12s} "
      f"{'line fit rms px':>16s} {'radius px (min-max)':>20s}")
for variant in VARIANTS:
    for name in names:
        fits = {off: fit_circle(ring_pixels(images[name, off], variant)) for off in OFFSETS_UM}
        found = [off for off, f in fits.items() if f is not None]
        if len(found) < 2:
            print(f"{variant:8s} {name:7s} {len(found):>3d}/{len(OFFSETS_UM)}")
            continue
        x = np.array(found, float)
        c = np.array([fits[o][0] for o in found])
        radii = np.array([fits[o][2] for o in found])
        slope, intercept = np.polyfit(x, c, 1)
        rms = np.sqrt(np.mean((c - (slope * x + intercept)) ** 2))
        at0 = f"{fits[0][0]:.1f}" if fits[0] is not None else "-"
        print(f"{variant:8s} {name:7s} {len(found):>3d}/{len(OFFSETS_UM)} {at0:>12s} {slope:>12.3f} "
              f"{rms:>16.1f} {radii.min():>9.0f}-{radii.max():<9.0f}")

# figure: rows = variants, columns = tfs_06 at 0, 150, 300 um and tfs_09 at 300 um
examples = [("tfs_06", 0), ("tfs_06", 150), ("tfs_06", 300), ("tfs_09", 300)]
fig, axes = plt.subplots(len(VARIANTS), len(examples), figsize=(3.6 * len(examples), 3.8 * len(VARIANTS)),
                         facecolor="#fcfcfb")
labels = {"current": "current: closing − image", "A": "A: max − image", "B": "B: max − min"}
for row, variant in zip(axes, VARIANTS):
    for ax, (name, offset) in zip(row, examples):
        image = images[name, offset]
        mask = ring_pixels(image, variant)
        fit = fit_circle(mask)
        ax.imshow(ndimage.gaussian_filter(image, 1.0), cmap="gray")
        ys, xs = np.nonzero(mask)
        ax.plot(xs, ys, ",", color="#1baf7a")
        title = f"{labels[variant]}\n{name} x +{offset} µm: "
        if fit is not None:
            ax.add_patch(plt.Circle(fit[:2], fit[2], fill=False, color="#eb6834", lw=2))
            title += f"centre {fit[0]:.0f} px, r {fit[2]:.0f}"
        else:
            title += "no ring"
        ax.set_xlim(0, image.shape[1])
        ax.set_ylim(image.shape[0], 0)
        ax.set_title(title, fontsize=9)
        ax.axis("off")
fig.suptitle("Ablation of the ring detection: which pixels are kept (green) and the fitted circle (orange)",
             fontsize=13, fontweight="bold", x=0.02, ha="left")
fig.text(0.02, 0.005, "DG2, one lens in, 9.5 keV, camera noise on. Same smoothing, threshold (30 %), beam mask "
         "and circle fit for all three.", fontsize=8.5, color="#52514e")
fig.tight_layout(rect=(0, 0.02, 1, 0.96))
fig.savefig(HERE / "figures" / "ablation_find_ring.png", dpi=70, facecolor=fig.get_facecolor())
print("saved figures/ablation_find_ring.png")
