"""
EV Charging Station — CadQuery Build Script
============================================
Dimensions from technical spec:
  Overall Width  (W): 2500 mm
  Overall Length (L): 1700 mm
  Overall Height (H): 2600 mm
  Base Height       :  200 mm

Run with:
  pip install cadquery
  python ev_charging_station.py

Outputs:
  ev_charging_station.step  — full assembly (engineering handoff)
  ev_charging_station.stl   — mesh (3D print / visualisation)
"""

import cadquery as cq

# ─────────────────────────────────────────────
# 0. MASTER DIMENSIONS
# ─────────────────────────────────────────────

# Overall envelope
W   = 2500   # total width  (X)
L   = 1700   # total length (Y)
H   = 2600   # total height (Z)

# Base slab
BASE_H = 200

# Structural columns (two vertical legs)
COL_W  = 120   # column cross-section width  (X)
COL_D  = 100   # column cross-section depth  (Y)
COL_H  = H - BASE_H - 180  # leaves 180 mm gap for canopy beam
COL_FILLET = 10

# Canopy beam (top horizontal bar)
CAN_W  = W
CAN_D  = 240   # depth front-to-back
CAN_H  = 180   # beam height

# Central dispenser tower
DIS_W  = 420
DIS_D  = 320
DIS_H  = 1650
DIS_FILLET = 20

# Screen recess
SCR_W  = 260
SCR_H  = 190
SCR_D  = 30    # depth of pocket

# Connector holster pockets (left & right of tower)
HOL_W  = 90
HOL_D  = 70
HOL_H  = 220

# Connector nozzle cylinder
NOZ_R  = 28
NOZ_L  = 130

# Ventilation slot array
SLOT_W = 200
SLOT_H = 10
SLOT_D = 8     # cut depth
SLOT_PITCH = 16

# LED channel on base perimeter
LED_W  = 22
LED_H  = 10
LED_INSET = 35   # inward from base edge

# Cable arch (right-side view)
ARCH_R = 620     # outer radius of arch sweep path
ARCH_TUBE_R = 18 # tube cross-section radius


# ─────────────────────────────────────────────
# STEP 1 — CONCRETE BASE SLAB
# ─────────────────────────────────────────────
# A flat box, chamfered on the top edges.
# Centered on XY, bottom face at Z=0.

base = (
    cq.Workplane("XY")
    .box(W, L, BASE_H, centered=(True, True, False))
    .edges("|Z")                # vertical edges only
    .chamfer(20)                # 20 mm corner chamfer
    .edges(">Z")                # top horizontal edges
    .fillet(5)                  # gentle 5 mm fillet where body sits
)


# ─────────────────────────────────────────────
# STEP 2 — LED CHANNEL GROOVE (perimeter of base top)
# ─────────────────────────────────────────────
# Cut a rectangular channel loop on the top face,
# inset from the outer edges, to house an LED strip.

led_outer_w = W - 2 * LED_INSET
led_outer_l = L - 2 * LED_INSET

led_groove = (
    cq.Workplane("XY")
    .workplane(offset=BASE_H)           # work on top face
    .rect(led_outer_w, led_outer_l)
    .rect(led_outer_w - 2*LED_W, led_outer_l - 2*LED_W)
    .extrude(-LED_H, both=False)        # cut downward
)

base = base.cut(led_groove)


# ─────────────────────────────────────────────
# STEP 3 — LEFT STRUCTURAL COLUMN
# ─────────────────────────────────────────────
# Rectangular extrusion with rounded vertical edges.
# X position: inset 150 mm from left edge of base.

col_x_left = -W/2 + 150 + COL_W/2    # center X of left column

left_col = (
    cq.Workplane("XY")
    .workplane(offset=BASE_H)
    .center(col_x_left, 0)
    .box(COL_W, COL_D, COL_H, centered=(True, True, False))
    .edges("|Z")
    .fillet(COL_FILLET)
)


