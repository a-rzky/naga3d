"""
Kepala Naga 3D - dibuat prosedural dengan Blender Python API.

Jalankan:
    blender --background --python build_naga.py -- [--render] [--samples N] [--size PX]

Hasil (di folder yang sama dengan script ini):
    naga_head.blend   file Blender yang bisa diedit
    naga_head.glb     ekspor glTF (untuk web / game engine)
    render_*.png      gambar pratinjau (jika --render)

Orientasi: moncong menghadap -Y, atas = +Z, simetri pada sumbu X.
"""
import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.dirname(os.path.abspath(__file__))


def arg_val(flag, default):
    return type(default)(ARGS[ARGS.index(flag) + 1]) if flag in ARGS else default


# ---------------------------------------------------------------- utilitas
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
COL = scene.collection

root = bpy.data.objects.new("Naga_Head", None)
COL.objects.link(root)


def add_obj(name, data, parent=root, mat=None):
    ob = bpy.data.objects.new(name, data)
    COL.objects.link(ob)
    ob.parent = parent
    if mat is not None:
        ob.data.materials.append(mat)
    return ob


def ring_at(rings, y):
    """Interpolasi linear parameter penampang pada posisi y."""
    rs = sorted(rings, key=lambda r: r["y"])
    if y <= rs[0]["y"]:
        return dict(rs[0])
    for a, b in zip(rs, rs[1:]):
        if a["y"] <= y <= b["y"]:
            t = (y - a["y"]) / (b["y"] - a["y"])
            return {k: a[k] + (b[k] - a[k]) * t for k in a}
    return dict(rs[-1])


def loft(name, rings, mat, nseg=24, parent=root, levels=2):
    """Bentuk organik dari deretan penampang (y, z, w, top, bot)."""
    bm = bmesh.new()
    loops = []
    for r in rings:
        e = r.get("e", 2.0)
        loop = []
        for i in range(nseg):
            a = 2 * math.pi * i / nseg
            c, s = math.cos(a), math.sin(a)
            x = r["w"] * math.copysign(abs(c) ** (2 / e), c)
            h = r["top"] if s >= 0 else r["bot"]
            z = r["z"] + h * math.copysign(abs(s) ** (2 / e), s)
            loop.append(bm.verts.new((x, r["y"], z)))
        loops.append(loop)
    for la, lb in zip(loops, loops[1:]):
        for i in range(nseg):
            j = (i + 1) % nseg
            bm.faces.new((la[i], la[j], lb[j], lb[i]))
    for loop, r in ((loops[0], rings[0]), (loops[-1], rings[-1])):
        c = bm.verts.new((0, r["y"], r["z"]))
        for i in range(nseg):
            bm.faces.new((loop[i], loop[(i + 1) % nseg], c))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = add_obj(name, me, parent, mat)
    m = ob.modifiers.new("Subsurf", "SUBSURF")
    m.levels = levels
    m.render_levels = levels + 1
    return ob


def tube(name, splines, mat, parent=root, res=6):
    """Tabung meruncing mengikuti kurva. Titik = (x, y, z, radius)."""
    if not isinstance(splines[0][0], (tuple, list)):
        splines = [splines]
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 1.0
    cu.bevel_resolution = res
    cu.use_fill_caps = True
    cu.resolution_u = 16
    for pts in splines:
        sp = cu.splines.new("NURBS")
        sp.points.add(len(pts) - 1)
        for p, (x, y, z, r) in zip(sp.points, pts):
            p.co = (x, y, z, 1.0)
            p.radius = r
        sp.order_u = min(4, len(pts))
        sp.use_endpoint_u = True
    return add_obj(name, cu, parent, mat)


def mirror_pts(pts):
    return [(-x, y, z, r) for x, y, z, r in pts]


def tube_pair(name, pts, mat, parent=root):
    tube(name + "_L", pts, mat, parent)
    tube(name + "_R", mirror_pts(pts), mat, parent)


_cone = None


