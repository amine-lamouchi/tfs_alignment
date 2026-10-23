"""
3D view of the twin with xrt (https://xrt.readthedocs.io), ray tracing.

    from tfs_twin.xrt_view import glow, movie
    glow(twin)               # opens xrtGlow on the current state of twin.tfs
    movie(twin, scan, path)  # GIF of a scan written with the tfs API

Built from the twin's current state: inserted lenses, stage position, lens
offsets and energy. Everything else is Matt's model: source (Gaussian, 30 um
waist), YAGs, slits and mirrors at the same z. Units are xrt's: mm, beam along
y from the source, x horizontal, z vertical.
Simplifications: the beam line is unfolded into a straight line, so a mirror
is drawn as its clear aperture (length x grazing angle); each lens is one Be
double paraboloid with the lens radius and aperture, and about 1 mm of Be
outside the aperture.
"""
import functools
import os
import sys
import types
import warnings

import numpy as np

# xrt's Qt layer imports QtWebEngineWidgets, which only its xrtQook help pages
# use. That import fails once a Qt app exists (Jupyter after %gui qt) and needs
# a 100 MB package, so give it an empty stand-in; xrtGlow works without it.
sys.modules.setdefault("PyQt5.QtWebEngineWidgets", types.ModuleType("PyQt5.QtWebEngineWidgets"))

import xrt.backends.raycing as raycing  # noqa: E402
import xrt.backends.raycing.apertures as ra  # noqa: E402
import xrt.backends.raycing.materials as rm  # noqa: E402
import xrt.backends.raycing.oes as roe  # noqa: E402
import xrt.backends.raycing.run as rr  # noqa: E402
import xrt.backends.raycing.screens as rsc  # noqa: E402
import xrt.backends.raycing.sources as rs  # noqa: E402
from lcls_beamline_toolbox.xraywavetrace import optics  # noqa: E402

from .geometry import Z_OFFSET, aperture  # noqa: E402

XRT_TESTED = "1.6.2"  # the cosmetic patches below rely on xrtGlow internals of this version


def _cosmetic(patch):
    """
    Run a patch of xrtGlow internals; if xrt changed and it fails, warn and go
    on without it. The viewer still works, only that cosmetic touch is lost.
    """
    @functools.wraps(patch)
    def safe(*args, **kwargs):
        try:
            return patch(*args, **kwargs)
        except Exception as error:  # noqa: BLE001
            import xrt
            warnings.warn(f"3D view: {patch.__name__} skipped ({error!r}); tested with xrt {XRT_TESTED}, "
                          f"installed {xrt.__version__}", stacklevel=2)
    return safe


def _check_display():
    """Qt aborts the whole process (and a Jupyter kernel) when there is no screen; fail cleanly instead."""
    if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise RuntimeError("The 3D view needs a screen and none was found (no $DISPLAY). Run it on a machine "
                           "with a display, or over ssh -X / NoMachine. The rest of tfs_twin works without one.")

WAIST = 30e-6  # m, as beam_params["sigma_x"] in Matt's model
WEB = 0.03  # mm, Be between the two paraboloids at the lens center
LENS_HALF_WIDTH = 1.0  # mm, beyond this the lens frame blocks the beam
MIRROR_HALF_WIDTH = 10.0  # mm, mirror size across the deflection plane (not in Matt's model)

beryllium = rm.Material("Be", rho=1.848, kind="lens")


