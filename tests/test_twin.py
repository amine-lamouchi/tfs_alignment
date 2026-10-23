import numpy as np
import pytest

from protocols.center_lenses import center_lens
from tfs_twin import DigitalTwin, SimCamera, design_geometry


@pytest.fixture
def twin():
    return DigitalTwin(9500, N=128, geometry=design_geometry(), misalignment=0)


def test_model_follows_tfs(twin):
    twin.tfs.tfs_06.insert(wait=True)
    twin.tfs.translation.mvr(-50)
    twin.propagate()
    crl = twin.crls["tfs_06"]
    assert crl.enabled and not twin.crls["tfs_05"].enabled
    assert crl.roc == pytest.approx(125e-6)
    assert crl.z == pytest.approx(twin.tfs.tfs_06.z + 624.645)


def test_focused_at_ip(twin):
    twin.tfs.focus_at(energy_eV=9500, wait=True)
    twin.propagate()
    assert twin.beamline.MFX_IP.wx < 5e-6


def test_decentered_lens_steers_beam(twin):
    twin.tfs.prefocus_bot.insert(wait=True)
    twin.tfs.tfs_06.insert(wait=True)
    twin.propagate()
    cx = twin.beamline.DG3_YAG.cx
    twin.tfs.tfs_06.x.mvr(0.03)  # 30 um
    twin.propagate()
    assert abs(twin.beamline.DG3_YAG.cx - cx) > 5e-6


def test_center_lens():
    twin = DigitalTwin(9500, N=128, geometry=design_geometry(), misalignment=50e-6, seed=3)
    twin.tfs.prefocus_bot.insert(wait=True)
    assert np.hypot(*twin.lens_offsets()["tfs_06"]) > 20e-6
    center_lens(twin.tfs, twin.tfs.tfs_06, SimCamera(twin, "DG3_YAG"), verbose=False)
    assert np.hypot(*twin.lens_offsets()["tfs_06"]) < 5e-6


def test_geometry_matches_matts_model():
    # with the design geometry, tfs, the twin and Matt's untouched model agree
    from lcls_beamline_toolbox.models.mfx import MFX

    twin = DigitalTwin(9500, N=64, geometry=design_geometry(), misalignment=0)
    for lens in twin.tfs.lenses:
        lens.insert(wait=True)
    twin.sync()
    matt = MFX(9500, N=64).beamline
    assert twin.beamline.MFX_IP.z == pytest.approx(matt.MFX_IP.z)
    assert twin.tfs.nominal_sample + 624.645 == pytest.approx(matt.MFX_IP.z)
    assert twin.tfs.prefocus_bot.z + 624.645 == pytest.approx(matt.prefocus.z)
    assert twin.mfx_sim.beam_params["z_source"] == MFX(9500, N=64).beam_params["z_source"]
    for name, crl in twin.crls.items():
        original = getattr(matt, crl.name)
        assert getattr(twin.tfs, name).z + 624.645 == pytest.approx(original.z)
        assert crl.diameter == pytest.approx(original.diameter)
