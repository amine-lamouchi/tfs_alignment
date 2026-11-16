"""
Sweep one DigitalTwin input at a time and run a centering protocol on it.

Base point: DigitalTwin(9500, N=256, misalignment=5e-5, seed=3), focus_at(E0), then the protocol
with SimCamera(twin, <camera>, noise=True). Grades with twin.lens_offsets() (hidden truth).
Writes results/<camera>/<param>[_<method>].json after every run, so partial results survive.

    python sweep.py misalignment                                  # one of: E0, N, misalignment, seed
    python sweep.py misalignment --camera DG3_YAG --method ring   # default: DG2_YAG, baseline
    python sweep.py E0 --method ring --resume                     # finish a stopped sweep
"""
import argparse
import contextlib
import io
import json
import logging
import os
import time
from pathlib import Path

logging.getLogger("tfs").setLevel(logging.CRITICAL)  # mute "TFS combo may be forbidden"

import numpy as np

from protocols.center_lenses import center_lenses
from protocols.center_rings import center_lenses_ring
from tfs_twin import DigitalTwin, SimCamera

HERE = Path(__file__).resolve().parent
METHODS = {
    "baseline": center_lenses,
    "ring": center_lenses_ring,
}

BASE = dict(E0=9500, N=256, misalignment=5e-5, seed=3)
SWEEPS = {
    "E0": [5000, 6000, 7000, 8000, 9000, 9500, 10000, 11000, 12000, 13000, 14000, 15000],
    "N": [32, 48, 64, 96, 128, 160, 192, 256, 384, 512],
    "misalignment": [1e-5, 2.5e-5, 5e-5, 7.5e-5, 1e-4, 1.25e-4, 1.5e-4, 1.75e-4, 2e-4, 2.5e-4, 3e-4, 4e-4, 5e-4],
    "seed": list(range(20)),
}
NOISE_SEEDS = {"E0": [0, 1, 2], "N": [0], "misalignment": [0, 1, 2], "seed": [0]}  # camera shot-noise seeds


def run_one(E0, N, misalignment, seed, noise_seed, camera_yag="DG2_YAG", method="baseline"):
    twin = DigitalTwin(E0, N=N, misalignment=misalignment, seed=seed)
    tfs = twin.tfs
    with contextlib.redirect_stdout(io.StringIO()):  # focus_at prints the lens table
        tfs.focus_at(energy_eV=E0, wait=True)
    lenses = [lens for lens in tfs.tfs_lenses if lens.inserted]
    names = [twin._name(lens) for lens in lenses]
    before = {n: float(np.hypot(*twin.lens_offsets()[n])) * 1e6 for n in names}
    camera = SimCamera(twin, camera_yag, noise=True, seed=noise_seed)
    t0, crash = time.time(), None
    try:
        with np.errstate(all="ignore"):
            METHODS[method](tfs, camera, lenses=lenses, verbose=False)
    except Exception as error:  # noqa: BLE001
        crash = repr(error)[:120]
    after = {n: float(np.hypot(*twin.lens_offsets()[n])) * 1e6 for n in names}
    return dict(lenses=names, before_um=max(before.values()), after_um=max(after.values()),
                before_per_lens=before, after_per_lens=after, crash=crash, seconds=round(time.time() - t0, 1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sweep one DigitalTwin input, run a centering protocol.")
    parser.add_argument("param", choices=list(SWEEPS))
    parser.add_argument("--camera", default="DG2_YAG", help="YAG the protocol's camera reads (default DG2_YAG)")
    parser.add_argument("--method", default="baseline", choices=list(METHODS),
                        help="baseline (center_lenses) or ring (center_lenses_ring)")
    parser.add_argument("--resume", action="store_true", help="keep finished runs in the json, do only the rest")
    args = parser.parse_args()
    param = args.param
    os.makedirs(HERE / "results" / args.camera, exist_ok=True)
    suffix = "" if args.method == "baseline" else f"_{args.method}"
    path = HERE / "results" / args.camera / f"{param}{suffix}.json"
    results = json.load(open(path)) if args.resume and os.path.exists(path) else []
    done = {(r["value"], r["noise_seed"]) for r in results}
    for value in SWEEPS[param]:
        for noise_seed in NOISE_SEEDS[param]:
            if (value, noise_seed) in done:
                continue
            inputs = {**BASE, param: value}
            result = {"param": param, "value": value, "noise_seed": noise_seed, "inputs": inputs,
                      "camera": args.camera, "method": args.method,
                      **run_one(**inputs, noise_seed=noise_seed, camera_yag=args.camera, method=args.method)}
            results.append(result)
            with open(path, "w") as f:
                json.dump(results, f, indent=1)
            print(f"{param}={value} noise={noise_seed}: worst {result['before_um']:.1f} -> {result['after_um']:.1f} um"
                  f"{'  CRASH ' + result['crash'] if result['crash'] else ''} ({result['seconds']} s)", flush=True)