def build_beamline(twin, nrays=20000):
    """xrt BeamLine with the source, inserted lenses, YAGs and the IP."""
    E0 = twin.mfx_sim.E0
    wavelength = 12398.4 / E0 * 1e-10  # m
    divergence = wavelength / (np.pi * WAIST)

    bl = raycing.BeamLine()
    bl.source = rs.GeometricSource(
        bl, "source", center=[0, 0, 0], nrays=nrays,
        distx="normal", dx=WAIST / 2 * 1e3, distz="normal", dz=WAIST / 2 * 1e3,
        distxprime="normal", dxprime=divergence / 2, distzprime="normal", dzprime=divergence / 2,
        distE="lines", energies=(E0,), polarization="horizontal",
    )

    offsets = twin.lens_offsets()
    elements = []
    for lens in twin.tfs.lenses:
        if not lens.inserted:
            continue
        name = twin._name(lens)
        dx, dy = offsets.get(name, (0.0, 0.0))
        r0 = aperture(name, lens.radius) / 2 * 1e3  # mm
        radius = lens.radius * 1e-3  # mm
        elements.append(roe.DoubleParaboloidLens(
            bl, name, center=[dx * 1e3, lens.z * 1e3, dy * 1e3], pitch=np.pi / 2,
            material=beryllium, t=WEB, focus=radius / 2, zmax=r0**2 / (2 * radius), shape="round",
            limPhysX=[-LENS_HALF_WIDTH, LENS_HALF_WIDTH], limPhysY=[-LENS_HALF_WIDTH, LENS_HALF_WIDTH],
        ))
    # YAGs, slits and mirrors from Matt's model, at the same z (lenses come from twin.tfs above)
    for device in twin.beamline.device_list:
        center = [0, (device.z - Z_OFFSET) * 1e3, 0]
        if isinstance(device, optics.PPM) and device.name != "dummy":
            elements.append(rsc.Screen(bl, device.name, center=center))
        elif isinstance(device, optics.Slit):
            w, h = device.x_width * 1e3 / 2, device.y_width * 1e3 / 2
            elements.append(ra.RectangularAperture(bl, device.name, center=center, opening=[-w, w, -h, h]))
        elif isinstance(device, optics.FlatMirror):
            half = device.length * np.sin(device.alpha) * 1e3 / 2  # clear aperture in the deflection plane
            w, h = (half, MIRROR_HALF_WIDTH) if device.orientation in (0, 2) else (MIRROR_HALF_WIDTH, half)
            elements.append(ra.RectangularAperture(bl, device.name, center=center, opening=[-w, w, -h, h]))
    elements.sort(key=lambda element: element.center[1])
    bl.elements = elements

    rr.run_process = run_process
    return bl


def run_process(bl):
    outDict = {"source": bl.source.shine()}
    beam = outDict["source"]
    for element in bl.elements:
        if isinstance(element, rsc.Screen):
            outDict[element.name] = element.expose(beam)
        elif isinstance(element, ra.RectangularAperture):
            outDict[element.name] = element.propagate(beam)  # blocks rays in beam itself
        else:
            beam, local1, local2 = element.multiple_refract(beam)
            outDict[element.name] = beam
            outDict[element.name + "_local1"] = local1
            outDict[element.name + "_local2"] = local2
    bl.prepare_flow()
    return outDict


@_cosmetic
def _see_through_lenses():
    """
    Draw lenses as translucent blue-grey instead of xrtGlow's opaque grey.
    Patches xrtGlow internals (plotOeSurface, setMaterial): check after xrt upgrades.
    """
    from OpenGL import GL as gl
    from xrt.gui.xrtGlow import xrtGlWidget

    if getattr(xrtGlWidget, "_see_through_lenses", False):
        return
    plot_surface, set_material = xrtGlWidget.plotOeSurface, xrtGlWidget.setMaterial

    def plotOeSurface(self, oe, is2ndXtal):
        if not isinstance(oe, roe.ParaboloidFlatLens):
            return plot_surface(self, oe, is2ndXtal)
        self._lens = True
        gl.glDepthMask(gl.GL_FALSE)  # overlapping lenses all stay visible
        try:
            return plot_surface(self, oe, is2ndXtal)
        finally:
            gl.glDepthMask(gl.GL_TRUE)
            self._lens = False

    def setMaterial(self, mat):
        if not getattr(self, "_lens", False):
            return set_material(self, mat)
        alpha = 0.3
        gl.glMaterialfv(gl.GL_FRONT_AND_BACK, gl.GL_AMBIENT, [0.15, 0.2, 0.25, alpha])
        gl.glMaterialfv(gl.GL_FRONT_AND_BACK, gl.GL_DIFFUSE, [0.45, 0.6, 0.75, alpha])
        gl.glMaterialfv(gl.GL_FRONT_AND_BACK, gl.GL_SPECULAR, [1.0, 1.0, 1.0, alpha])
        gl.glMaterialfv(gl.GL_FRONT_AND_BACK, gl.GL_EMISSION, [0.05, 0.08, 0.1, alpha])
        gl.glMaterialf(gl.GL_FRONT, gl.GL_SHININESS, 80)

    xrtGlWidget.plotOeSurface, xrtGlWidget.setMaterial = plotOeSurface, setMaterial
    xrtGlWidget._see_through_lenses = True


