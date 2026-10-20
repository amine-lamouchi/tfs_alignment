import json

import pytest
from ophyd.utils import LimitError
from tfs.lens import LensConnect
from tfs.offline_calculator import TFS_Calculator
from tfs.transfocator import Transfocator

from tfs_twin import design_geometry, make_tfs_sim
from tfs_twin.motor_sim import SimTransfocator, real_pvs


@pytest.fixture
def tfs():
    return make_tfs_sim(geometry=design_geometry())


def test_no_real_pvs():
    assert "tfs_02.x.setpoint" in real_pvs(Transfocator)  # the check does catch them
    assert real_pvs(SimTransfocator) == []


def test_prefix_cannot_contain_tfs_or_dia():
    with pytest.raises(ValueError):
        make_tfs_sim(geometry=design_geometry(), prefix="SIM:TFS")


def test_lens_sorting(tfs):
    assert len(tfs.xrt_lenses) == 3
    assert len(tfs.tfs_lenses) == 9


def test_prefocus_has_no_xy_motors(tfs):
    with pytest.raises(RuntimeError):
        tfs.prefocus_bot.x.mv(1.0)


def test_stage_moves_only_tfs_lenses(tfs):
    z_tfs, z_prefocus = tfs.tfs_05.z, tfs.prefocus_bot.z
    tfs.translation.mvr(-10.0)
    assert tfs.tfs_05.z == pytest.approx(z_tfs - 0.010)
    assert tfs.prefocus_bot.z == z_prefocus
    with pytest.raises(LimitError):
        tfs.translation.mv(400)


def test_insert_remove(tfs):
    tfs.tfs_04.insert(wait=True)
    assert tfs.tfs_04.inserted
    tfs.tfs_04.remove(wait=True)
    assert tfs.tfs_04.removed


def test_focus_at(tfs):
    tfs.focus_at(energy_eV=9500, wait=True)
    inserted = [lens for lens in tfs.lenses if lens.inserted]
    assert abs(LensConnect(*inserted).image(0.0, 9500) - tfs.nominal_sample) < 0.02


def test_track_focus(tfs, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))  # track_focus saves ~/track_focus_results.json
    record = tfs.track_focus([9500, 9550, 9600], margin_mm=5.0, display=False)
    assert [step["energy"] for step in record] == [9500, 9550, 9600]
    assert json.loads((tmp_path / "track_focus_results.json").read_text()) == record


def test_matches_confluence(tfs):
    # "Calculate Transfocator Combinations": stage at 100 mm gives these lens z
    tfs.translation.mv(100)
    assert tfs.tfs_02.z == pytest.approx(395.365, abs=1e-3)
    assert tfs.tfs_06.z == pytest.approx(395.665, abs=1e-3)
    assert tfs.tfs_09.z == pytest.approx(395.889, abs=1e-3)
    assert not TFS_Calculator(tfs.lenses).check_forbidden(750, energy=9551, radius=33.33)
