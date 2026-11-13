"""
GIF of the baseline protocol (protocols/center_lenses.py) on the twin.

One frame per camera image the protocol takes: a wrapped camera records the
viewer each time get_image() is called, so the protocol runs unchanged and you
follow it step by step. Unlike xrt_view.movie(), lenses can be inserted and removed.
The protocol's camera is on DG3; the YAG shown next to the 3D view can be another one.
When the shown YAG is the camera's, each frame marks the centroid the protocol
measures (+) and its target, the lens-out reference (o). If the protocol crashes,
the frames up to the crash are still saved.

    python record_baseline_gif.py gifs/baseline_protocol.gif --seed 7 --yag DG3_YAG --frame-ms 1500
    python record_baseline_gif.py gifs/misaligned_500um.gif --misalignment 5e-4 --yag DG3_YAG
    python record_baseline_gif.py gifs/misaligned_500um_DG2.gif --misalignment 5e-4 --yag DG2_YAG --camera DG2_YAG
    %run record_baseline_gif.py baseline_protocol.gif         # from a notebook (after %gui qt)
"""
import argparse
import logging
import traceback

logging.getLogger("tfs").setLevel(logging.CRITICAL)  # mute "TFS combo may be forbidden"

from PIL import ImageDraw, ImageFont

from protocols.center_lenses import center_lenses, centroid
from tfs_twin import DigitalTwin, SimCamera
from tfs_twin.xrt_view import glow
from xrt.gui.commons import qt  # after tfs_twin.xrt_view, which stubs QtWebEngineWidgets


class RecordingCamera:
    """Wraps a camera: each get_image() also records a frame of the viewer."""

    def __init__(self, camera, viewer, twin, lenses, width=1600):
        self.camera, self.viewer, self.twin, self.width = camera, viewer, twin, width
        self.names = [twin._name(lens) for lens in lenses]
        self.frames = []
        self.target = None  # centroid of the last lens-out image: what the protocol aims for

    def get_image(self):
        image = self.camera.get_image()
        measured = centroid(image.copy())  # same function the protocol uses
        if not any(lens.inserted for lens in self.twin.tfs.tfs_lenses):
            self.target = measured  # lens-out reference image
        self.snap(f"center_lenses: camera image {len(self.frames)} (camera on {self.camera.yag})", measured)
        return image

    def _um(self, col, row):
        """Camera pixel (col, row) to YAG coordinates in um, as drawn by the viewer."""
        ppm = getattr(self.twin.beamline, self.camera.yag)
        nrow, ncol = ppm.profile.shape
        x = ppm.x.min() + col * (ppm.x.max() - ppm.x.min()) / (ncol - 1)
        y = ppm.y.min() + row * (ppm.y.max() - ppm.y.min()) / (nrow - 1)
        return x * 1e6, y * 1e6

    def snap(self, title, measured=None):
        self.viewer.refresh(force=True)
        if self.viewer.yag == self.camera.yag and self.viewer.figure.axes:
            ax = self.viewer.figure.axes[0]
            if self.target is not None:
                ax.plot(*self._um(*self.target), "o", ms=14, mfc="none", mec="lime", mew=2.5)
            if measured is not None:
                ax.plot(*self._um(*measured), "+", ms=18, color="white", mew=2.5)
        frame = self.viewer.grab()
        frame = frame.resize((self.width, round(frame.height * self.width / frame.width)))
        lines = [title]
        for name, (dx, dy) in self.twin.lens_offsets().items():  # hidden truth: shown, never used by the protocol
            if name in self.names:
                state = "in " if getattr(self.twin.tfs, name).inserted else "out"
                lines.append(f"{name} {state}  dx {dx * 1e6:+7.1f} um  dy {dy * 1e6:+7.1f} um")
        if self.viewer.yag == self.camera.yag:
            lines.append("+ measured centroid   o target (lens-out reference)")
        draw = ImageDraw.Draw(frame)
        draw.multiline_text((20, 20), "\n".join(lines), fill="white", font=ImageFont.load_default(size=22), spacing=8)
        self.frames.append(frame)

    def stamp(self, text):
        """Repeat the last frame with `text` in red, e.g. after a crash."""
        frame = self.frames[-1].copy()
        ImageDraw.Draw(frame).text((20, frame.height - 60), text, fill="red", font=ImageFont.load_default(size=28))
        self.frames.append(frame)


def record_baseline(path="baseline_protocol.gif", seed=3, yag="DG2_YAG", camera_yag="DG3_YAG", frame_ms=700,
                    misalignment=50e-6, E0=9500, noise_seed=None):
    """
    `yag`: shown next to the 3D view. `camera_yag`: where the protocol's camera is.
    `frame_ms`: how long each frame shows; the first and last frames stay up longer.
    `misalignment`: hidden lens offsets, within +/- this many metres (as in DigitalTwin).
    `E0`: photon energy in eV; lenses are chosen with focus_at for that energy.
    `noise_seed`: camera shot-noise seed, to repeat a run exactly (None: different every time).
    """
    twin = DigitalTwin(E0, N=256, misalignment=misalignment, seed=seed)
    tfs = twin.tfs
    tfs.focus_at(energy_eV=E0, wait=True)
    lenses = [lens for lens in tfs.tfs_lenses if lens.inserted]

    viewer = glow(twin, yag=yag, nrays=10000, size=(1200, 800), follow=False, block=False)
    camera = RecordingCamera(SimCamera(twin, camera_yag, noise=True, seed=noise_seed), viewer, twin, lenses)
    errors = []

    def record():
        try:
            camera.snap(f"before ({E0 / 1e3:g} keV)")
            center_lenses(tfs, camera, lenses=lenses)
            camera.snap(f"after center_lenses ({E0 / 1e3:g} keV)")
        except Exception as error:  # noqa: BLE001  (an exception inside a Qt callback would abort Python)
            traceback.print_exc()
            errors.append(error)
            if camera.frames:
                camera.stamp(f"protocol crashed: {type(error).__name__}: {str(error)[:60]}")
        finally:
            viewer.window.close()
            viewer.app.quit()

    qt.QTimer.singleShot(500, record)
    viewer.exec()

    frames = camera.frames
    durations = [3 * frame_ms] + [frame_ms] * (len(frames) - 2) + [5 * frame_ms]  # hold on the first and last
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations, loop=0)
    print(f"Saved {len(frames)} frames to {path}" + (" (protocol crashed)" if errors else ""))
    twin.report()
    return twin


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GIF of the baseline protocol on the twin.")
    parser.add_argument("path", nargs="?", default="baseline_protocol.gif")
    parser.add_argument("--seed", type=int, default=3, help="hidden misalignment (default 3)")
    parser.add_argument("--yag", default="DG2_YAG", help="YAG shown next to the 3D view (default DG2_YAG)")
    parser.add_argument("--frame-ms", type=int, default=700, help="time per frame in ms (default 700)")
    parser.add_argument("--misalignment", type=float, default=50e-6, help="lens misalignment in m (default 50e-6)")
    parser.add_argument("--camera", default="DG3_YAG", help="YAG the protocol's camera reads (default DG3_YAG)")
    parser.add_argument("--E0", type=float, default=9500, help="photon energy in eV (default 9500)")
    parser.add_argument("--noise-seed", type=int, default=None, help="camera noise seed, to repeat a run exactly")
    args = parser.parse_args()
    record_baseline(args.path, seed=args.seed, yag=args.yag, camera_yag=args.camera, frame_ms=args.frame_ms,
                    misalignment=args.misalignment, E0=args.E0, noise_seed=args.noise_seed)