def _density(points, bins=48, gap=5.0):
    """
    Local ray density in [0, 1] at each point (N x 3, mm). Points are grouped
    by element (y gaps > `gap` mm) and histogrammed in x, z within each group.
    """
    density = np.zeros(len(points))
    order = np.argsort(points[:, 1])
    groups = np.split(order, np.where(np.diff(points[order, 1]) > gap)[0] + 1)
    for group in groups:
        x, z = points[group, 0], points[group, 2]
        counts, xedges, zedges = np.histogram2d(x, z, bins=bins)
        ix = np.clip(np.searchsorted(xedges, x, side="right") - 1, 0, bins - 1)
        iz = np.clip(np.searchsorted(zedges, z, side="right") - 1, 0, bins - 1)
        density[group] = counts[ix, iz] / counts.max()
    return density


@_cosmetic
def _density_colors(cmap="gnuplot"):
    """
    Colour rays and footprints by local ray density with Matt's colormap, so
    the bright core of the beam stands out as on his YAG images.
    Patches xrtGlow internals (populateVerticesArray): check after xrt upgrades.
    """
    import matplotlib

    from xrt.gui.xrtGlow import xrtGlWidget

    if getattr(xrtGlWidget, "_density_colors", False):
        return
    populate = xrtGlWidget.populateVerticesArray
    colormap = matplotlib.colormaps[cmap]

    def populateVerticesArray(self, segmentsModelRoot):
        populate(self, segmentsModelRoot)
        try:
            for points, colors in [("verticesArray", "raysColor"), ("footprintsArray", "dotsColor")]:
                points, colors = getattr(self, points, None), getattr(self, colors, None)
                if points is None or colors is None or len(points) != len(colors):
                    continue
                # 0.15 + ...: the darkest end of gnuplot is black, invisible on the black background
                colors[:, :3] = colormap(0.15 + 0.85 * np.sqrt(_density(points)))[:, :3]
        except Exception:  # noqa: BLE001  keep xrt's own colours
            pass

    xrtGlWidget.populateVerticesArray = populateVerticesArray
    xrtGlWidget._density_colors = True


@_cosmetic
def _quiet_glow():
    """Hide Qt's harmless "non-exposed window" warnings (xrtGlow draws before the window shows)."""
    from xrt.gui.commons import qt

    def handler(mode, context, message):
        if "non-exposed window" not in message:
            print(message)

    qt.QtCore.qInstallMessageHandler(handler)

    # Labels: just the name ("DG2_YAG", "tfs_06"), not "tfs_06_Entrance: (x, y, z)mm",
    # moved off the beam by widget.label_offsets[name] (mm)
    from xrt.gui.xrtGlow import xrtGlWidget

    if getattr(xrtGlWidget, "_short_labels", False):
        return
    draw_text = xrtGlWidget.drawText

    def drawText(self, coord, text, *args, useCaption=False, **kwargs):
        if useCaption:
            try:
                name = text.split(":")[0].strip().removesuffix("_Entrance")
                offset = np.array(getattr(self, "label_offsets", {}).get(name, (0, 0, 0)))
                coord, text = coord + offset * self.scaleVec / self.maxLen, "  " + name
            except Exception:  # noqa: BLE001  keep xrt's own label
                pass
        return draw_text(self, coord, text, *args, useCaption=useCaption, **kwargs)

    xrtGlWidget.drawText = drawText
    xrtGlWidget._short_labels = True


# YAGs and image sources offered in the viewer's right column
YAGS = ["DIA_YAG", "DG1_YAG", "DG2_YAG", "MFX_IP", "DG3_YAG"]
MODES = ["wavefront", "ray trace"]
_open_viewers = []  # keeps viewers (and their refresh timers) alive in Jupyter even if not assigned


def update_beamline(bl, twin):
    """Move the lenses of `bl` to where they are in the twin (stage, x/y motors)."""
    offsets = twin.lens_offsets()
    lenses = {e.name: e for e in bl.elements if isinstance(e, roe.OE)}
    inserted = {twin._name(lens): lens for lens in twin.tfs.lenses if lens.inserted}
    if set(inserted) != set(lenses):
        raise ValueError("Inserted lenses changed: rebuild the beam line with build_beamline")
    for name, element in lenses.items():
        dx, dy = offsets.get(name, (0.0, 0.0))
        element.center = [dx * 1e3, inserted[name].z * 1e3, dy * 1e3]


