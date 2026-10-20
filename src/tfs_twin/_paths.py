"""
Make ``import tfs`` work.

``tfs`` lives in pcdshub/mfx and is not pip-installable, so by default we
import it from the ``external/mfx`` submodule. Set ``TFS_MFX_PATH`` to use a
different checkout (e.g. the hutch's mfx repo on psdev, so the twin runs
against exactly the code that drives the real transfocator).
"""
import importlib.util
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SUBMODULE_MFX = REPO_ROOT / "external" / "mfx"


def _setup():
    env_path = os.environ.get("TFS_MFX_PATH")
    if env_path:
        path = Path(env_path).expanduser().resolve()
        if not (path / "tfs").is_dir():
            raise ImportError(f"TFS_MFX_PATH={env_path} has no tfs/ directory")
        sys.path.insert(0, str(path))
        return
    if importlib.util.find_spec("tfs") is not None:
        # Already importable, e.g. inside a hutch-python session.
        return
    if not (SUBMODULE_MFX / "tfs").is_dir():
        raise ImportError(
            "Cannot find the tfs package. Run `git submodule update --init` "
            "or set TFS_MFX_PATH to an mfx checkout."
        )
    sys.path.append(str(SUBMODULE_MFX))


_setup()
