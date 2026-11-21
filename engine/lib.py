"""Shared helpers for rendering vertical reels with PIL + ffmpeg."""
import os, sys, math, random, subprocess, functools
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops, ImageEnhance

W, H, FPS = 1080, 1920, 30
ROOT = os.environ.get('REELS_HOME', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VEIL = os.environ.get('VEIL_DIR', os.path.join(ROOT, 'assets', 'veil')).rstrip('/') + '/'
FD = os.path.join(ROOT, 'fonts') + '/'
OUT = os.environ.get('REELS_OUT', os.path.join(ROOT, 'out')).rstrip('/') + '/'
os.makedirs(OUT, exist_ok=True)

FONTS = {
    'cinzel':      (FD + 'Cinzel[wght].ttf', 600),
    'cinzelb':     (FD + 'Cinzel[wght].ttf', 800),
    'cinzeldec':   (FD + 'CinzelDecorative-Bold.ttf', None),
    'corm':        (FD + 'CormorantGaramond[wght].ttf', 500),
    'cormb':       (FD + 'CormorantGaramond[wght].ttf', 700),
    'anton':       (FD + 'Anton-Regular.ttf', None),
    'rye':         (FD + 'Rye-Regular.ttf', None),
    'vt':          (FD + 'VT323-Regular.ttf', None),
    'px':          (FD + 'PressStart2P-Regular.ttf', None),
    'grot':        (FD + 'SpaceGrotesk[wght].ttf', 500),
    'grotb':       (FD + 'SpaceGrotesk[wght].ttf', 700),
    'inter':       (FD + 'Inter-Regular.otf', None),
    'interb':      (FD + 'Inter-Bold.otf', None),
    'interx':      (FD + 'Inter-ExtraBold.otf', None),
    'mono':        (FD + 'DejaVuSansMono.ttf', None),
    'arch':        (FD + 'Archivo[wdth,wght].ttf', (500, 100)),
    'archb':       (FD + 'Archivo[wdth,wght].ttf', (700, 100)),
    'archx':       (FD + 'Archivo[wdth,wght].ttf', (900, 112)),
    'archc':       (FD + 'Archivo[wdth,wght].ttf', (800, 80)),
    'monob':       (FD + 'DejaVuSansMono-Bold.ttf', None),
    'dejab':       (FD + 'DejaVuSans-Bold.ttf', None),
    'deja':        (FD + 'DejaVuSans.ttf', None),
}


@functools.lru_cache(None)
def F(key, size):
    path, wght = FONTS[key]
    f = ImageFont.truetype(path, int(size))
    if wght:
        f.set_variation_by_axes(list(wght) if isinstance(wght, tuple) else [wght])
    return f


def hexc(h, a=255):
    h = h.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x

def prog(t, a, b):
    return clamp((t - a) / (b - a)) if b > a else (1.0 if t >= b else 0.0)

def eo(x):  # ease out cubic
    x = clamp(x); return 1 - (1 - x) ** 3

def eio(x):
    x = clamp(x); return 3 * x * x - 2 * x * x * x

def eback(x, s=1.7):
    x = clamp(x); x -= 1; return x * x * ((s + 1) * x + s) + 1

def lerp(a, b, x):
    return a + (b - a) * x


# ---------------------------------------------------------------- text
def _measure(text, f, tracking):
    if tracking == 0:
        b = f.getbbox(text)
        return b[2] - b[0], b[0]
    w = 0
    for ch in text:
        w += f.getlength(ch) + tracking
    return w - tracking, 0


def fit(text, key, size, maxw, tracking=0):
    s = size
    while s > 10:
        f = F(key, s)
        if max(_measure(l, f, tracking)[0] for l in text.split('\n')) <= maxw:
            return s
        s -= 2
    return s


@functools.lru_cache(None)
def text_img(text, key, size, fill='#ffffff', tracking=0, spacing=1.12,
             align='center', stroke=0, stroke_fill='#000000', glow=None,
             glow_r=14, glow_k=1, shadow=None, grad=None, maxw=None):
    """Return an RGBA layer with the text. grad = tuple of hex colours top->bottom."""
    if maxw:
        size = fit(text, key, size, maxw, tracking)
    f = F(key, size)
    lines = text.split('\n')
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * spacing)
    widths = [_measure(l, f, tracking)[0] for l in lines]
    tw = int(max(widths)) + 2
    th = lh * (len(lines) - 1) + asc + desc
    pad = int(glow_r * 3 + stroke + 8) if (glow or shadow) else stroke + 8
    Wd, Hd = tw + 2 * pad, th + 2 * pad
    mask = Image.new('L', (Wd, Hd), 0)
    d = ImageDraw.Draw(mask)
    smask = Image.new('L', (Wd, Hd), 0) if stroke else None
    ds = ImageDraw.Draw(smask) if stroke else None
    for i, l in enumerate(lines):
        lw, off = _measure(l, f, tracking)
        if align == 'center':
            x = pad + (tw - lw) / 2 - off
        elif align == 'right':
            x = pad + tw - lw - off
        else:
            x = pad - off
        y = pad + i * lh
        if tracking == 0:
            d.text((x, y), l, font=f, fill=255)
            if stroke:
                ds.text((x, y), l, font=f, fill=255, stroke_width=stroke, stroke_fill=255)
        else:
            cx = x
            for ch in l:
                d.text((cx, y), ch, font=f, fill=255)
                if stroke:
                    ds.text((cx, y), ch, font=f, fill=255, stroke_width=stroke, stroke_fill=255)
                cx += f.getlength(ch) + tracking
    out = Image.new('RGBA', (Wd, Hd), (0, 0, 0, 0))
    if shadow:
        sc, dx, dy, r = shadow
        sh = Image.new('RGBA', (Wd, Hd), hexc(sc))
        sm = (smask or mask).filter(ImageFilter.GaussianBlur(r))
        sh.putalpha(sm)
        out.alpha_composite(sh, (0, 0))
        out = ImageChops.offset(out, dx, dy)
    if glow:
        gm = (smask or mask).filter(ImageFilter.GaussianBlur(glow_r))
        if glow_k != 1:
            gm = gm.point(lambda v: min(255, int(v * glow_k)))
        gl = Image.new('RGBA', (Wd, Hd), hexc(glow))
        gl.putalpha(gm)
        out.alpha_composite(gl)
    if stroke:
        st = Image.new('RGBA', (Wd, Hd), hexc(stroke_fill))
        st.putalpha(smask)
        out.alpha_composite(st)
    if grad:
        cols = [np.array(hexc(c)[:3], dtype=np.float32) for c in grad]
        ys = np.linspace(0, 1, Hd)
        # map gradient only across the text box
        y0, y1 = pad / Hd, (pad + th) / Hd
        ys = np.clip((ys - y0) / max(1e-6, (y1 - y0)), 0, 1)
        n = len(cols) - 1
        idx = np.minimum((ys * n).astype(int), n - 1)
        fr = ys * n - idx
        row = np.array([cols[i] * (1 - a) + cols[i + 1] * a for i, a in zip(idx, fr)])
        arr = np.repeat(row[:, None, :], Wd, axis=1).astype(np.uint8)
        fl = Image.fromarray(arr, 'RGB').convert('RGBA')
    else:
        fl = Image.new('RGBA', (Wd, Hd), hexc(fill))
    fl.putalpha(mask)
    out.alpha_composite(fl)
    return out


