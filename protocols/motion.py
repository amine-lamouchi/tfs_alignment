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
