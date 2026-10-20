"""Digital twin of the MFX transfocator."""
import warnings

from tfs_twin import _paths  # noqa: F401  (makes `import tfs` work)

# lcls_beamline_toolbox calls scipy's interp2d on every YAG; scipy is pinned
# <1.14 so it works, but the deprecation warning would flood the output.
warnings.filterwarnings("ignore", message=".*interp2d.*", category=DeprecationWarning)

from tfs_twin.geometry import design_geometry, load_geometry, snapshot  # noqa: E402
from tfs_twin.motor_sim import make_tfs_sim  # noqa: E402
from tfs_twin.twin import DigitalTwin, SimCamera  # noqa: E402