# ---------------------------------------------------------------- compositing
_LUTS = {}
def with_alpha(layer, a):
    if a >= 0.999:
        return layer
    k = int(a * 255)
    lut = _LUTS.get(k)
    if lut is None:
        lut = [v * k // 255 for v in range(256)]
        _LUTS[k] = lut
    L = layer.copy()
    L.putalpha(layer.getchannel('A').point(lut))
    return L


def put(base, layer, cx, cy, a=1.0, s=1.0, rot=0.0, anchor='c'):
    """Paste RGBA layer onto RGB/RGBA base centred at (cx, cy)."""
    if a <= 0.003 or layer is None:
        return
    L = layer
    if abs(s - 1) > 1e-3:
        L = L.resize((max(1, int(L.width * s)), max(1, int(L.height * s))), Image.BICUBIC)
    if abs(rot) > 0.01:
        L = L.rotate(rot, Image.BICUBIC, expand=True)
    L = with_alpha(L, a)
    if anchor == 'c':
        x, y = cx - L.width / 2, cy - L.height / 2
    elif anchor == 'l':
        x, y = cx, cy - L.height / 2
    elif anchor == 'tl':
        x, y = cx, cy
    base.paste(L, (int(round(x)), int(round(y))), L)


@functools.lru_cache(None)
def load(path, mode='RGB'):
    return Image.open(path).convert(mode)


@functools.lru_cache(None)
def prep_cover(path, over=1.22, sharpen=True, bright=1.0):
    im = load(path)
    s = max(W * over / im.width, H * over / im.height)
    im = im.resize((int(im.width * s + .5), int(im.height * s + .5)), Image.LANCZOS)
    if sharpen and s > 1.3:
        im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
    if bright != 1.0:
        im = ImageEnhance.Brightness(im).enhance(bright)
    return im


def kb(path, x, z0=1.0, z1=1.12, p0=(0.5, 0.5), p1=(0.5, 0.5), over=1.22, bright=1.0):
    """Ken-Burns frame. x in 0..1. Zoom z is relative to cover fit (1 = full cover)."""
    im = prep_cover(path, over, True, bright)
    z = lerp(z0, z1, x)
    ww, hh = W * over / z, H * over / z
    ww = min(ww, im.width); hh = min(hh, im.height)
    px = lerp(p0[0], p1[0], x); py = lerp(p0[1], p1[1], x)
    cx = ww / 2 + (im.width - ww) * px
    cy = hh / 2 + (im.height - hh) * py
    box = (cx - ww / 2, cy - hh / 2, cx + ww / 2, cy + hh / 2)
    return im.resize((W, H), Image.BILINEAR, box=box)


def darken(img, k):
    if k >= 0.999:
        return img
    return Image.blend(Image.new('RGB', img.size, (0, 0, 0)), img, k)


def fade(img, k, color=(0, 0, 0)):
    if k >= 0.999:
        return img
    return Image.blend(Image.new('RGB', img.size, color), img, max(0.0, k))


@functools.lru_cache(None)
def vgrad(c_top, c_bot, w=W, h=H):
    a = np.array(hexc(c_top)[:3], np.float32); b = np.array(hexc(c_bot)[:3], np.float32)
    t = np.linspace(0, 1, h)[:, None]
    row = a * (1 - t) + b * t
    arr = np.repeat(row[:, None, :], w, axis=1).reshape(h, w, 3)
    return Image.fromarray(arr.astype(np.uint8), 'RGB')


@functools.lru_cache(None)
def shade(top=0.6, bottom=0.75, mid=0.0, top_h=0.35, bot_h=0.4, color='#000000'):
    """RGBA overlay darkening top and bottom for legibility."""
    y = np.linspace(0, 1, H)
    a = np.full(H, mid)
    a = np.maximum(a, top * np.clip(1 - y / top_h, 0, 1) ** 1.5)
    a = np.maximum(a, bottom * np.clip((y - (1 - bot_h)) / bot_h, 0, 1) ** 1.5)
    al = (a * 255).astype(np.uint8)
    A = Image.fromarray(np.repeat(al[:, None], W, axis=1), 'L')
    L = Image.new('RGBA', (W, H), hexc(color)); L.putalpha(A)
    return L


@functools.lru_cache(None)
def radial(w, h, color, inner=0.0, power=2.0, amax=1.0):
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    a = np.clip(1 - (d - inner) / (1 - inner), 0, 1) ** power * amax
    L = Image.new('RGBA', (w, h), hexc(color))
    L.putalpha(Image.fromarray((a * 255).astype(np.uint8), 'L'))
    return L


@functools.lru_cache(None)
def vignette(strength=0.65, power=2.2):
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.62)) ** 2)
    a = np.clip(d, 0, 1.4) ** power / (1.4 ** power) * strength * 1.6
    a = np.clip(a, 0, strength)
    L = Image.new('RGBA', (W, H), (0, 0, 0, 255))
    L.putalpha(Image.fromarray((a * 255).astype(np.uint8), 'L'))
    return L