def _state(twin):
    """What the view depends on: energy, inserted lenses, stage and lens motors."""
    tfs = twin.tfs
    return (twin.mfx_sim.E0, tuple(lens.inserted for lens in tfs.lenses), round(tfs.translation.position, 6),
            tuple((round(lens.x.position, 6), round(lens.y.position, 6)) for lens in tfs.tfs_lenses))


def _in_ipython():
    try:
        from IPython import get_ipython
    except ImportError:
        return False
    return get_ipython() is not None


def _event_loop_running():
    """True in Jupyter/IPython after %gui qt: windows then stay live without blocking."""
    try:
        from IPython import get_ipython
    except ImportError:
        return False
    shell = get_ipython()
    return shell is not None and getattr(shell, "active_eventloop", None) in ("qt", "qt5")


class Viewer:
    """
    Two-panel window: the 3D beam line in xrtGlow on the left, and on the right
    the YAG picked in the drop-down, as the operator sees it. The image comes
    from Matt's wavefront model (default, the same as SimCamera) or from the
    ray trace, picked in the second drop-down.

    It follows the twin: every second it checks whether energy, lenses, stage or
    motors changed, and redraws if so. Use glow(twin) to open one.
    """

    def __init__(self, twin, yag="DG2_YAG", mode="wavefront", nrays=20000, zoom_on=None, scale=(2e5, 250, 2e5),
                 rotations=(0, 65, 25), centerAt=None, size=None, follow=True):
        from xrt.gui import xrtGlow as xrtglow
        from xrt.gui.commons import qt
        from matplotlib.figure import Figure

        _check_display()
        _see_through_lenses()
        _density_colors()
        _quiet_glow()
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.twin, self.nrays = twin, nrays
        if zoom_on == "stack":  # beam axis squashed only 50x, so the lens spacing shows
            scale = (1e5, 2000, 1e5)
        elif zoom_on is not None:
            scale, rotations, centerAt = (2e5, 2e5, 2e5), (-15, 0, 60), zoom_on + "_Entrance"
        self.scale, self.rotations, self.centerAt = scale, rotations, centerAt

        self.bl = build_beamline(twin, nrays)
        rr.run_process(self.bl)  # trace once so xrtGlow knows the flow
        self.glow = xrtglow.xrtGlow(self.bl.export_to_glow())
        self.glow.bl, self.bl.blViewer = self.bl, self.glow

        # right column: YAG picker and image
        self.figure = Figure(facecolor="black")
        self.canvas = qt.FigCanvas(self.figure)
        self.picker = qt.QComboBox()
        self.picker.addItems(YAGS)
        self.picker.setCurrentText(yag or "DG2_YAG")
        self.picker.currentTextChanged.connect(lambda _: self.draw_yag())
        self.mode_picker = qt.QComboBox()
        self.mode_picker.addItems(MODES)
        self.mode_picker.setCurrentText(mode)
        self.mode_picker.currentTextChanged.connect(lambda _: self.draw_yag())
        right = qt.QWidget()
        column = qt.QVBoxLayout(right)
        pickers = qt.QHBoxLayout()
        pickers.addWidget(self.picker)
        pickers.addWidget(self.mode_picker)
        column.addLayout(pickers)
        column.addWidget(self.canvas)
        right.setVisible(yag is not None)
        self._show_yag = yag is not None

        self.window = qt.QSplitter(qt.Horizontal)
        self.window.addWidget(self.glow)
        self.window.addWidget(right)
        self.window.setWindowTitle("MFX Digital Twin")
        if size is not None:  # size of the 3D view in pixels (+450 for xrtGlow's side panel)
            self.window.resize(size[0] + 450 + (size[1] if yag else 0), size[1])
            self.glow.canvasSplitter.setSizes([size[0], 450])
            self.window.setSizes([size[0] + 450, size[1] if yag else 0])
        else:
            self.window.resize(2000, 900)
            self.window.setSizes([1400, 600])
        self.window.show()
        self._style()
        self.draw_yag()

        self._last = _state(twin)
        self.timer = qt.QTimer()
        self.timer.timeout.connect(self.refresh)
        if follow:
            self.timer.start(1000)

    @property
    def yag(self):
        return self.picker.currentText() if self._show_yag else None

    @_cosmetic
    def _style(self):
        """Our default look: surfaces, labels, no grid, camera angle and zoom."""
        self._decorate()
        glow, widget = self.glow, self.glow.customGlWidget
        lenses = [e for e in self.bl.elements if isinstance(e, roe.OE)]
        rx, ry, rz = self.rotations
        widget.rotations = np.float32([[rx, 1, 0, 0], [ry, 0, 1, 0], [rz, 0, 0, 1]])
        widget.updateQuats()
        glow.updateRotationFromGL(widget.rotations)
        glow.updateScaleFromGL(list(self.scale))
        center = self.centerAt
        if center is None:
            inserted = [e.name for e in lenses if e.name.startswith("tfs_")]
            center = inserted[len(inserted) // 2] + "_Entrance" if inserted else "DG2_YAG"
        glow.centerEl(center)
        widget.glDraw()

    @_cosmetic
    def _decorate(self):
        """Surfaces, labels, no grid; leaves the camera alone."""
        from xrt.gui.commons import qt

        glow, bl = self.glow, self.bl
        glow.gridPanel.setChecked(False)  # no grid box around the beam line
        root = glow.segmentsModelRoot
        root.child(0, 2).setCheckState(qt.Checked)  # "Surface" for all elements
        for row in range(1, root.rowCount()):  # "Label" for everything, once per lens
            name = root.child(row, 0).text()
            if not name.endswith("_Exit") and name != "source":
                root.child(row, 3).setCheckState(qt.Checked)
        widget = glow.customGlWidget
        # YAG names above, slit and mirror names higher up, lens names below and staggered
        widget.label_offsets = {}
        lenses = [e for e in bl.elements if isinstance(e, roe.OE)]
        for e in bl.elements:
            if isinstance(e, rsc.Screen):
                widget.label_offsets[e.name] = (0, 0, 1.3)
            elif isinstance(e, ra.RectangularAperture):
                widget.label_offsets[e.name] = (0, 0, 1.9)
        for i, e in enumerate(lenses):
            widget.label_offsets[e.name] = (0, 0, -1.3 - 0.3 * i)
        widget.populateVerticesArray(root)
        widget.glDraw()

    def refresh(self, force=False):
        """Redraw if the twin changed (or always with force=True)."""
        state = _state(self.twin)
        if state == self._last and not force:
            return
        if state[:2] != self._last[:2]:  # energy or inserted lenses: new beam line
            self.bl = build_beamline(self.twin, self.nrays)
            rr.run_process(self.bl)
            self.glow.bl, self.bl.blViewer = self.bl, self.glow
            self.glow.updateOEsList(self.bl.export_to_glow())
            self._decorate()  # keep the camera where it is
        else:
            update_beamline(self.bl, self.twin)
            self.bl.propagate_flow()
            self.glow.updateOEsList(self.bl.export_to_glow())
            self.glow.customGlWidget.glDraw()
        self._last = state
        self.draw_yag()

    @property
    def mode(self):
        return self.mode_picker.currentText()

    def draw_yag(self):
        if self.yag is None:
            return
        fov = getattr(self.twin.beamline, self.yag).FOV * 1e6  # um, same field of view in both modes
        if self.mode == "wavefront":
            with np.errstate(invalid="ignore", divide="ignore"):  # Matt's lineouts divide by 0 on empty YAGs
                self.twin.propagate()
            ppm = getattr(self.twin.beamline, self.yag)
            image = np.flipud(ppm.profile)
            extent = np.array([ppm.x.min(), ppm.x.max(), ppm.y.min(), ppm.y.max()]) * 1e6
        else:  # histogram of the rays hitting the screen, in its local x (horizontal), z (vertical)
            beam = self.bl.beamsDict[self.yag]
            good = (beam.state == 1) | (beam.state == 2)
            edges = np.linspace(-fov / 2, fov / 2, 129)
            counts, _, _ = np.histogram2d(beam.z[good] * 1e3, beam.x[good] * 1e3, bins=[edges, edges],
                                          weights=(beam.Jss + beam.Jpp)[good])
            image = np.flipud(counts)
            extent = [-fov / 2, fov / 2, -fov / 2, fov / 2]
        self.figure.clear()
        ax = self.figure.add_axes([0.15, 0.1, 0.8, 0.8])
        ax.imshow(image, extent=extent, cmap="gnuplot", aspect="equal")
        ax.set_title(self.yag, color="white")
        if not image.any():
            ax.text(0.5, 0.5, "beam outside the field of view", color="white", ha="center", transform=ax.transAxes)
        ax.set_xlabel("x (um)", color="white")
        ax.set_ylabel("y (um)", color="white")
        ax.tick_params(colors="white")
        self.canvas.draw()

    def grab(self):
        """Current 3D view (and YAG image, if shown) as one PIL image."""
        import io

        from PIL import Image
        from xrt.gui.commons import qt

        widget = self.glow.customGlWidget
        widget.glDraw()
        widget.glDraw()  # grabFrameBuffer returns the frame drawn before the last one
        buffer = qt.QtCore.QBuffer()
        buffer.open(qt.QtCore.QIODevice.ReadWrite)
        widget.grabFrameBuffer().save(buffer, "PNG")
        frame = Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGB")
        if self.yag is None:
            return frame
        self.canvas.draw()
        panel = Image.fromarray(np.asarray(self.canvas.buffer_rgba())[..., :3])
        panel = panel.resize((round(panel.width * frame.height / panel.height), frame.height))
        both = Image.new("RGB", (frame.width + panel.width, frame.height))
        both.paste(frame, (0, 0))
        both.paste(panel, (frame.width, 0))
        return both

    def exec(self):
        """Run the window until it is closed."""
        self.app.exec_()


def glow(twin, yag="DG2_YAG", mode="wavefront", nrays=20000, zoom_on=None, block=None, **kwargs):
    """
    Open the two-panel viewer: 3D beam line on the left, `yag` on the right
    (pick another one in the drop-down; yag=None for 3D only). The YAG image
    comes from Matt's wavefront model or, with mode="ray trace", from the rays
    in the 3D view; switch in the second drop-down.

    In a script it blocks until the window is closed. In Jupyter, run
    `%gui qt` first: the window then stays open while you keep working, and
    redraws within a second when you move motors, insert lenses or change energy.

    The default view shows the transfocator and the YAGs, with the beam axis y
    squashed 800x relative to x and z, so lenses 75 mm apart look stacked.
    zoom_on="stack" shows only the inserted TFS lenses, squashed 50x, so their
    spacing is visible. zoom_on="tfs_06" shows one inserted lens at true scale.
    Change the view with the mouse or xrtGlow's side panel.
    """
    viewer = Viewer(twin, yag=yag, mode=mode, nrays=nrays, zoom_on=zoom_on, **kwargs)
    if block if block is not None else not _event_loop_running():
        if _in_ipython():
            print("Tip: run %gui qt first to keep using the notebook while the window is open.")
        viewer.exec()
    else:
        _open_viewers.append(viewer)
    return viewer


def movie(twin, scan, path="tfs_movie.gif", fps=3, yag=None, nrays=10000, size=(1200, 800), **kwargs):
    """
    Record a GIF of a scan. `scan(tfs)` is a generator that moves motors with
    the usual tfs API and yields once per frame, e.g.

        def scan(tfs):
            for x in np.linspace(-0.1, 0.1, 21):
                tfs.tfs_06.x.mv(x)
                yield

        movie(twin, scan, "tfs_06_x.gif", yag="DG2_YAG")

    With yag=..., each frame also shows that YAG next to the 3D view
    (mode="wavefront" or "ray trace", as in glow).
    Lenses can move (x/y motors, stage) but not be inserted or removed during
    the scan. The window opens, plays the scan and closes by itself.
    `size` is the size of the 3D view in pixels. kwargs as for glow().
    """
    from xrt.gui.commons import qt

    viewer = Viewer(twin, yag=yag, nrays=nrays, size=size, follow=False, **kwargs)
    frames = []

    def record():
        for _ in scan(twin.tfs):
            viewer.refresh(force=True)
            frames.append(viewer.grab())
        viewer.window.close()
        viewer.app.quit()

    qt.QTimer.singleShot(500, record)
    viewer.exec()
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=1000 / fps, loop=0)
    print(f"Saved {len(frames)} frames to {path}")
    return path


if __name__ == "__main__":
    # python -m tfs_twin.xrt_view [energy_eV]
    import sys

    from .twin import DigitalTwin

    twin = DigitalTwin(float(sys.argv[1]) if len(sys.argv) > 1 else 9500, N=256, seed=3)
    twin.tfs.focus_at(energy_eV=twin.mfx_sim.E0, wait=True)
    glow(twin)
