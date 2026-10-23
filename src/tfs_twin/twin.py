"""
Digital twin of the MFX transfocator.

    twin.tfs       offline `tfs` (same API as in hutch-python)
    twin.mfx_sim   Matt's wavefront model, lcls_beamline_toolbox.models.mfx.MFX
    twin.beamline  twin.mfx_sim.beamline

Move things with twin.tfs, call twin.propagate(), then look at the YAGs as
usual, e.g. twin.beamline.DG3_YAG.view_beam() or .profile / .cx / .wx.
Don't use the mfx_sim motion axes (tfs_5_x, tfs_z, ...): propagate()
overwrites the lens positions from twin.tfs.
"""
import numpy as np
from lcls_beamline_toolbox.models.mfx import MFX
from lcls_beamline_toolbox.xraywavetrace.beam import Beam

from tfs_twin.geometry import TFS_RADII, Z_OFFSET, aperture, load_geometry
from tfs_twin.motor_sim import make_tfs_sim


class DigitalTwin:
    """
    Parameters
    ----------
    E0 : float
        Photon energy [eV].
    N : int
        Wavefront grid size, as in MFX(E0, N). 256 takes ~0.5 s per propagate.
    geometry : dict, optional
        Default: load_geometry() (snapshot if there is one, design values otherwise).
    misalignment : float
        Each TFS lens's true center is hidden within +/- this many metres of
        its motor readback. 0 gives a perfectly aligned transfocator.
    seed : int, optional
        Seed for the hidden misalignment.
    """

    def __init__(self, E0, N=256, geometry=None, misalignment=50e-6, seed=None, multi_beam=True):
        self.geometry = geometry or load_geometry()
        self.tfs = make_tfs_sim(geometry=self.geometry)
        self.mfx_sim = MFX(E0, N=N, multi_beam=multi_beam)
        self.beamline = self.mfx_sim.beamline
        self.crls = dict(zip(TFS_RADII, self.mfx_sim.tfs_list))  # tfs_02 -> tfs_2, ...

        # Positions as built by the model; we move devices along the beam from there.
        devices = [self.beamline.prefocus, self.beamline.MFX_IP, *self.mfx_sim.tfs_list]
        self._ref = {dev.name: (dev.get_pos().copy(), dev.z) for dev in devices}
        # IP at nominal_sample, as in tfs. The source stays where Matt's model puts it,
        # 0.645 m upstream of tfs z=0 (tfs assumes z=0; the focus moves by ~0.2 mm).
        self._place(self.beamline.MFX_IP, self.geometry["nominal_sample"])
        self.set_energy(E0)

        # Hidden truth: x/y motor position [mm] where each TFS lens is centered on the beam
        rng = np.random.default_rng(seed)
        self._center = {}
        for name in TFS_RADII:
            lens = self.geometry["lenses"][name]
            dx, dy = rng.uniform(-1, 1, 2) * misalignment * 1e3
            self._center[name] = (lens["x"] + dx, lens["y"] + dy)

    def set_energy(self, E0):
        self.tfs.beam_energy.sim_put(E0)
        self.mfx_sim.E0 = E0
        self.mfx_sim.beam_params["photonEnergy"] = E0
        self.mfx_sim.b1 = Beam(beam_params=self.mfx_sim.beam_params, suppress=True)

    def _name(self, lens):
        """tfs_sim_tfs_05 -> tfs_05"""
        return lens.name.removeprefix(self.tfs.name + "_")

    def _place(self, device, z, dx=0.0, dy=0.0):
        """Put a model device at tfs z [m], off the beam axis by dx, dy [m]."""
        pos0, z0 = self._ref[device.name]
        dz = z + Z_OFFSET - z0
        device.set_pos(pos0 + device.zhat * dz / device.zhat[2] + device.xhat * dx + device.yhat * dy)

    def lens_offsets(self):
        """True (dx, dy) [m] of each TFS lens from the beam axis. For grading only."""
        offsets = {}
        for name in TFS_RADII:
            lens = getattr(self.tfs, name)
            cx, cy = self._center[name]
            offsets[name] = ((lens.x.position - cx) * 1e-3, (lens.y.position - cy) * 1e-3)
        return offsets

    def sync(self):
        """Copy lens state from twin.tfs into the wavefront model."""
        offsets = self.lens_offsets()
        for name, crl in self.crls.items():
            lens = getattr(self.tfs, name)
            crl.roc = lens.radius * 1e-6
            crl.diameter = aperture(name, lens.radius)
            crl.enable() if lens.inserted else crl.disable()
            self._place(crl, lens.z, *offsets[name])
        # The model has one prefocus lens; combine if several are inserted
        prefocus = self.beamline.prefocus
        inserted = [lens for lens in self.tfs.xrt_lenses if lens.inserted]
        if inserted:
            radius = 1 / sum(1 / lens.radius for lens in inserted)
            prefocus.roc = radius * 1e-6
            prefocus.diameter = min(aperture(self._name(lens), lens.radius) for lens in inserted)
            prefocus.enable()
            self._place(prefocus, inserted[0].z)
        else:
            prefocus.disable()

    def propagate(self):
        self.sync()
        self.mfx_sim.propagate()

    def report(self):
        """Print the hidden truth: focus error and decentring of inserted TFS lenses."""
        print(f"E0 = {self.mfx_sim.E0:.1f} eV")
        print(f"focus - nominal_sample = {self.tfs.current_focus * 1e3:+.2f} mm")
        for name, (dx, dy) in self.lens_offsets().items():
            if getattr(self.tfs, name).inserted:
                print(f"{name}: dx = {dx * 1e6:+6.1f} um, dy = {dy * 1e6:+6.1f} um")


class SimCamera:
    """
    YAG camera on the twin. get_image() works like
    tfs.transfocator_scan.gigE_camera_accessor.get_image().
    """

    def __init__(self, twin, yag, noise=False, seed=None):
        self.twin = twin
        self.yag = yag
        self.noise = noise
        self.rng = np.random.default_rng(seed)
        self.scale = None

    def get_image(self):
        self.twin.propagate()
        image = getattr(self.twin.beamline, self.yag).profile
        if self.scale is None:
            self.scale = 4000 / image.max()  # ~4000 counts peak on the first frame
        image = image * self.scale
        if self.noise:
            image = self.rng.poisson(image + 20).astype(float)  # shot noise + background
        return image