def overlay(base, layer, x=0, y=0):
    base.paste(layer, (x, y), layer)


def screen(base, layer_rgba, a=1.0):
    """Screen-blend an RGBA glow layer (full frame) onto base."""
    if a <= 0.003:
        return base
    L = with_alpha(layer_rgba, a)
    black = Image.new('RGB', L.size, (0, 0, 0))
    black.paste(L, (0, 0), L)
    return ImageChops.screen(base, black)


# ---------------------------------------------------------------- particles
@functools.lru_cache(None)
def sparkle_sprite(r, color, star=True):
    s = r * 6
    yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
    c = (s - 1) / 2
    dx, dy = (xx - c) / r, (yy - c) / r
    d = np.sqrt(dx * dx + dy * dy)
    a = np.exp(-(d * 1.1) ** 2) * 0.9 + np.exp(-(d * 3.2) ** 2)
    if star:
        a += np.exp(-(dy * 6) ** 2) * np.exp(-np.abs(dx) * 0.9) * 0.55
        a += np.exp(-(dx * 6) ** 2) * np.exp(-np.abs(dy) * 0.9) * 0.55
    a = np.clip(a, 0, 1)
    L = Image.new('RGBA', (s, s), hexc(color))
    L.putalpha(Image.fromarray((a * 255).astype(np.uint8), 'L'))
    return L


