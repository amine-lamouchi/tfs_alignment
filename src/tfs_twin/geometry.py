"""
Transfocator geometry shared by both simulators, as a plain dict / json file.

Units are the control-system ones (what `tfs` reads from EPICS):
lens z in m from the source, radius in um, stage in mm, lens x/y in mm.
"""
import json
import os
from datetime import datetime
from pathlib import Path

from tfs_twin._paths import REPO_ROOT

DEFAULT_SNAPSHOT = REPO_ROOT / "snapshots" / "latest.json"

PREFOCUS_RADII = {"prefocus_top": 333.3, "prefocus_mid": 428.0, "prefocus_bot": 750.0}
TFS_RADII = {"tfs_02": 500, "tfs_03": 300, "tfs_04": 250, "tfs_05": 200, "tfs_06": 125,
             "tfs_07": 62.5, "tfs_08": 50, "tfs_09": 50, "tfs_10": 50}

# Matt's MFX model uses LCLS z: z_lcls = z + Z_OFFSET. This puts TFS:06 at
# 1020.44 m (the model's TFS centre) with the stage at ~230 mm.
Z_OFFSET = 624.645


def aperture(radius):
    """
    Geometric aperture 2*R0 [m] of a lens of radius [um]. Fit to the table on
    the "Working Transfocator Combinations" Confluence page.
    """
    return 63.2e-6 * radius ** 0.5


def design_geometry():
    """Readbacks from the real instrument (mfx#233, stage at 229.9945 mm)."""
    lenses = {name: {"radius": radius, "z": 360.0} for name, radius in PREFOCUS_RADII.items()}
    for i, (name, radius) in enumerate(TFS_RADII.items()):
        # lenses are 75 mm apart
        lenses[name] = {"radius": radius, "z": 395.49499 + 0.075 * i, "x": 0.0, "y": 0.0}
    return {"source": "design", "lenses": lenses, "inserted": [],
            "stage": 229.9945, "stage_limits": [-0.409, 299.591], "nominal_sample": 400.37}


def read_geometry(tfs):
    """Read the geometry of a live `tfs`. Read-only, nothing moves."""
    lenses = {}
    for name in [*PREFOCUS_RADII, *TFS_RADII]:
        lens = getattr(tfs, name)
        lenses[name] = {"radius": float(lens.radius), "z": float(lens.z)}
        if name in TFS_RADII:
            lenses[name].update(x=float(lens.x.position), y=float(lens.y.position))
    return {"source": f"{tfs.name} {datetime.now():%Y-%m-%d %H:%M}",
            "lenses": lenses,
            "inserted": [name for name in lenses if getattr(tfs, name).inserted],
            "stage": float(tfs.translation.position),
            "stage_limits": [float(tfs.translation.low_limit), float(tfs.translation.high_limit)],
            "nominal_sample": float(tfs.nominal_sample)}


def snapshot(tfs, path=DEFAULT_SNAPSHOT):
    """Save the geometry of a live `tfs` to json (default snapshots/latest.json)."""
    geometry = read_geometry(tfs)
    Path(path).parent.mkdir(exist_ok=True)
    Path(path).write_text(json.dumps(geometry, indent=2))
    print(f"Saved {geometry['source']} to {path}")
    return geometry


def load_geometry(path=None):
    """Geometry from `path`, $TFS_TWIN_SNAPSHOT, snapshots/latest.json, or the design values."""
    path = path or os.environ.get("TFS_TWIN_SNAPSHOT")
    if path is None and DEFAULT_SNAPSHOT.exists():
        path = DEFAULT_SNAPSHOT
    if path is None:
        return design_geometry()
    return json.loads(Path(path).read_text())
