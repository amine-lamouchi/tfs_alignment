"""
Ring protocol: center each TFS lens on the beam using the shadow of its aperture.

Part of the beam passes outside a lens's aperture and is not focused by it, so the
aperture edge casts a thin dark ring on a downstream YAG. The ring is the shadow of
the lens: its center moves with the lens motors, even when the lens is so far off
that the beam centroid hardly moves (where center_lenses fails). With only that
lens in, the lens is centered when its ring is centered on the beam axis:
1. remove the lens, record the centroid (the beam axis), as in center_lenses;
2. insert it, find the ring, step each motor once to measure ring shift vs motor;
3. move so the ring center lands on the axis (moves capped); repeat.
With no ring (the beam fits inside the aperture) it says so and leaves the lens
for center_lenses.

Only uses `tfs` and the camera's images. Assumes camera x/y are aligned with
motor x/y, and that the ring (or part of it) is on the camera to start with.
"""
import numpy as np
from scipy import ndimage

from protocols.center_lenses import centroid
from protocols.motion import fresh_image, insert, move, put_back, readback, remove, remove_others


def find_ring(image, line_width=9, contrast=0.3, min_pixels=40):
    """
    Circle (col, row, radius) fitted to the thin dark ring in `image`, in pixels,
    or None if there is no ring. A morphological closing fills dark lines thinner
    than `line_width` pixels but leaves the beam's outer edge alone, so
    closing - image picks out the ring and not the edge of the beam.
    """
    smooth = ndimage.gaussian_filter(image.astype(float), 1.0)  # tame shot noise
    closed = ndimage.grey_closing(smooth, size=line_width)
    inside = closed > 0.1 * closed.max()  # only where there is beam around
    ring = inside & (closed - smooth > contrast * closed)
    rows, cols = np.nonzero(ring)
    if len(rows) < min_pixels:
        return None
    # algebraic circle fit: x^2 + y^2 + D x + E y + F = 0
    A = np.column_stack([cols, rows, np.ones_like(cols)])
    b = -(cols.astype(float) ** 2 + rows.astype(float) ** 2)
    (D, E, F), *_ = np.linalg.lstsq(A, b, rcond=None)
    c, r = -D / 2, -E / 2
    radius = np.sqrt(max(c ** 2 + r ** 2 - F, 0))
    return np.array([c, r, radius])


def center_lens_ring(tfs, lens, camera, step=0.05, max_move=0.2, iterations=6, tolerance_px=1.0, verbose=True):
    """
    Center `lens` (e.g. tfs.tfs_06) on the beam with its aperture ring. Steps and
    moves in motor units (mm).
    """
    others = remove_others(tfs, lens)

    remove(lens)
    axis = centroid(fresh_image(camera))
    insert(lens)
    motors = [lens.x, lens.y]

    ring = find_ring(fresh_image(camera))
    if ring is None and verbose:
        print(f"{lens.name}: no ring, left as it is")
    if ring is not None:
        gains = []
        for i, motor in enumerate(motors):  # ring shift (pixels) per mm, one step per axis
            start = readback(motor)
            move(motor, start + step)
            moved = readback(motor) - start
            shifted = find_ring(fresh_image(camera))
            move(motor, start)
            gains.append((shifted[i] - ring[i]) / moved if shifted is not None else None)
        if verbose:
            print(f"{lens.name}: ring found, gain {gains} px/mm")
        for _ in range(iterations):
            if ring is None or None in gains or 0 in gains:
                break
            error = axis - ring[:2]
            if np.all(np.abs(error) < tolerance_px):
                break
            for i, motor in enumerate(motors):
                step_to_axis = np.clip(error[i] / gains[i], -max_move, max_move)
                move(motor, readback(motor) + step_to_axis)
            ring = find_ring(fresh_image(camera))
        if verbose:
            print(f"{lens.name}: x {readback(lens.x):.4f}, y {readback(lens.y):.4f}")

    put_back(others)


def center_lenses_ring(tfs, camera, lenses=None, **kwargs):
    """Center every lens in `lenses` (default: all TFS lenses) with center_lens_ring."""
    for lens in lenses or tfs.tfs_lenses:
        center_lens_ring(tfs, lens, camera, **kwargs)
