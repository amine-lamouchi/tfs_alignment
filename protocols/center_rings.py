"""
Ring protocol: center each TFS lens on the beam using the shadow of its aperture.

Part of the beam passes outside a lens's aperture and is not focused by it, so the
aperture edge casts a thin dark ring on a downstream YAG. The ring is the shadow of
the lens: its center moves with the lens motors, even when the lens is so far off
that the beam centroid hardly moves (where center_lenses fails). With only that
lens in, the lens is centered when its ring is centered on the beam axis:
1. remove the lens, record the centroid (the beam axis), as in center_lenses;
2. insert it, find the ring, step each motor once to measure ring shift vs motor;
3. move so the ring center lands on the axis (moves capped); repeat;
4. when no ring is left (the beam fits inside the aperture), finish with the
   centroid steps of center_lenses, with capped moves.

Only uses `tfs` and `camera.get_image()`. Assumes camera x/y are aligned with
motor x/y, and that the ring (or part of it) is on the camera to start with.
"""
import numpy as np
from scipy import ndimage

from protocols.center_lenses import centroid
from protocols.motion import move


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


def center_lens_ring(tfs, lens, camera, step=0.05, max_move=0.2, iterations=6, fine_iterations=4,
                     fine_step=0.02, max_fine_move=0.2, tolerance_px=1.0, verbose=True):
    """
    Center `lens` (e.g. tfs.tfs_06) on the beam with its aperture ring, then a
    few capped centroid steps. Steps and moves in motor units (mm).
    """
    others = [other for other in tfs.tfs_lenses if other.inserted and other is not lens]
    for other in others:
        other.remove(wait=True)

    lens.remove(wait=True)
    axis = centroid(camera.get_image())
    lens.insert(wait=True)
    motors = [lens.x, lens.y]

    # coarse: put the ring center on the axis
    ring = find_ring(camera.get_image())
    if ring is not None:
        gains = []
        for i, motor in enumerate(motors):  # ring shift (pixels) per mm, one step per axis
            start = motor.position
            move(motor, start + step)
            shifted = find_ring(camera.get_image())
            move(motor, start)
            gains.append((shifted[i] - ring[i]) / step if shifted is not None else None)
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
                move(motor, motor.position + step_to_axis)
            ring = find_ring(camera.get_image())

    # fine: centroid steps as in center_lenses, but with capped moves
    for i, motor in enumerate(motors):
        for _ in range(fine_iterations):
            start = motor.position
            c0 = centroid(camera.get_image())[i]
            move(motor, start + fine_step)
            c1 = centroid(camera.get_image())[i]
            gain = (c1 - c0) / fine_step
            to_axis = (axis[i] - c0) / gain if gain else 0.0
            move(motor, start + np.clip(to_axis, -max_fine_move, max_fine_move))
        if verbose:
            print(f"{motor.name}: {motor.position:.4f}")

    for other in others:
        other.insert(wait=True)


def center_lenses_ring(tfs, camera, lenses=None, **kwargs):
    """Center every lens in `lenses` (default: all TFS lenses) with center_lens_ring."""
    for lens in lenses or tfs.tfs_lenses:
        center_lens_ring(tfs, lens, camera, **kwargs)