@functools.lru_cache(None)
def sprite_alpha(r, color, star, k):
    return with_alpha(sparkle_sprite(r, color, star), k / 8)


class Particles:
    def __init__(self, n, seed, colors=('#f7d98b',), r=(2, 6), vy=(-60, -15), vx=(-12, 12),
                 region=(0, 0, W, H), star_frac=0.4, tw=(1.5, 4.0)):
        rnd = random.Random(seed)
        x0, y0, x1, y1 = region
        self.region = region
        self.p = []
        for _ in range(n):
            self.p.append(dict(x=rnd.uniform(x0, x1), y=rnd.uniform(y0, y1),
                               vx=rnd.uniform(*vx), vy=rnd.uniform(*vy),
                               r=rnd.randint(*r), c=rnd.choice(colors),
                               star=rnd.random() < star_frac,
                               ph=rnd.uniform(0, 6.28), sp=rnd.uniform(*tw)))

    def draw(self, img, t, a=1.0):
        x0, y0, x1, y1 = self.region
        w, h = x1 - x0, y1 - y0
        for q in self.p:
            x = x0 + (q['x'] - x0 + q['vx'] * t) % w
            y = y0 + (q['y'] - y0 + q['vy'] * t) % h
            k = (0.55 + 0.45 * math.sin(q['ph'] + q['sp'] * t)) * a
            k = int(round(clamp(k) * 8))
            if k <= 0:
                continue
            sp = sprite_alpha(q['r'], q['c'], q['star'], k)
            img.paste(sp, (int(x - sp.width / 2), int(y - sp.height / 2)), sp)


# ---------------------------------------------------------------- shapes
def rrect(size, radius, fill=None, outline=None, width=0, scale=2):
    w, h = size
    L = Image.new('RGBA', (w * scale, h * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    d.rounded_rectangle([0, 0, w * scale - 1, h * scale - 1], radius * scale,
                        fill=hexc(fill) if fill else None,
                        outline=hexc(outline) if outline else None, width=width * scale)
    return L.resize((w, h), Image.LANCZOS)


def star_poly(cx, cy, r_out, r_in, n=5, rot=-90):
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


@functools.lru_cache(None)
def star_img(r, color, n=4, inner=0.38, glow=None):
    s = int(r * 2 + 40)
    L = Image.new('RGBA', (s * 2, s * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    d.polygon(star_poly(s, s, r * 2, r * 2 * inner, n), fill=hexc(color))
    L = L.resize((s, s), Image.LANCZOS)
    if glow:
        g = L.getchannel('A').filter(ImageFilter.GaussianBlur(r * 0.5))
        G = Image.new('RGBA', L.size, hexc(glow)); G.putalpha(g)
        G.alpha_composite(L); L = G
    return L


def shadow_of(layer, r=24, color='#000000', a=0.7):
    pad = r * 3
    m = Image.new('L', (layer.width + 2 * pad, layer.height + 2 * pad), 0)
    m.paste(layer.getchannel('A'), (pad, pad))
    m = m.filter(ImageFilter.GaussianBlur(r)).point(lambda v: int(v * a))
    S = Image.new('RGBA', m.size, hexc(color)); S.putalpha(m)
    return S


def find_coeffs(pa, pb):
    matrix = []
    for p1, p2 in zip(pa, pb):
        matrix.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0] * p1[0], -p2[0] * p1[1]])
        matrix.append([0, 0, 0, p1[0], p1[1], 1, -p2[1] * p1[0], -p2[1] * p1[1]])
    A = np.array(matrix, dtype=np.float64)
    B = np.array(pb, dtype=np.float64).reshape(8)
    res = np.linalg.solve(A, B)
    return res.tolist()


def perspective(layer, quad, out_size):
    """Map layer (rect) onto quad [(tl),(tr),(br),(bl)] in an image of out_size."""
    w, h = layer.size
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    co = find_coeffs(quad, src)
    return layer.transform(out_size, Image.PERSPECTIVE, co, Image.BICUBIC)


@functools.lru_cache(None)
def noise_tex(w, h, seed=1, scale=1.0, amp=30):
    rng = np.random.default_rng(seed)
    n = rng.normal(0, 1, (h // 4 + 2, w // 4 + 2)).astype(np.float32)
    im = Image.fromarray(np.clip(128 + n * amp, 0, 255).astype(np.uint8), 'L')
    im = im.resize((w, h), Image.BICUBIC)
    fine = rng.normal(0, amp * 0.4, (h, w)).astype(np.float32)
    arr = np.clip(np.asarray(im, np.float32) + fine, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, 'L')


# ---------------------------------------------------------------- rendering
def _encode_cmd(path):
    return ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
            '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-c:v', 'libx264',
            '-preset', 'veryfast', '-crf', '19', '-pix_fmt', 'yuv420p',
            '-g', '60', '-movflags', '+faststart', path]


SCENES = []   # filled by each reel module: list of (name, nframes, fn(t_local, i))


def _render_scene(idx):
    name, nf, fn = SCENES[idx]
    final = OUT + f'{name}.mp4'
    tmp = OUT + f'{name}.tmp.mp4'
    p = subprocess.Popen(_encode_cmd(tmp), stdin=subprocess.PIPE)
    for i in range(nf):
        img = fn(i / FPS, i)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        p.stdin.write(img.tobytes())
    p.stdin.close()
    rc = p.wait()
    if rc == 0:
        os.replace(tmp, final)
    return name, rc


def render_all(reel, scenes, audio_wav, workers=2, only=None):
    import multiprocessing as mp
    SCENES[:] = scenes
    idxs = [i for i, s in enumerate(scenes) if (only is None or s[0] in only)]
    ctx = mp.get_context('fork')
    with ctx.Pool(workers) as pool:
        for name, rc in pool.imap_unordered(_render_scene, idxs):
            print('  scene', name, 'rc', rc, flush=True)
            if rc != 0:
                raise SystemExit('render failed ' + name)
    lst = OUT + f'{reel}_list.txt'
    with open(lst, 'w') as fh:
        for s in scenes:
            fh.write(f"file '{OUT}{s[0]}.mp4'\n")
    silent = OUT + f'{reel}_silent.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst,
                    '-c', 'copy', silent], check=True)
    final = OUT + f'{reel}.mp4'
    tmp = OUT + f'{reel}.tmp.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', silent, '-i', audio_wav,
                    '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                    '-shortest', '-movflags', '+faststart', tmp], check=True)
    os.replace(tmp, final)
    return final


