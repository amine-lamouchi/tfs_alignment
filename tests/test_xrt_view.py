import numpy as np
import pytest
import xrt.backends.raycing.oes as roe

from tfs_twin import DigitalTwin, design_geometry
from tfs_twin.xrt_view import build_beamline, run_process, update_beamline


def test_focus_at_ip():
    twin = DigitalTwin(9500, N=64, geometry=design_geometry(), misalignment=0)
    twin.tfs.focus_at(energy_eV=9500, wait=True)
    bl = build_beamline(twin, nrays=5000)
    lenses = [element.name for element in bl.elements if isinstance(element, roe.OE)]
    assert lenses == [lens.name.replace("tfs_sim_", "") for lens in twin.tfs.lenses if lens.inserted]
    names = {element.name for element in bl.elements}
    assert {"DG1_slits", "DG2_us_slit", "MR1L4", "DIA_YAG", "DG3_YAG"} <= names  # from Matt's model
    beam = run_process(bl)["MFX_IP"]
    good = beam.state == 1
    r = np.hypot(beam.x[good], beam.z[good])  # mm
    assert np.mean(r < 5e-3) > 0.5  # most rays focused within 5 um; the rest went around the lens apertures


def test_update_beamline():
    twin = DigitalTwin(9500, N=64, geometry=design_geometry(), misalignment=0)
    twin.tfs.tfs_06.insert(wait=True)
    bl = build_beamline(twin, nrays=1000)
    lens = next(element for element in bl.elements if element.name == "tfs_06")
    twin.tfs.tfs_06.x.mvr(0.05)
    twin.tfs.translation.mvr(-10)
    update_beamline(bl, twin)
    assert lens.center[0] == pytest.approx(0.05)
    assert lens.center[1] == pytest.approx(twin.tfs.tfs_06.z * 1e3)
    twin.tfs.tfs_05.insert(wait=True)
    with pytest.raises(ValueError):
        update_beamline(bl, twin)


def test_broken_xrt_patch_only_warns():
    from tfs_twin.xrt_view import _cosmetic

    @_cosmetic
    def patch():
        raise AttributeError("xrtGlWidget has no attribute 'drawText'")  # as if xrt changed

    with pytest.warns(UserWarning, match="skipped"):
        patch()


def test_no_display_is_a_clear_error(monkeypatch):
    from tfs_twin import xrt_view

    monkeypatch.setattr(xrt_view.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    with pytest.raises(RuntimeError, match="needs a screen"):
        xrt_view._check_display()
