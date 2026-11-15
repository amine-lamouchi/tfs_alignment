"""
Moving MFX's motors the way the protocols need, on the instrument and on the twin alike. The twin's
motors have no EPICS record and move instantly, so there is nothing to wait for there.
"""
import time

import numpy as np
from epics import caget


def _record(motor):
    """The motor's EPICS motor record, or None for the twin's motors."""
    return motor.prefix if hasattr(motor, "setpoint") else None


def wait_stopped(motor, timeout=30.0):
    """
    Wait for the motor record's done-moving flag (.DMOV). MFX's lens motors report a move done as
    soon as it is sent, so `mv(wait=True)` alone does not mean the motor has stopped.
    """
    record = _record(motor)
    if record is None:
        return
    deadline = time.monotonic() + timeout
    while caget(record + ".DMOV") != 1:
        if time.monotonic() > deadline:
            raise TimeoutError(f"{record} still moving after {timeout} s")
        time.sleep(0.02)


def move(motor, target):
    """Move and wait until the motor has stopped."""
    motor.mv(target, wait=True)
    wait_stopped(motor)


def insert(lens):
    """Insert and wait for y to stop: insert(wait=True) returns once the IOC reads In, before y stops."""
    lens.insert(wait=True)
    wait_stopped(lens.y)


def remove(lens):
    """Remove and wait for y to stop, so nothing of the lens is left in the beam."""
    lens.remove(wait=True)
    wait_stopped(lens.y)


def fresh_image(camera, average=5, timeout=10.0):
    """
    The mean of `average` images taken after this call, against shot-to-shot noise. A camera serves
    its latest frame, which can be from before the last move, so wait for its frame counter to move
    on (the first new frame may have begun before the call, so it is skipped). The twin's camera has
    no PV and renders the present, so its images are read at once.
    """
    pv = getattr(camera, "camera_pv", None)
    if pv is None:
        return np.mean([camera.get_image() for _ in range(average)], axis=0)
    counter = pv + ":IMAGE1:ArrayCounter_RBV"
    last = caget(counter) + 1
    deadline = time.monotonic() + timeout
    frames = []
    while len(frames) < average:
        if time.monotonic() > deadline:
            raise TimeoutError(f"{pv}: {len(frames)} new frames in {timeout} s")
        count = caget(counter)
        if count > last:
            frames.append(camera.get_image().astype(float))
            last = count
        else:
            time.sleep(0.01)
    return np.mean(frames, axis=0)


def readback(motor):
    """
    Where the motor is. On MFX's lens motors `position` is the setpoint, so read the motor record's
    readback (.RBV). The twin's motors are where they were told to go.
    """
    record = _record(motor)
    return motor.position if record is None else float(caget(record + ".RBV"))


def remove_others(tfs, lens):
    """
    Remove every TFS lens but `lens` that is not out, and return {lens: y} for each one removed. A
    centered lens can sit outside its IN window, where `inserted` reads False though it is in the
    beam, so a lens counts as in unless it reads `removed`.
    """
    removed = {other: readback(other.y) for other in tfs.tfs_lenses if other is not lens and not other.removed}
    for other in removed:
        remove(other)
    return removed


def put_back(removed):
    """Insert each lens and move it back to the y it had, so it keeps its centering."""
    for lens, y in removed.items():
        insert(lens)
        move(lens.y, y)


def one_at_a_time(tfs, lenses, center_one):
    """
    Center each of `lenses` with `center_one(lens)` alone in the beam, then put them all in at their
    centered y. Every lens starts from all-out and goes back out after, so the ladders move once per
    lens instead of every other lens moving out and back for each one. Lenses that were in and not
    in `lenses` go back to the y they had.
    """
    taken_out = remove_others(tfs, None)
    centered = {}
    for lens in lenses:
        center_one(lens)
        centered[lens] = readback(lens.y)
        remove(lens)
    put_back({**taken_out, **centered})
