"""
Offline MFX transfocator: the real `tfs.transfocator.Transfocator` with every
PV faked and every motor replaced by a software positioner.

Replaces `tfs/sim_transfocator.py` (mfx#233), which needed a live `tfs`,
moved the prefocus lenses with the TFS stage, and left the lens x/y motors on
the real MFX:TFS:MMS:03..20 PVs.

    tfs_sim = make_tfs_sim()      # offline, from snapshots/latest.json or design values
    tfs_sim = make_tfs_sim(tfs)   # in hutch-python, copy the live geometry
"""
from ophyd import Component as Cpt
from ophyd import Device, SoftPositioner
from ophyd.signal import EpicsSignalBase
from ophyd.sim import make_fake_device
from tfs.lens import MFXLens
from tfs.transfocator import Transfocator

from tfs_twin.geometry import TFS_RADII, load_geometry, read_geometry


class SimMotor(SoftPositioner):
    """Software motor with the mv/mvr/wm/mv_retry calls of the real lens motors."""

    def __init__(self, prefix="", **kwargs):
        super().__init__(init_pos=0.0, **kwargs)
        self.prefix = prefix

    def set_position(self, position, limits=None):
        """Set the readback (and limits) without a move."""
        SoftPositioner._set_position(self, position)
        if limits is not None:
            self._limits = tuple(limits)

    def mv(self, position, wait=True, timeout=None):
        return self.move(position, wait=wait, timeout=timeout)

    def mvr(self, delta, wait=True, timeout=None):
        return self.mv(self.position + delta, wait=wait, timeout=timeout)

    def wm(self):
        return self.position

    def mv_retry(self, position, *, retries=3, tolerance=1e-2, settle_time=0.2, timeout=None):
        return self.mv(position, timeout=timeout)


class NoMotor(SimMotor):
    """The prefocus lenses have no x/y motors on the real instrument."""

    def move(self, *args, **kwargs):
        if getattr(self, "_built", False):
            raise RuntimeError(f"{self.name}: prefocus lenses have no x/y motors")
        self._built = True  # SoftPositioner moves once to init_pos while being built
        return super().move(*args, **kwargs)


class SimStage(SimMotor):
    """TFS z translation [mm]. Moves the TFS lenses with it, not the prefocus lenses."""

    def _set_position(self, value, **kwargs):
        old = self._position
        super()._set_position(value, **kwargs)
        if old is not None and self.parent is not None:
            for lens in self.parent.tfs_lenses:
                lens._sig_z.sim_put(lens._sig_z.get() + (value - old) / 1000)  # mm -> m


class SimLens(make_fake_device(MFXLens)):
    x = Cpt(SimMotor, ":X")
    y = Cpt(SimMotor, ":Y")

    def _do_move(self, state):
        if state.name == "IN":
            self._removed.sim_put(0)
            self._inserted.sim_put(1)
        elif state.name == "OUT":
            self._inserted.sim_put(0)
            self._removed.sim_put(1)
        else:
            raise ValueError(f"Invalid State {state}")


class SimPrefocusLens(SimLens):
    x = Cpt(NoMotor, ":X", kind="omitted")
    y = Cpt(NoMotor, ":Y", kind="omitted")


class SimTransfocator(make_fake_device(Transfocator)):
    prefocus_top = Cpt(SimPrefocusLens, ":DIA:03")
    prefocus_mid = Cpt(SimPrefocusLens, ":DIA:02")
    prefocus_bot = Cpt(SimPrefocusLens, ":DIA:01")
    tfs_02 = Cpt(SimLens, ":TFS:02")
    tfs_03 = Cpt(SimLens, ":TFS:03")
    tfs_04 = Cpt(SimLens, ":TFS:04")
    tfs_05 = Cpt(SimLens, ":TFS:05")
    tfs_06 = Cpt(SimLens, ":TFS:06")
    tfs_07 = Cpt(SimLens, ":TFS:07")
    tfs_08 = Cpt(SimLens, ":TFS:08")
    tfs_09 = Cpt(SimLens, ":TFS:09")
    tfs_10 = Cpt(SimLens, ":TFS:10")
    translation = Cpt(SimStage, ":MMS:21")


def real_pvs(device_cls, path=""):
    """Components of `device_cls` that would connect to EPICS. Checks the class only."""
    found = []
    for attr, cpt in device_cls._sig_attrs.items():
        if issubclass(cpt.cls, EpicsSignalBase):
            found.append(path + attr)
        elif issubclass(cpt.cls, Device):
            found += real_pvs(cpt.cls, f"{path}{attr}.")
    return found


# Never build a simulator that can talk to real hardware.
assert not real_pvs(SimTransfocator), real_pvs(SimTransfocator)


def make_tfs_sim(tfs=None, geometry=None, prefix="SIM:", name="tfs_sim"):
    """
    Offline transfocator. Geometry from the live `tfs` if given, otherwise
    `geometry`, otherwise `load_geometry()`.
    """
    # Transfocator sorts lenses by looking for "TFS"/"DIA" in their prefix (mfx#233)
    if "TFS" in prefix or "DIA" in prefix:
        raise ValueError("prefix must not contain 'TFS' or 'DIA'")
    if tfs is not None:
        geometry = read_geometry(tfs)
    geometry = geometry or load_geometry()

    tfs_sim = SimTransfocator(prefix, name=name, nominal_sample=geometry["nominal_sample"])
    tfs_sim.translation.set_position(geometry["stage"], geometry["stage_limits"])
    for lens_name, values in geometry["lenses"].items():
        lens = getattr(tfs_sim, lens_name)
        lens._sig_z.sim_put(values["z"])
        lens._sig_radius.sim_put(values["radius"])
        if lens_name in geometry["inserted"]:
            lens._inserted.sim_put(1)
        else:
            lens._removed.sim_put(1)
        if lens_name in TFS_RADII:
            lens.x.set_position(values["x"])
            lens.y.set_position(values["y"])
    return tfs_sim
