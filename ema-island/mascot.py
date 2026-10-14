"""Raven's mascot: the Avatar Lab export in kirby-avatar/, drawn on a Tk canvas.

The export is a React package whose engine renders a sphere head with two side lobes and two capsule
eyes in SVG. This is a port of the parts of that engine the avatar uses: head orientation as a
quaternion, perspective with focal length 620, eyes wrapped onto the sphere, smoothstep transitions
between expressions, and the blink curve. Colors and animation data come straight from the export.
"""
import json
import math
import random
import time
from pathlib import Path

K = 620.0  # engine focal length
FIELDS = ("headX", "headY", "headZ", "widthLeft", "widthRight", "heightLeft", "heightRight", "spacing",
          "positionXLeft", "positionXRight", "positionYLeft", "positionYRight", "leftAngle", "rightAngle",
          "perspective")


def load_export(path):
    """avatarData from the exported kirby.avatar.ts (a JSON literal wrapped in TypeScript)."""
    src = Path(path).read_text()
    start = src.index("export const avatarData = ") + len("export const avatarData = ")
    return json.loads(src[start:src.index(" as const satisfies AvatarData")])


def _quat(axis, deg):
    h = math.radians(deg) / 2
    s = math.sin(h)
    return (math.cos(h), axis[0] * s, axis[1] * s, axis[2] * s)


def _qmul(a, b):
    e, t, n, r = a
    i, o, s, c = b
    q = (e * i - t * o - n * s - r * c, e * o + t * i + n * c - r * s, e * s - t * c + n * i + r * o,
         e * c + t * s - n * o + r * i)
    m = math.hypot(*q) or 1
    return tuple(v / m for v in q)


def orientation(hx, hy, hz):
    """Same composition as the engine: roll * pitch * yaw."""
    return _qmul(_qmul(_quat((0, 0, 1), hz), _quat((1, 0, 0), hx)), _quat((0, 1, 0), hy))


def _rot(q, v):
    e, t, n, r = q
    i, a, o = v
    s, c, l = 2 * (n * o - r * a), 2 * (r * i - t * o), 2 * (t * a - n * i)
    return (i + e * s + (n * l - r * c), a + e * c + (r * s - t * l), o + e * l + (t * c - n * s))


def _proj(p, persp):
    d = K - p[2] * persp
    s = K / d if abs(d) > 1e-4 else K / 1e-4
    return p[0] * s, p[1] * s


def _capsule(w, h, corner_steps=6):
    """Outline of a w x h stadium (rounded ends), as the engine's eye shape."""
    n, r = w / 2, h / 2
    c = min(n, r)
    pts = []
    for cx, cy, a0 in ((n - c, -r + c, -90), (n - c, r - c, 0), (-n + c, r - c, 90), (-n + c, -r + c, 180)):
        for k in range(corner_steps + 1):
            a = math.radians(a0 + 90 * k / corner_steps)
            pts.append((cx + c * math.cos(a), cy + c * math.sin(a)))
    return pts