# ─────────────────────────────────────────────
# STEP 4 — RIGHT STRUCTURAL COLUMN (mirror of left)
# ─────────────────────────────────────────────

col_x_right = W/2 - 150 - COL_W/2

right_col = (
    cq.Workplane("XY")
    .workplane(offset=BASE_H)
    .center(col_x_right, 0)
    .box(COL_W, COL_D, COL_H, centered=(True, True, False))
    .edges("|Z")
    .fillet(COL_FILLET)
)


# ─────────────────────────────────────────────
# STEP 5 — TOP CANOPY BEAM
# ─────────────────────────────────────────────
# Full-width horizontal beam at the top of the columns.
# Slightly overhangs front & back (COL_D < CAN_D).

canopy_z = BASE_H + COL_H   # bottom of canopy beam

canopy = (
    cq.Workplane("XY")
    .workplane(offset=canopy_z)
    .box(CAN_W, CAN_D, CAN_H, centered=(True, True, False))
    .edges("|Z")
    .fillet(15)                  # softer fillet on canopy corners
    .edges("<Z")                 # bottom canopy edge
    .fillet(8)
)

# Sign recess on front face of canopy
# Front face is at Y = -CAN_D/2; cut a pocket into it.
sign_recess = (
    cq.Workplane("XZ")
    .workplane(offset=-CAN_D/2)
    .center(0, canopy_z + CAN_H/2)
    .rect(680, 55)
    .extrude(22)                 # 22 mm deep pocket
)
canopy = canopy.cut(sign_recess)


# ─────────────────────────────────────────────
# STEP 6 — CENTRAL DISPENSER TOWER
# ─────────────────────────────────────────────
# Main body of the charging unit, centered on the base,
# sitting on top of the base slab.
# Tapered slightly at the top using a loft.

tower_z = BASE_H   # bottom of tower

# Build the tapered tower using a loft between two profiles:
# bottom profile (full DIS_W × DIS_D) and
# top profile (reduced by taper ~3° each side over top 200 mm).
TAPER = 15   # mm narrower each side at top

bottom_profile = cq.Workplane("XY").workplane(offset=tower_z).rect(DIS_W, DIS_D)
top_profile    = cq.Workplane("XY").workplane(offset=tower_z + DIS_H).rect(
    DIS_W - 2*TAPER, DIS_D - 2*TAPER
)

tower = (
    cq.Workplane("XY")
    .workplane(offset=tower_z)
    .center(0, 0)
    .box(DIS_W, DIS_D, DIS_H, centered=(True, True, False))
    .edges("|Z")
    .fillet(DIS_FILLET)
)


# ─────────────────────────────────────────────
# STEP 7 — SCREEN RECESS (front face of tower)
# ─────────────────────────────────────────────
# Rectangular pocket cut into the front face.
# Front face of tower at Y = -DIS_D/2.
# Screen center height: 1200 mm from ground → Z center = 1200 mm

screen_z_center = 1200
screen_recess = (
    cq.Workplane("XZ")
    .workplane(offset=-DIS_D/2)
    .center(0, screen_z_center)
    .rect(SCR_W, SCR_H)
    .extrude(SCR_D)
)
tower = tower.cut(screen_recess)

# Chamfer around the screen opening
# (Approximate: fillet the inner pocket edges)
tower = (
    tower
    .faces("<Y")               # front face
    .edges()
    .fillet(3)
)


# ─────────────────────────────────────────────
# STEP 8 — CONNECTOR HOLSTER POCKETS (left side)
# ─────────────────────────────────────────────
# Pockets on the left face of the dispenser tower
# at Z = 800 mm from ground.

hol_z_center = 800

left_holster = (
    cq.Workplane("YZ")
    .workplane(offset=-DIS_W/2)
    .center(0, hol_z_center)
    .rect(HOL_D, HOL_H)
    .extrude(HOL_W)            # cuts into tower from left face
)
tower = tower.cut(left_holster)