def stills(reel, scenes, times, cols=4, thumb=360):
    """Render chosen (scene_name, t) moments; save full-size PNGs + a contact sheet."""
    ims = []
    for name, t in times:
        fn = dict((s[0], s[2]) for s in scenes)[name]
        im = fn(t, int(t * FPS)).convert('RGB')
        im.save(OUT + f'still_{name}_{t:.2f}.jpg', quality=88)
        ims.append(im)
    th = int(thumb * H / W)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * thumb, rows * th), 'white')
    for k, im in enumerate(ims):
        sheet.paste(im.resize((thumb, th), Image.LANCZOS), ((k % cols) * thumb, (k // cols) * th))
    path = OUT + f'sheet_{reel}.jpg'
    sheet.save(path, quality=85)
    return path


# ---------------------------------------------------------------- attention effects
def zoom(img, s):
    if s <= 1.001:
        return img
    w, h = W / s, H / s
    return img.resize((W, H), Image.BILINEAR, box=((W - w) / 2, (H - h) / 2, (W + w) / 2, (H + h) / 2))


def rgb_split(img, d):
    if d < 1:
        return img
    r, g, b = img.split()
    return Image.merge('RGB', (ImageChops.offset(r, int(d), 0), g, ImageChops.offset(b, -int(d), 0)))


def glitch(img, amt, seed):
    """Horizontal band displacement + RGB split. amt 0..1."""
    if amt <= 0.01:
        return img
    rnd = random.Random(seed)
    out = img.copy()
    for _ in range(int(6 + 10 * amt)):
        y = rnd.randint(0, H - 40); hh = rnd.randint(8, int(30 + 140 * amt))
        dx = int(rnd.uniform(-1, 1) * 120 * amt)
        band = img.crop((0, y, W, min(H, y + hh)))
        out.paste(ImageChops.offset(band, dx, 0), (0, y))
    return rgb_split(out, 14 * amt)


@functools.lru_cache(None)
def scanlines(alpha=22, gap=4):
    L = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    for y in range(0, H, gap):
        d.line([(0, y), (W, y)], fill=(0, 0, 0, alpha), width=1)
    return L


def shake(img, amp, t):
    if amp < 0.5:
        return img
    return ImageChops.offset(img, int(amp * math.sin(t * 97)), int(amp * 0.7 * math.cos(t * 83)))


def flash(img, k, color=(255, 255, 255)):
    if k <= 0.01:
        return img
    return Image.blend(img, Image.new('RGB', img.size, color), clamp(k))
