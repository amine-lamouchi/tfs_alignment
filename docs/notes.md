# Notes

## Background

* **pcdshub/mfx#233 (EXAFS, Oct 2025).** `tfs.track_focus()` keeps the focus
  during an energy scan by moving the z stage. It was tested on
  `tfs/sim_transfocator.py`, a fake `Transfocator` that copies lens radii and z
  from the real one. `tfs_twin.motor_sim` is the same idea, but works offline.
* **Matt's MFX model** (`lcls_beamline_toolbox/models/mfx.py`, example in
  `scripts/mfx_test.ipynb`) shows the beam on each YAG for a lens configuration.
* **[MFX Confluence](https://confluence.slac.stanford.edu/display/MFX/MFX@LCLS+Home), Align CRLs**, the current manual procedure:
  1. attenuate the beam;
  2. move the lens in x until the beam clips its edge and you can see the aperture;
  3. center the lens with the y motor;
  4. find the aperture edge on the other side in x;
  5. center x between the two edges.

  Then scan the z stage for the smallest spot on the YAG (`tfs/transfocator_scan.py`).

## Tasks

1. Automate *Align CRLs* in `protocols/`. In the model the aperture shows as a
   dark ring on the YAG (see `img/aperture_clipping.png`), while total intensity
   barely changes, so detect the edge from the image.
2. Turn "rings centered and concentric" into a number computed from one image.
3. Automate the z-stage focus scan.
4. Combine them into one procedure, and test it over seeds, energies, noise and
   larger misalignments.
5. With staff: calibrate the twin against the instrument (YAG positions, camera
   orientation, motor units and signs, current lens radii).

Protocols should only use `tfs` and `camera.get_image()`. Grade them with
`twin.report()` / `twin.lens_offsets()`, never use those inside a protocol.

## Things to know

* **Units** follow the control system: lens z in m from the source, radius in
  µm, stage and lens x/y in mm. Matt's model uses LCLS z = tfs z + 624.645 m.
* **What the twin changes in Matt's model:** source position, IP position,
  prefocus position and lens apertures are set to match `tfs`. Lens apertures
  use 2R₀ = 63.2 µm·√R, fit to the Confluence table.
* **Stage:** moves the 9 TFS lenses. The 3 prefocus lenses (XRT, 36 m upstream)
  don't move with it and have no x/y motors.
* **Focus:** `tfs` (pcdscalc) and Matt's model (CXRO table) use different Be
  refractive indices. The focus differs by about 3 mm at 9.5 keV.
* **Outside the aperture:** light goes through about 1 mm of Be unfocused
  (`multi_beam=True`), which is where the rings come from. The square edge
  of that beam on DG2 is the simulation grid, not real.
* **Not modelled:** thick lenses, shape errors, pointing jitter, YAG
  saturation. A static pointing error can be set with
  `twin.mfx_sim.undulator_pointing(ax, ay)`.
* **Old numbers:** `find_solution` was fixed on 2025-11-01, so lens combos and
  focus offsets quoted in mfx#233 and on Confluence before that don't reproduce.
* **`track_focus`** holds the TFS focal length, not the focus position. In the
  twin the focus drifts by about 13 mm from 7050 to 7150 eV.

## Safety

The old `tfs/sim_transfocator.py` subclasses the real `MFXLens`, so each
simulated lens still has **real** x/y motors (`MFX:TFS:MMS:03..20`) and a real
`:REQ_FOCUS`. On the controls network, moving a simulated lens could move the
real one. The twin's lenses are fully fake, and `motor_sim.py` refuses to load
if any real PV is left. The upstream fix is in
`mfx-sim_transfocator-safety.patch`.