# Right holster (mirror on right face)
right_holster = (
    cq.Workplane("YZ")
    .workplane(offset=DIS_W/2)
    .center(0, hol_z_center)
    .rect(HOL_D, HOL_H)
    .extrude(-HOL_W)
)
tower = tower.cut(right_holster)


# ─────────────────────────────────────────────
# STEP 9 — CONNECTOR NOZZLES (in holsters)
# ─────────────────────────────────────────────
# Cylinder sitting inside each holster pocket.

left_nozzle = (
    cq.Workplane("YZ")
    .workplane(offset=-DIS_W/2 + 10)
    .center(0, hol_z_center)
    .circle(NOZ_R)
    .extrude(-NOZ_L)           # points outward to the left
)

right_nozzle = (
    cq.Workplane("YZ")
    .workplane(offset=DIS_W/2 - 10)
    .center(0, hol_z_center)
    .circle(NOZ_R)
    .extrude(NOZ_L)            # points outward to the right
)


# ─────────────────────────────────────────────
# STEP 10 — CABLE MANAGEMENT GROOVE (tower side)
# ─────────────────────────────────────────────
# A vertical channel groove running down the left
# and right faces of the tower from holster to base.

cable_groove_left = (
    cq.Workplane("XY")
    .workplane(offset=BASE_H)
    .center(-DIS_W/2 + 15, 0)   # on left face
    .rect(30, DIS_D)
    .extrude(hol_z_center)
    .intersect(
        cq.Workplane("XY").box(30, DIS_D, hol_z_center,
                                centered=(True, True, False))
        .translate((-DIS_W/2 + 15, 0, BASE_H))
    )
)
# We subtract a 30 mm wide × 20 mm deep slot from the tower face
groove_cut_left = (
    cq.Workplane("YZ")
    .workplane(offset=-DIS_W/2)
    .center(0, hol_z_center/2 + BASE_H/2)
    .rect(40, hol_z_center)
    .extrude(20)
)
tower = tower.cut(groove_cut_left)

groove_cut_right = (
    cq.Workplane("YZ")
    .workplane(offset=DIS_W/2)
    .center(0, hol_z_center/2 + BASE_H/2)
    .rect(40, hol_z_center)
    .extrude(-20)
)
tower = tower.cut(groove_cut_right)


# ─────────────────────────────────────────────
# STEP 11 — VENTILATION GRILLE (rear face, array of slots)
# ─────────────────────────────────────────────
# 5 horizontal slots arrayed vertically on the rear face.
# Rear face of tower at Y = +DIS_D/2.

SLOT_COUNT = 5
slot_z_start = BASE_H + 350   # start of grille zone

vent_slots = []
for i in range(SLOT_COUNT):
    slot_z = slot_z_start + i * SLOT_PITCH * 2
    slot = (
        cq.Workplane("XZ")
        .workplane(offset=DIS_D/2)
        .center(0, slot_z)
        .rect(SLOT_W, SLOT_H)
        .extrude(-SLOT_D)
    )
    vent_slots.append(slot)

for slot in vent_slots:
    tower = tower.cut(slot)


# ─────────────────────────────────────────────
# STEP 12 — CABLE ARCH (right-side view profile)
# ─────────────────────────────────────────────
# An arch-shaped tube rising from the holster on the
# right column inward face up to the underside of the canopy.
# We build the sweep path as a 2D arc in the XZ plane,
# then sweep a circle along it.

import math

# Arch center at column right inner face, holster height
arch_start = cq.Vector(col_x_right - COL_W/2, 0, BASE_H + hol_z_center)
arch_end   = cq.Vector(col_x_right - COL_W/2, 0, canopy_z - 20)