def _hull(points):
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and ((out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                                     - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(p)
        return out

    lower, upper = half(pts), half(reversed(pts))
    return lower[:-1] + upper[:-1]


def _ease(p, kind):
    if kind == "smooth":
        return p * p * (3 - 2 * p)
    if kind == "snappy":
        return 1 - (1 - p) ** 3
    return 1 - math.exp(-6 * p) * math.cos(8 * p)


class Mascot:
    def __init__(self, path, body="#C7C3FF", eyes=None):
        data = load_export(path)
        avatar = data["avatar"]
        self.body, self.eyes = body, eyes or avatar["colors"]["eyes"]
        self.radius = avatar["surface"]["width"] / 2
        self.expressions, self.animations = data["expressions"], data["animations"]
        self.nodes = [self._node_points(n) for n in avatar.get("bodyNodes", [])]
        # extent of the whole figure, to fit it in a box
        xs = [abs(p[0]) for pts in self.nodes for p in pts] + [self.radius]
        ys = [abs(p[1]) for pts in self.nodes for p in pts] + [self.radius]
        self.extent = 2 * max(max(xs), max(ys)) * 1.04
        self.name = None
        self.pose = dict(self.expressions[next(iter(self.animations.values()))["steps"][0]["expressionId"]])
        self.play(next(iter(self.animations)))

    def _node_points(self, node, lat_steps=7, lon_steps=16):
        """Surface samples of a side lobe (an ellipsoid), placed in head space."""
        s = node["surface"]
        a, b, c = s["width"] / 2, s["height"] / 2, s["depth"] / 2
        q = orientation(*node.get("rotation", (0, 0, 0)))
        px, py, pz = node["position"]
        pts = []
        for i in range(lat_steps + 1):
            lat = -math.pi / 2 + math.pi * i / lat_steps
            for j in range(lon_steps):
                lon = 2 * math.pi * j / lon_steps
                v = _rot(q, (a * math.cos(lat) * math.cos(lon), b * math.sin(lat), c * math.cos(lat) * math.sin(lon)))
                pts.append((v[0] + px, v[1] + py, v[2] + pz))
        return pts

    # ----- animation -----
    def play(self, name, now=None):
        if name == self.name or name not in self.animations:
            return
        now = now if now is not None else time.perf_counter() * 1000
        self.name, self.anim, self.step = name, self.animations[name], -1
        self.blink_at = now + self.anim["blink"].get("initialDelayMs", 1200)
        self.blink_t0 = None
        self._next(now)

    def _next(self, now):
        steps = self.anim["steps"]
        self.step = (self.step + 1) % len(steps)
        st = steps[self.step]
        self.src = self.current(now) if hasattr(self, "dst") else dict(self.pose)
        self.dst = self.expressions[st["expressionId"]]
        self.t0, self.trans, self.hold, self.kind = now, max(st["transitionMs"], 1), st["holdMs"], st["transition"]

    def current(self, now):
        p = _ease(min(max((now - self.t0) / self.trans, 0), 1), self.kind)
        return {f: self.src[f] + (self.dst[f] - self.src[f]) * p for f in FIELDS}

    def _blink(self, now):
        b = self.anim["blink"]
        if not b.get("enabled"):
            return 1.0
        if self.blink_t0 is None and now >= self.blink_at:
            self.blink_t0 = now
        if self.blink_t0 is None:
            return 1.0
        p = (now - self.blink_t0) / b["durationMs"]
        if p >= 1:
            self.blink_t0 = None
            self.blink_at = now + b["minIntervalMs"] + random.random() * (b["maxIntervalMs"] - b["minIntervalMs"])
            return 1.0
        return 1 - (p / 0.42) ** 2 if p <= 0.42 else 1 - (1 - (p - 0.42) / 0.58) ** 2

    # ----- drawing -----
    def draw(self, cv, cx, cy, size, tags=("mascot",)):
        """Draw the current frame centered on (cx, cy), fitting the figure in a size x size box."""
        now = time.perf_counter() * 1000
        if now - self.t0 >= self.trans + self.hold:
            self._next(now)
        pose, blink = self.current(now), self._blink(now)
        q = orientation(pose["headX"], pose["headY"], pose["headZ"])
        persp, k = pose["perspective"], size / self.extent

        def to_canvas(p):
            x, y = _proj(_rot(q, p), persp)
            return cx + x * k, cy + y * k

        for pts in self.nodes:  # all body parts share one color, so their order doesn't matter
            outline = _hull([to_canvas(p) for p in pts])
            cv.create_polygon([v for p in outline for v in p], fill=self.body, outline="", tags=tags)
        r = self.radius * K / math.sqrt(K * K - self.radius * self.radius) * k  # sphere silhouette in perspective
        cv.create_oval(cx - r, cy - r, cx + r, cy + r, fill=self.body, outline="", tags=tags)
        for side in (-1, 1):
            self._eye(cv, pose, q, side, blink, to_canvas, tags)

    def _eye(self, cv, pose, q, side, blink, to_canvas, tags):
        s = "Left" if side < 0 else "Right"
        w, h = pose[f"width{s}"], 5 + (pose[f"height{s}"] - 5) * blink
        ox = side * pose["spacing"] / 2 + pose[f"positionX{s}"]
        oy = pose[f"positionY{s}"]
        a = math.radians(pose["leftAngle"] if side < 0 else pose["rightAngle"])
        R = self.radius
        pts, facing = [], 0.0
        for x, y in _capsule(w, h):
            ex, ey = ox + x * math.cos(a) - y * math.sin(a), oy + x * math.sin(a) + y * math.cos(a)
            lon, lat = ex / R, ey / R  # eye space wraps onto the sphere as longitude / latitude
            p = (R * math.cos(lat) * math.sin(lon), R * math.sin(lat), R * math.cos(lat) * math.cos(lon))
            facing += _rot(q, p)[2]
            pts.append(to_canvas(p))
        if facing > 0:  # eye on the visible side of the head
            cv.create_polygon([v for p in pts for v in p], fill=self.eyes, outline="", smooth=True, tags=tags)
