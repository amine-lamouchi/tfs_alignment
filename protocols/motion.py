"""
Moving MFX's motors the way the protocols need, on the instrument and on the twin alike. The twin's
motors have no EPICS record and move instantly, so there is nothing to wait for there.
"""
import time

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


def fresh_image(camera, timeout=10.0):
    """
    An image taken after this call. A camera serves its latest frame, which can be from before the
    last move, so wait for its frame counter to move on twice (the first new frame may have begun
    before the call). The twin's camera has no PV and renders the present, so it is read at once.
    """
    pv = getattr(camera, "camera_pv", None)
    if pv is None:
        return camera.get_image()
    counter = pv + ":IMAGE1:ArrayCounter_RBV"
    start = caget(counter)
    deadline = time.monotonic() + timeout
    while caget(counter) < start + 2:
        if time.monotonic() > deadline:
            raise TimeoutError(f"{pv}: no new frame in {timeout} s")
        time.sleep(0.02)
    return camera.get_image()


def readback(motor):
    """
    Where the motor is. On MFX's lens motors `position` is the setpoint, so read the motor record's
    readback (.RBV). The twin's motors are where they were told to go.
    """
    record = _record(motor)
    return motor.position if record is None else float(caget(record + ".RBV"))
