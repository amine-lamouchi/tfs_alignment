"""
Baseline protocol: center each TFS lens on the beam, one lens at a time.

A decentered lens steers the beam like a prism. With only that lens in, the
beam centroid on a downstream YAG moves linearly with the lens x/y motor:
1. remove the lens, record the centroid (the beam axis);
2. insert it, step the motor to measure centroid vs motor;
3. move to where the centroid is back on the axis; repeat.

Only uses `tfs` and `camera.get_image()`, so it runs the same on the twin and
on the real instrument (with a gigE_camera_accessor). Assumes camera x/y are
aligned with motor x/y.
"""
import numpy as np


def centroid(image, threshold=0.1):
    """Centroid (col, row) in pixels, after background subtraction and threshold."""
    image = image - np.median(image)
    image[image < threshold * image.max()] = 0
    rows, cols = np.indices(image.shape)
    return np.array([(cols * image).sum(), (rows * image).sum()]) / image.sum()


def center_lens(tfs, lens, camera, step=0.02, iterations=3, verbose=True):
    """Center `lens` (e.g. tfs.tfs_05) on the beam. `step` in motor units (mm)."""
    others = [other for other in tfs.tfs_lenses if other.inserted and other is not lens]
    for other in others:
        other.remove(wait=True)

    lens.remove(wait=True)
    axis = centroid(camera.get_image())
    lens.insert(wait=True)

    for i, motor in enumerate([lens.x, lens.y]):
        for _ in range(iterations):
            start = motor.position
            c0 = centroid(camera.get_image())[i]
            motor.mv(start + step)
            c1 = centroid(camera.get_image())[i]
            gain = (c1 - c0) / step  # pixels per mm
            motor.mv(start + (axis[i] - c0) / gain)
        if verbose:
            print(f"{motor.name}: {motor.position:.4f}")

    for other in others:
        other.insert(wait=True)


def center_lenses(tfs, camera, lenses=None, **kwargs):
    """Center every lens in `lenses` (default: all TFS lenses)."""
    for lens in lenses or tfs.tfs_lenses:
        center_lens(tfs, lens, camera, **kwargs)
