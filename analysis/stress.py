"""
Stress tests of the baseline protocol on the DG3 camera: where does each lens end up?

Base twin DigitalTwin(9500, N=256, misalignment=5e-5, seed=3). Each case adds one stress around the
unchanged protocol with a wrapper camera: beam moved on the reference image, shot-to-shot beam
jitter, large misalignment, rotated camera, low light. Prints worst lens offset before -> after.

    python stress.py          # all cases (~1-2 min)
    python stress.py 1 5      # only cases 1 and 5
"""
import logging
import sys
import time

logging.getLogger("tfs").setLevel(logging.CRITICAL)

import numpy as np
from scipy import ndimage

from protocols.center_lenses import center_lenses
from tfs_twin import DigitalTwin, SimCamera

IMAGES_PER_LENS = 13  # 1 reference (lens out) + 2 per iteration x 3 iterations x 2 axes


def make_twin(misalignment=50e-6):
    twin = DigitalTwin(9500, N=256, misalignment=misalignment, seed=3)
    twin.tfs.focus_at(energy_eV=9500, wait=True)
    return twin


def beam_shift_per_urad():
    """Beam shift on DG1 (just before the TFS) per microradian of pointing."""
    twin = make_twin()
    with np.errstate(all="ignore"):
        twin.propagate()
        x0 = twin.beamline.DG1_YAG.cx
        twin.mfx_sim.undulator_pointing(1e-6, 0)
        twin.propagate()
        x1 = twin.beamline.DG1_YAG.cx
    return (x1 - x0) * 1e6


class StressCamera:
    """SimCamera plus a hook run before each image and an optional image transform."""

    def __init__(self, twin, before=None, transform=None, light=1.0):
        self.camera = SimCamera(twin, "DG3_YAG", noise=True, seed=1)
        self.twin, self.before, self.transform, self.n = twin, before, transform, 0
        if light != 1.0:
            self.camera.get_image()
            self.camera.scale *= light
        self.light = light

    def get_image(self):
        if self.before:
            self.before(self.twin, self.n)
        with np.errstate(all="ignore"):
            image = self.camera.get_image()
        self.twin.mfx_sim.undulator_pointing(0, 0)  # beam back on axis for grading
        self.n += 1
        return self.transform(image) if self.transform else image


def run(label, misalignment=50e-6, **camera_kwargs):
    twin = make_twin(misalignment)
    tfs = twin.tfs
    lenses = [lens for lens in tfs.tfs_lenses if lens.inserted]
    names = [twin._name(lens) for lens in lenses]
    before = {n: twin.lens_offsets()[n] for n in names}
    start = {n: (getattr(tfs, n).x.position, getattr(tfs, n).y.position) for n in names}
    camera = StressCamera(twin, **camera_kwargs)
    t0 = time.time()
    try:
        center_lenses(tfs, camera, lenses=lenses, verbose=False)
        error = ""
    except Exception as exc:  # noqa: BLE001
        error = f"  CRASH: {exc!r}"[:80]
    after = twin.lens_offsets()
    worst_before = max(np.hypot(*before[n]) for n in names) * 1e6
    worst_after = max(np.hypot(*after[n]) for n in names) * 1e6
    biggest_move = max(max(abs(getattr(tfs, n).x.position - start[n][0]), abs(getattr(tfs, n).y.position - start[n][1]))
                       for n in names) * 1e3
    print(f"{label:34s} worst offset {worst_before:6.1f} -> {worst_after:8.1f} um   "
          f"biggest move {biggest_move:8.1f} um   ({time.time() - t0:.0f} s){error}", flush=True)
    for n in names:
        (bx, by), (ax_, ay_) = before[n], after[n]
        print(f"    {n}: dx {bx * 1e6:+7.1f} -> {ax_ * 1e6:+8.1f} um   dy {by * 1e6:+7.1f} -> {ay_ * 1e6:+8.1f} um",
              flush=True)


k = beam_shift_per_urad()
jitter_urad = abs(30 / k)  # pointing that moves the beam ~30 um at the TFS
print(f"pointing: {k:.0f} um at DG1 per urad -> using {jitter_urad:.3f} urad for ~30 um\n", flush=True)
rng = np.random.default_rng(0)


def reference_jump(twin, n):
    if n % IMAGES_PER_LENS == 0:  # only the lens-out reference image
        twin.mfx_sim.undulator_pointing(jitter_urad * 1e-6, jitter_urad * 1e-6)


def shot_jitter(twin, n):
    ax, ay = rng.normal(0, jitter_urad * 1e-6, 2)
    twin.mfx_sim.undulator_pointing(ax, ay)


cases = {
    "0": lambda: run("0. baseline (as in the notebook)"),
    "1": lambda: run("1. beam moved 30 um on reference shot", before=reference_jump),
    "2": lambda: run("2. shot-to-shot jitter, 30 um rms", before=shot_jitter),
    "3": lambda: run("3. large misalignment (+-300 um)", misalignment=300e-6),
    "4": lambda: run("4. camera rotated 30 deg", transform=lambda im: ndimage.rotate(im, 30, reshape=False, order=1)),
    "5": lambda: run("5. camera rotated 90 deg", transform=np.rot90),
    "6": lambda: run("6. low light (peak ~40 counts)", light=0.01),
    "7": lambda: run("7. large misalignment (+-500 um)", misalignment=5e-4),
}
for key in sys.argv[1:] or cases:
    cases[key]()