def cone_mesh():
    global _cone
    if _cone is None:
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=20,
                              radius1=1.0, radius2=0.0, depth=1.0)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, 0.5))
        _cone = bpy.data.meshes.new("Cone")
        bm.to_mesh(_cone)
        bm.free()
        for p in _cone.polygons:
            p.use_smooth = True
    return _cone


def spike(name, loc, scale, rot_x, mat, parent=root, rot_y=0.0):
    """Kerucut: alas di loc, tinggi scale.z, dimiringkan rot_x (radian)."""
    me = cone_mesh().copy()
    ob = add_obj(name, me, parent, mat)
    ob.location = loc
    ob.scale = scale
    ob.rotation_euler = (rot_x, rot_y, 0)
    return ob


def sphere(name, loc, radius, mat, parent=root, scale=(1, 1, 1)):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=radius)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = add_obj(name, me, parent, mat)
    ob.location = loc
    ob.scale = scale
    return ob


# ---------------------------------------------------------------- material
def principled(name, color, rough=0.5, metallic=0.0, **extra):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, 1)
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    for k, v in extra.items():
        b.inputs[k].default_value = v
    return mat, b


def make_skin():
    mat, b = principled("Kulit_Sisik", (0.03, 0.30, 0.16), rough=0.38)
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    tc = N.new("ShaderNodeTexCoord")
    vor = N.new("ShaderNodeTexVoronoi")
    vor.feature = "F1"
    vor.inputs["Scale"].default_value = 11.0
    vor.inputs["Randomness"].default_value = 0.75
    L.new(tc.outputs["Object"], vor.inputs["Vector"])

    # gradasi perut (emas) -> punggung (hijau zamrud)
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["Object"], sep.inputs[0])
    mr = N.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = -0.55
    mr.inputs["From Max"].default_value = 0.05
    L.new(sep.outputs["Z"], mr.inputs["Value"])
    grad = N.new("ShaderNodeValToRGB")
    e = grad.color_ramp.elements
    e[0].position, e[0].color = 0.0, (0.80, 0.52, 0.14, 1)
    e[1].position, e[1].color = 1.0, (0.015, 0.24, 0.13, 1)
    mid = grad.color_ramp.elements.new(0.55)
    mid.color = (0.05, 0.42, 0.22, 1)
    L.new(mr.outputs["Result"], grad.inputs["Fac"])

    # tiap sisik: terang di tengah, gelap di tepi
    shade = N.new("ShaderNodeValToRGB")
    s = shade.color_ramp.elements
    s[0].position, s[0].color = 0.0, (1.25, 1.25, 1.25, 1)
    s[1].position, s[1].color = 0.75, (0.25, 0.25, 0.25, 1)
    L.new(vor.outputs["Distance"], shade.inputs["Fac"])
    mul = N.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    L.new(grad.outputs["Color"], mul.inputs[6])
    L.new(shade.outputs["Color"], mul.inputs[7])
    L.new(mul.outputs[2], b.inputs["Base Color"])

    bump = N.new("ShaderNodeBump")
    bump.invert = True
    bump.inputs["Strength"].default_value = 0.9
    bump.inputs["Distance"].default_value = 0.06
    L.new(vor.outputs["Distance"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Coat Weight"].default_value = 0.15
    b.inputs["Coat Roughness"].default_value = 0.2
    return mat


def make_horn():
    mat, b = principled("Tanduk", (0.78, 0.66, 0.45), rough=0.42)
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    tc = N.new("ShaderNodeTexCoord")
    wave = N.new("ShaderNodeTexWave")
    wave.bands_direction = "Y"
    wave.inputs["Scale"].default_value = 5.0
    wave.inputs["Distortion"].default_value = 1.5
    L.new(tc.outputs["Object"], wave.inputs["Vector"])
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.45
    bump.inputs["Distance"].default_value = 0.04
    L.new(wave.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], b.inputs["Normal"])
    ramp = N.new("ShaderNodeValToRGB")
    r = ramp.color_ramp.elements
    r[0].color = (0.55, 0.40, 0.22, 1)
    r[1].color = (0.90, 0.80, 0.58, 1)
    L.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    L.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return mat


M_SKIN = make_skin()
M_HORN = make_horn()
M_TOOTH, _ = principled("Gigi", (0.92, 0.88, 0.76), rough=0.25)
M_GOLD, _ = principled("Emas", (0.95, 0.62, 0.16), rough=0.3, metallic=0.85)
M_TONGUE, _ = principled("Lidah", (0.65, 0.04, 0.05), rough=0.3)
M_DARK, _ = principled("Gelap", (0.01, 0.01, 0.01), rough=0.15)
M_EYE, _eb = principled("Mata", (1.0, 0.45, 0.02), rough=0.1)
_eb.inputs["Emission Color"].default_value = (1.0, 0.42, 0.02, 1)
_eb.inputs["Emission Strength"].default_value = 2.5
_eb.inputs["Coat Weight"].default_value = 1.0

# ---------------------------------------------------------------- kepala
HEAD = [  # dari pangkal leher ke ujung moncong
    dict(y=3.60, z=-1.10, w=0.70, top=0.70, bot=0.75),
    dict(y=2.60, z=-0.55, w=0.78, top=0.76, bot=0.80),
    dict(y=1.70, z=-0.08, w=0.86, top=0.80, bot=0.85),
    dict(y=1.00, z=0.25, w=0.96, top=0.76, bot=0.75),
    dict(y=0.50, z=0.35, w=1.00, top=0.74, bot=0.45),
    dict(y=0.00, z=0.35, w=0.90, top=0.72, bot=0.35),
    dict(y=-0.40, z=0.30, w=0.72, top=0.50, bot=0.30),
    dict(y=-1.00, z=0.25, w=0.56, top=0.36, bot=0.25),
    dict(y=-1.60, z=0.22, w=0.50, top=0.34, bot=0.22),
    dict(y=-2.00, z=0.22, w=0.54, top=0.44, bot=0.22),
    dict(y=-2.35, z=0.20, w=0.42, top=0.32, bot=0.18),
    dict(y=-2.52, z=0.17, w=0.20, top=0.15, bot=0.10),
]
loft("Kepala", HEAD, M_SKIN)

# ---------------------------------------------------------------- rahang bawah
HINGE = Vector((0, 0.70, -0.05))
JAW_OPEN = math.radians(17)
JAW = [  # koordinat lokal terhadap engsel
    dict(y=0.45, z=-0.28, w=0.74, top=0.28, bot=0.40),
    dict(y=-0.30, z=-0.20, w=0.86, top=0.20, bot=0.42),
    dict(y=-1.10, z=-0.17, w=0.68, top=0.14, bot=0.32),
    dict(y=-1.80, z=-0.15, w=0.50, top=0.12, bot=0.25),
    dict(y=-2.50, z=-0.13, w=0.45, top=0.11, bot=0.22),
    dict(y=-2.95, z=-0.12, w=0.37, top=0.10, bot=0.20),
    dict(y=-3.12, z=-0.10, w=0.18, top=0.06, bot=0.10),
]
jaw = loft("Rahang_Bawah", JAW, M_SKIN)
jaw.location = HINGE
jaw.rotation_euler = (JAW_OPEN, 0, 0)

# ---------------------------------------------------------------- gigi
ys = [-2.36, -2.12, -1.86, -1.60, -1.34, -1.08, -0.82, -0.58]
lens = [0.20, 0.46, 0.22, 0.26, 0.20, 0.24, 0.18, 0.15]
for i, (y, ln) in enumerate(zip(ys, lens)):
    r = ring_at(HEAD, y)
    for sx in (1, -1):
        spike(f"Gigi_Atas_{i}_{'L' if sx > 0 else 'R'}",
              (sx * r["w"] * 0.78, y, r["z"] - r["bot"] * 0.55),
              (0.055 + ln * 0.06, 0.055 + ln * 0.06, ln),
              math.pi + 0.08, M_TOOTH, rot_y=sx * 0.10)

ys = [-2.98, -2.74, -2.46, -2.20, -1.94, -1.68, -1.42, -1.16]
lens = [0.18, 0.36, 0.20, 0.22, 0.24, 0.18, 0.20, 0.15]
for i, (y, ln) in enumerate(zip(ys, lens)):
    r = ring_at(JAW, y)
    for sx in (1, -1):
        spike(f"Gigi_Bawah_{i}_{'L' if sx > 0 else 'R'}",
              (sx * r["w"] * 0.76, y, r["z"] + r["top"] * 0.5),
              (0.05 + ln * 0.06, 0.05 + ln * 0.06, ln),
              -0.06, M_TOOTH, parent=jaw, rot_y=sx * 0.08)

# ---------------------------------------------------------------- lidah bercabang
tube("Lidah", [
    [(0, -0.4, -0.02, 0.13), (0, -1.3, 0.02, 0.12), (0, -2.2, 0.10, 0.09),
     (0, -2.9, 0.30, 0.055), (0, -3.3, 0.36, 0.045)],
    [(0, -3.25, 0.355, 0.04), (0.07, -3.5, 0.40, 0.03),
     (0.16, -3.75, 0.52, 0.004)],
    [(0, -3.25, 0.355, 0.04), (-0.07, -3.5, 0.40, 0.03),
     (-0.16, -3.75, 0.52, 0.004)],
], M_TONGUE, parent=jaw)

# ---------------------------------------------------------------- tanduk
tube_pair("Tanduk_Utama", [
    (0.48, 0.70, 0.78, 0.21), (0.70, 1.30, 1.42, 0.18),
    (0.95, 2.20, 1.80, 0.13), (1.05, 3.10, 1.78, 0.075),
    (0.92, 3.80, 2.15, 0.006)], M_HORN)
tube_pair("Tanduk_Samping", [
    (0.74, 0.90, 0.52, 0.14), (1.15, 1.45, 0.66, 0.11),
    (1.42, 2.15, 0.90, 0.06), (1.40, 2.75, 1.25, 0.006)], M_HORN)

# sirip / duri pipi
for i, (z0, dz, ln) in enumerate([(0.15, 0.10, 1.0), (-0.10, -0.12, 0.85),
                                  (-0.32, -0.34, 0.65)]):
    tube_pair(f"Duri_Pipi_{i}", [
        (0.80, 0.75, z0, 0.10),
        (1.10, 0.75 + 0.55 * ln, z0 + dz * 0.6, 0.075),
        (1.28, 0.75 + 1.25 * ln, z0 + dz * 1.6, 0.005)], M_GOLD)

# alis menonjol di atas mata
tube_pair("Alis", [
    (0.26, -0.72, 0.56, 0.05), (0.56, -0.42, 0.74, 0.11),
    (0.78, 0.05, 0.86, 0.13), (0.86, 0.60, 0.74, 0.05)], M_SKIN)

# ---------------------------------------------------------------- mata
for sx in (1, -1):
    side = "L" if sx > 0 else "R"
    c = Vector((sx * 0.62, -0.18, 0.56))
    sphere(f"Mata_{side}", c, 0.17, M_EYE)
    n = Vector((sx * 0.86, -0.42, 0.28)).normalized()
    pup = sphere(f"Pupil_{side}", c + n * 0.105, 1.0, M_DARK,
                 scale=(0.078, 0.042, 0.135))
    pup.rotation_euler = n.to_track_quat("X", "Z").to_euler()

# ---------------------------------------------------------------- hidung
for sx in (1, -1):
    side = "L" if sx > 0 else "R"
    sphere(f"Cuping_{side}", (sx * 0.23, -2.18, 0.46), 0.13, M_SKIN,
           scale=(1.0, 1.3, 0.9))
    sphere(f"Lubang_Hidung_{side}", (sx * 0.29, -2.31, 0.50), 0.05, M_DARK,
           scale=(0.8, 1.2, 0.8))

# ---------------------------------------------------------------- duri punggung
y, i = 0.35, 0
while y < 3.4:
    r = ring_at(HEAD, y)
    h = 0.62 - 0.09 * abs(y - 1.2)
    spike(f"Duri_Punggung_{i}", (0, y, r["z"] + r["top"] - 0.10),
          (0.07, 0.21, h), -0.55 - 0.12 * max(0.0, y - 1.0), M_GOLD)
    y += 0.40
    i += 1
r = ring_at(HEAD, -1.85)
spike("Cula_Hidung", (0, -1.85, r["z"] + r["top"] - 0.06),
      (0.07, 0.12, 0.30), -0.45, M_HORN)

# jenggot di bawah dagu
for i, (y, h) in enumerate([(-2.75, 0.30), (-2.40, 0.42), (-2.00, 0.36),
                            (-1.60, 0.28)]):
    r = ring_at(JAW, y)
    spike(f"Jenggot_{i}", (0, y, r["z"] - r["bot"] + 0.07),
          (0.06, 0.13, h), math.pi + 0.5, M_GOLD, parent=jaw)

# ---------------------------------------------------------------- sungut
tube_pair("Sungut", [
    (0.36, -2.10, 0.22, 0.05), (0.85, -2.55, 0.20, 0.042),
    (1.30, -2.35, -0.25, 0.032), (1.55, -1.70, -0.85, 0.022),
    (1.40, -1.00, -1.35, 0.012), (1.60, -0.55, -1.65, 0.003)], M_GOLD)

# ---------------------------------------------------------------- kamera & cahaya
def look_at(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


cam_data = bpy.data.cameras.new("Kamera")
cam_data.lens = 50
cam = bpy.data.objects.new("Kamera", cam_data)
COL.objects.link(cam)
scene.camera = cam


def add_light(name, loc, energy, size, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy, ld.size, ld.color = energy, size, color
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    COL.objects.link(ob)
    look_at(ob, (0, 0.3, 0.2))
    return ob


add_light("Lampu_Utama", (5, -6, 6), 2000, 5, (1.0, 0.95, 0.88))
add_light("Lampu_Isi", (-6, -4, 1), 700, 6, (0.55, 0.70, 1.0))
add_light("Lampu_Tepi", (-3, 7, 5), 2200, 4, (1.0, 0.70, 0.40))
add_light("Lampu_Bawah", (1, -3, -5), 350, 5, (0.9, 0.5, 0.3))

world = bpy.data.worlds.new("Dunia")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.012, 0.016, 0.024, 1)
scene.world = world

VIEWS = {
    "tigaperempat": ((5.6, -6.9, 2.1), (0.2, 0.45, 0.15)),
    "samping": ((9.2, 0.6, 0.6), (0, 0.6, 0.15)),
    "depan": ((1.0, -8.6, 1.3), (0, 0.5, 0.1)),
}
cam.location = VIEWS["tigaperempat"][0]
look_at(cam, VIEWS["tigaperempat"][1])

scene.render.engine = "CYCLES"
scene.cycles.samples = arg_val("--samples", 96)
scene.cycles.use_denoising = True
size = arg_val("--size", 1200)
scene.render.resolution_x = size
scene.render.resolution_y = int(size * 0.8)
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    if any(d.type == "METAL" for d in prefs.devices):
        scene.cycles.device = "GPU"
except Exception as ex:  # tanpa GPU: tetap jalan di CPU
    print("GPU tidak dipakai:", ex)

# ---------------------------------------------------------------- simpan
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "naga_head.blend"))
print("Tersimpan: naga_head.blend")

if "--no-glb" not in ARGS:
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "naga_head.glb"),
                              export_format="GLB", export_apply=True,
                              export_cameras=False, export_lights=False)
    print("Tersimpan: naga_head.glb")

if "--render" in ARGS:
    only = arg_val("--view", "")
    for vname, (loc, tgt) in VIEWS.items():
        if only and vname != only:
            continue
        cam.location = loc
        look_at(cam, tgt)
        scene.render.filepath = os.path.join(OUT, f"render_{vname}.png")
        bpy.ops.render.render(write_still=True)
        print("Render:", scene.render.filepath)
