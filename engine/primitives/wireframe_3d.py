"""
3D线框原语 — 顶点+边+旋转+投影渲染

支持的几何体:
  cube       — 立方体
  hypercube  — 超立方体(4D投影到3D再投到2D)
  mobius     — 莫比乌斯环(参数曲面)
  tunnel     — 隧道/虫洞(多层环)
  custom     — 自定义顶点/边

配置:
  geometry: 几何体类型
  vertices: 自定义顶点 [[x,y,z], ...] (仅 custom)
  edges:    自定义边 [[a,b], ...] (仅 custom)
  ring_count: 隧道环数 (仅 tunnel)
  scale:    投影缩放
  rotation: {x_speed, y_speed, z_speed}
"""
import math
import random as _random
from engine.primitives import register_primitive, RenderPrimitive


# ===== 预设几何体 =====
CUBE_VERTS = [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
CUBE_EDGES = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]

HYPERCUBE_VERTS = [[(i>>k)&1 for k in range(4)] for i in range(16)]
HYPERCUBE_VERTS = [[v[0]*2-1, v[1]*2-1, v[2]*2-1, v[3]*2-1] for v in HYPERCUBE_VERTS]
HYPERCUBE_EDGES = [(i,j) for i in range(16) for j in range(i+1,16)
                   if sum(abs(HYPERCUBE_VERTS[i][k]-HYPERCUBE_VERTS[j][k]) for k in range(4))==2]

MOBIUS_POINTS = 100
MOBIUS_VERTS = []
for i in range(MOBIUS_POINTS):
    t = i / MOBIUS_POINTS * math.pi * 2
    u = t
    v = 0.5
    x = (1 + v/2 * math.cos(u/2)) * math.cos(u)
    y = (1 + v/2 * math.cos(u/2)) * math.sin(u)
    z = v/2 * math.sin(u/2)
    MOBIUS_VERTS.append((x, y, z))
MOBIUS_EDGES = [(i, i+1) for i in range(MOBIUS_POINTS - 1)]


@register_primitive('wireframe_3d')
class Wireframe3DPrimitive(RenderPrimitive):
    """3D线框投影

    配置:
        geometry: str       'cube'/'hypercube'/'mobius'/'tunnel'/'custom'
        vertices: list     自定义顶点 (仅 custom)
        edges: list         自定义边 (仅 custom)
        scale: float        投影缩放 (默认 150)
        rotation: {x,y,z}_speed  旋转速度
    """

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        geom = config.get('geometry', 'cube')
        self.scale = min(config.get('scale', 150), self._max_safe_radius)
        rot = config.get('rotation', {})
        self.rot_x = rot.get('x_speed', 0.5)
        self.rot_y = rot.get('y_speed', 0.7)
        self.rot_z = rot.get('z_speed', 0.0)
        self.line_width = config.get('line_width', 2)

        if geom == 'cube':
            self.verts = CUBE_VERTS
            self.edges = CUBE_EDGES
        elif geom == 'hypercube':
            self.verts = HYPERCUBE_VERTS
            self.edges = HYPERCUBE_EDGES
            self._is_4d = True
        elif geom == 'mobius':
            self.verts = MOBIUS_VERTS
            self.edges = MOBIUS_EDGES
        elif geom == 'tunnel':
            self.tunnel_rings = config.get('ring_count', 15)
            self.tunnel_rad = min(config.get('tunnel_radius', 40), self._max_safe_radius / 6)
            self._build_tunnel()
        elif geom == 'helix':
            self._build_helix(config.get('helix_points', 50),
                              min(config.get('helix_radius', 60), self._max_safe_radius / 2))
        elif geom == 'custom':
            self.verts = config.get('vertices', [])
            self.edges = config.get('edges', [])
        self._is_4d = geom == 'hypercube'

    def _build_tunnel(self):
        rings = []
        all_verts = []
        all_edges = []
        for ring in range(self.tunnel_rings):
            r = self.tunnel_rad + ring * 25
            ring_verts = []
            for i in range(24):
                a = (i / 24) * math.pi * 2
                ring_verts.append((math.cos(a) * r, math.sin(a) * r, ring * 1.0))
                all_verts.append(ring_verts[-1])
            rings.append(ring_verts)
            if ring > 0:
                for i in range(24):
                    idx = len(all_verts) - 48 + i
                    all_edges.append((idx, idx + 24))
        self.verts = all_verts
        self.edges = all_edges + [(i, (i+1)%24) for i in range(24)]
        self._tunnel_rings = rings

    def _build_helix(self, points, radius):
        # 两条螺旋线 + 横档
        all_verts = []
        all_edges = []
        for i in range(points):
            t = i / (points - 1)
            y = -1 + t * 2  # -1 to 1
            a = t * math.pi * 6  # 3 full rotations
            r = radius + math.sin(a * 2) * 20
            # Strand 1
            all_verts.append((math.cos(a) * r, y * 250, math.sin(a) * r))
            # Strand 2
            all_verts.append((-math.cos(a) * r, y * 250, -math.sin(a) * r))
        # Connect along strands
        for s in range(2):
            for i in range(points - 1):
                all_edges.append((s + i * 2, s + (i + 1) * 2))
        # Cross-bars every 5 points
        for i in range(0, points, 5):
            all_edges.append((i * 2, i * 2 + 1))
        self.verts = all_verts
        self.edges = all_edges

    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)

    def _project(self, v, rx, ry, rz=0, w=0):
        if self._is_4d:
            x4, y4, z4, w4 = v
            # 4D → 3D rotation
            cx = math.cos(rx); sx = math.sin(rx)
            y1 = y4*cx - z4*sx; z1 = y4*sx + z4*cx
            cy = math.cos(ry); sy = math.sin(ry)
            x2 = x4*cy - z1*sy; z2 = x4*sy + z1*cy
            # Stereographic: 4D → 3D
            s = 1.0 / (2.0 - w4 - 0.5)
            x, y, z = x2 * s, y1 * s, z2 * s + 2
            z += 3
        else:
            x, y, z = v[0], v[1], v[2] + w * 0.5 + 3
            cx = math.cos(rx); sx = math.sin(rx)
            y1 = y*cx - z*sx; z1 = y*sx + z*cx
            cy = math.cos(ry); sy = math.sin(ry)
            x1 = x*cy - z1*sy

        sc = self.scale
        return (self.cx + x1 * sc / z1, self.cy + y1 * sc / z1) if not self._is_4d else \
               (self.cx + x * sc, self.cy + y * sc)

    def draw(self, drawer):
        rx = self._time * self.rot_x
        ry = self._time * self.rot_y
        rz = self._time * self.rot_z

        w_val = 0
        if not self._is_4d:
            audio_rms = sum(self._audio.get_band_energy(i) for i in range(32)) / 32
            w_val = audio_rms * 2

        for i, (a, b) in enumerate(self.edges):
            va = self.verts[a]
            vb = self.verts[b]
            pa = self._project(va, rx, ry, rz, w_val)
            pb = self._project(vb, rx, ry, rz, w_val)
            color = self._get_color(i, len(self.edges), w_val if not self._is_4d else 0)
            drawer.line([pa, pb], fill=color, width=self.line_width)