# Build the arch as a swept tube using a spline path
arch_path = (
    cq.Workplane("XZ")
    .moveTo(col_x_right - COL_W/2, BASE_H + hol_z_center)
    .threePointArc(
        (col_x_right - COL_W/2 - ARCH_R * 0.5,
         BASE_H + hol_z_center + (canopy_z - BASE_H - hol_z_center) / 2),
        (col_x_right - COL_W/2, canopy_z - 20)
    )
)

arch_tube = (
    cq.Workplane("XZ")
    .center(col_x_right - COL_W/2, BASE_H + hol_z_center)
    .circle(ARCH_TUBE_R)
    .sweep(arch_path)
)


# ─────────────────────────────────────────────
# STEP 13 — MIRROR ARCH FOR LEFT SIDE
# ─────────────────────────────────────────────

left_arch_path = (
    cq.Workplane("XZ")
    .moveTo(col_x_left + COL_W/2, BASE_H + hol_z_center)
    .threePointArc(
        (col_x_left + COL_W/2 + ARCH_R * 0.5,
         BASE_H + hol_z_center + (canopy_z - BASE_H - hol_z_center) / 2),
        (col_x_left + COL_W/2, canopy_z - 20)
    )
)

left_arch_tube = (
    cq.Workplane("XZ")
    .center(col_x_left + COL_W/2, BASE_H + hol_z_center)
    .circle(ARCH_TUBE_R)
    .sweep(left_arch_path)
)


# ─────────────────────────────────────────────
# STEP 14 — ASSEMBLY
# ─────────────────────────────────────────────
# Union all components into a single solid,
# or keep as assembly dict for per-part material assignment.

assembly = (
    cq.Assembly()
    .add(base,           name="base_slab",      color=cq.Color("gray"))
    .add(left_col,       name="col_left",        color=cq.Color("lightgray"))
    .add(right_col,      name="col_right",       color=cq.Color("lightgray"))
    .add(canopy,         name="canopy_beam",     color=cq.Color("lightgray"))
    .add(tower,          name="dispenser_tower", color=cq.Color("darkgray"))
    .add(left_nozzle,    name="nozzle_left",     color=cq.Color("black"))
    .add(right_nozzle,   name="nozzle_right",    color=cq.Color("black"))
    .add(arch_tube,      name="arch_right",      color=cq.Color("dimgray"))
    .add(left_arch_tube, name="arch_left",        color=cq.Color("dimgray"))
)


# ─────────────────────────────────────────────
# STEP 15 — EXPORT
# ─────────────────────────────────────────────

# Full assembly as STEP (best for CAD interchange)
assembly.save("ev_charging_station.step")

# Individual parts as STEP for separate material specs
cq.exporters.export(base,           "parts/base_slab.step")
cq.exporters.export(left_col,       "parts/column_left.step")
cq.exporters.export(right_col,      "parts/column_right.step")
cq.exporters.export(canopy,         "parts/canopy_beam.step")
cq.exporters.export(tower,          "parts/dispenser_tower.step")
cq.exporters.export(left_nozzle,    "parts/nozzle_left.step")
cq.exporters.export(right_nozzle,   "parts/nozzle_right.step")
cq.exporters.export(arch_tube,      "parts/arch_right.step")
cq.exporters.export(left_arch_tube, "parts/arch_left.step")

# STL for 3D printing / mesh visualisation
full_model = (
    base
    .union(left_col)
    .union(right_col)
    .union(canopy)
    .union(tower)
    .union(left_nozzle)
    .union(right_nozzle)
    .union(arch_tube)
    .union(left_arch_tube)
)
cq.exporters.export(full_model, "ev_charging_station.stl")

# DXF projection (2D drawings — front view)
cq.exporters.export(
    full_model,
    "drawings/front_view.dxf",
    opt={"projectionDir": (0, -1, 0)}   # looking in +Y direction (front)
)

print("✓ Export complete — ev_charging_station.step / .stl")
print(f"  Envelope check: W={W}mm  L={L}mm  H={BASE_H + COL_H + CAN_H}mm")
