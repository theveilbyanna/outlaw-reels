"""Outlaw Reels engine: turn a JSON script into a finished 1080x1920 reel with music.

Usage:  python3 engine/make_reel.py specs/example.json OUT_DIR
Writes OUT_DIR/<slug>.mp4 and OUT_DIR/<slug>.jpg (cover). See README.md for the spec format.
"""
import sys, os, json, re, math, random, functools, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
from lib import *
import audio as A

# ------------------------------------------------------------------ themes
GOLDG = ('#fff1c2', '#e9c46a', '#b9832f')
THEMES = {
    'veil':     dict(bg='image', img='vt-world.webp', head='cinzelb', body='cinzel', fancy='cinzeldec', ink='#f1e8d5', acc='#d6a64b', acc2='#e9dfff',
                     card='#0b0b22', cardInk='#f1e8d5', cardLine='#d6a64b', parts='sparkle', music='jig', trans='soft', maxHead=96),
    'academy':  dict(bg='image', img='ch-school.webp', head='cinzelb', body='cinzel', fancy='cinzeldec', ink='#f1e8d5', acc='#d6a64b', acc2='#e9dfff',
                     card='#0b0b22', cardInk='#f1e8d5', cardLine='#d6a64b', parts='sparkle', music='jig2', trans='soft', maxHead=96),
    'frickfake':dict(bg='ink', head='anton', body='interb', mono='vt', ink='#f3ece0', acc='#e5322b', acc2='#ffd23f', card='#cdc6ba', cardInk='#0d0c0b',
                     cardLine='#0d0c0b', parts=None, music='chip', trans='glitch', maxHead=170),
    'uaom':     dict(bg='navy', head='archc', body='arch', bold='archb', ink='#FFFFFF', acc='#FFB547', acc2='#3B8CFF', card='#FFFFFF', cardInk='#16202E',
                     cardLine='#26425F', parts=None, music='corp', trans='soft', maxHead=132),
    'outlaw':   dict(bg='ember', head='anton', body='grot', western='rye', ink='#f3ece0', acc='#e8352a', acc2='#d9a441', card='#151313', cardInk='#f3ece0',
                     cardLine='#3a2a20', parts='ember', music='western', trans='punch', maxHead=180),
    'pocket':   dict(bg='pocket', head='anton', body='grotb', ink='#f3ece0', acc='#e5322b', acc2='#c9ccd1', card='#171617', cardInk='#f3ece0',
                     cardLine='#2e2b2b', parts='ember', music='pop', trans='punch', maxHead=170),
}
TH = {}            # the active theme
SPARK = Particles(70, 3, colors=('#f7d98b', '#ffe9b8', '#c3aef7'), r=(2, 6), vy=(-70, -20))
EMBER = Particles(60, 31, colors=('#ff6a2a', '#ffb347', '#d42a20', '#ffd27a'), r=(1, 4), vy=(-150, -50), vx=(-25, 25),
                  region=(0, 300, W, H + 100), star_frac=0.0, tw=(3, 8))


def hb(key):  # bold body key per theme
    return {'arch': 'archb', 'cinzel': 'cinzelb', 'grot': 'grotb', 'interb': 'interx', 'grotb': 'grotb'}.get(TH[key], TH[key])


def T(text, key, size, fill=None, **kw):
    return text_img(text, key, int(size), fill=fill or TH['ink'], **kw)


def head(text, size=None, color=None, maxw=960):
    size = size or TH['maxHead']
    if TH['bg'] == 'image':
        return text_img(text, TH['head'], size, fill=color or TH['ink'], glow='#d6a64b', glow_r=16, glow_k=1.2,
                        shadow=('#000000', 0, 4, 10), maxw=maxw)
    sh = ('#000000', 0, 6, 10) if TH['bg'] != 'ink' else ('#e5322b', 6, 6, 0) if color in (None, TH['ink']) else ('#000000', 0, 5, 8)
    return text_img(text, TH['head'], size, fill=color or TH['ink'], shadow=sh, maxw=maxw)


def split_star(line):
    return (line[1:], True) if line.startswith('*') else (line, False)


# ------------------------------------------------------------------ backgrounds
@functools.lru_cache(None)
def bg_static(kind, seed=1):
    if kind == 'ink':
        b = Image.new('RGB', (W, H), hexc('#0d0c0b')[:3]); n = noise_tex(W, H, seed, 1, 14)
        b = Image.blend(b, Image.merge('RGB', (n, n, n)), 0.05)
        g = radial(1400, 1200, '#3a0a07', 0.0, 1.6, 0.6); b.paste(g, (W // 2 - 700, 400), g)
        return b
    if kind == 'navy':
        b = vgrad('#10233B', '#0A1524').copy(); d = ImageDraw.Draw(b)
        for x in range(0, W, 54):
            for y in range(0, H, 54):
                d.point((x, y), fill=(40, 70, 105))
        g = radial(1500, 1300, '#1E5AA8', 0.0, 1.8, 0.55); b.paste(g, (W // 2 - 750, 300), g)
        return b
    if kind == 'ember':
        b = Image.new('RGB', (W, H), (10, 9, 9)); n = noise_tex(W, H, 12, 1, 14)
        b = Image.blend(b, Image.merge('RGB', (n, n, n)), 0.05)
        g = radial(1800, 1100, '#7a1a08', 0.0, 1.5, 0.85); b.paste(g, (W // 2 - 900, H - 450), g)
        return b
    if kind == 'pocket':
        b = Image.new('RGB', (W, H), hexc('#0c0b0b')[:3]); n = noise_tex(W, H, 4, 1, 16)
        b = Image.blend(b, Image.merge('RGB', (n, n, n)), 0.06)
        g = radial(1500, 1500, '#5a0d0a', 0.0, 1.6, 0.8); b.paste(g, (W // 2 - 750, 210), g)
        return b
    raise ValueError(kind)


def background(sc, t, x, idx):
    if TH['bg'] == 'image':
        img_name = sc.get('bg') or TH['img']
        path = VEIL + img_name
        if not os.path.exists(path):
            path = VEIL + TH['img']
        z0, z1 = (1.04, 1.14) if idx % 2 == 0 else (1.14, 1.04)
        img = kb(path, x, z0, z1, (0.5, 0.55), (0.5, 0.45))
        img = darken(img, sc.get('dark', 0.5))
        sh = shade(0.55, 0.65, 0.15)
        img.paste(sh, (0, 0), sh)
    else:
        img = bg_static(TH['bg']).copy()
    if TH['parts'] == 'sparkle':
        SPARK.draw(img, t + idx * 3, 0.85)
    elif TH['parts'] == 'ember':
        EMBER.draw(img, t + idx * 3, 0.9)
    return img


def finish(img, t, i, idx):
    tr = TH['trans']
    if tr in ('punch', 'glitch') and idx > 0:
        img = zoom(img, 1 + 0.07 * (1 - eo(prog(t, 0, 0.22))))
    if tr == 'glitch':
        if t < 0.1 and idx > 0:
            img = glitch(img, 0.6 * (1 - t / 0.1), idx * 31 + i)
        img.paste(scanlines(), (0, 0), scanlines())
    if TH['bg'] in ('image', 'ember', 'pocket'):
        img.paste(vignette(0.5), (0, 0), vignette(0.5))
    if tr == 'soft':
        img = fade(img, 0.55 + 0.45 * eo(prog(t, 0, 0.3))) if idx > 0 else fade(img, eo(prog(t, 0, 0.3)))
    elif idx == 0:
        img = flash(img, 0.7 * (1 - prog(t, 0, 0.08)))
    return img


def appear(img, layer, cx, cy, t, st, d=None, s0=None, anchor='c'):
    """Theme-aware entrance: slam for punchy themes, rise for soft ones."""
    if TH['trans'] == 'soft':
        k = eo(prog(t, st, st + (d or 0.45)))
        if k > 0:
            put(img, layer, cx, cy + (1 - k) * 30, a=k, anchor=anchor)
    else:
        k = eo(prog(t, st, st + (d or 0.15)))
        if k > 0:
            put(img, layer, cx, cy, a=min(1, k * 2.2), s=lerp(s0 or 1.4, 1, k), anchor=anchor)
    return k


# ------------------------------------------------------------------ widgets
@functools.lru_cache(None)
def card_box(w, h, fill, line, radius=30):
    if TH['bg'] == 'ink':  # retro putty window with bevel
        L = Image.new('RGBA', (w + 14, h + 14), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
        d.rectangle([14, 14, w + 13, h + 13], fill=hexc('#e5322b'))
        d.rectangle([0, 0, w - 1, h - 1], fill=hexc(fill), outline=hexc('#0d0c0b'), width=4)
        d.line([(4, 4), (w - 5, 4)], fill=hexc('#fffaf0'), width=3); d.line([(4, 4), (4, h - 5)], fill=hexc('#fffaf0'), width=3)
        return L
    return rrect((w, h), radius, fill=fill, outline=line, width=2)


@functools.lru_cache(None)
def badge(label, size=120):
    L = Image.new('RGBA', (size * 2, size * 2), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    if TH['bg'] == 'ink':
        d.rectangle([0, 0, size * 2 - 1, size * 2 - 1], fill=hexc(TH['acc']), outline=hexc('#0d0c0b'), width=8)
    elif TH['bg'] == 'ember':
        d.polygon(star_poly(size, size, size * 0.98, size * 0.55, 6), fill=hexc(TH['acc2']))
    else:
        d.ellipse([0, 0, size * 2 - 1, size * 2 - 1], fill=hexc(TH['acc'] if TH['bg'] != 'navy' else '#1F4E79'))
    L = L.resize((size, size), Image.LANCZOS)
    if label == 'check':
        c = Image.new('RGBA', (size * 2, size * 2), (0, 0, 0, 0))
        ImageDraw.Draw(c).line([(size * .55, size * 1.02), (size * .88, size * 1.35), (size * 1.48, size * .68)], fill=(255, 255, 255, 255), width=int(size * .2), joint='curve')
        c = c.resize((size, size), Image.LANCZOS); L.alpha_composite(c)
    else:
        col = '#16202E' if TH['bg'] == 'ember' else '#ffffff'
        n = text_img(str(label), 'anton', int(size * 0.62), fill=col)
        L.paste(n, (size // 2 - n.width // 2, size // 2 - n.height // 2), n)
    return L


@functools.lru_cache(None)
def item_card(i, title, sub, numbered):
    w, h = 960, (200 if sub else 150)
    C = card_box(w, h, TH['card'], TH['cardLine']).copy()
    b = badge(str(i + 1) if numbered else 'check', 104)
    C.paste(b, (28, h // 2 - 52), b)
    tk = hb('body') if TH['head'] != 'anton' else 'anton'
    t1 = text_img(title, tk, 60 if tk == 'anton' else 48, fill=TH['cardInk'], align='left', maxw=760)
    C.paste(t1, (160 - 8, (h // 2 - 34 if sub else h // 2) - t1.height // 2), t1)
    if sub:
        mut = '#5B6B80' if TH['card'] in ('#FFFFFF',) else '#3a3530' if TH['bg'] == 'ink' else '#a59d92'
        t2 = text_img(sub, TH['body'] if TH['body'] not in ('cinzel',) else 'corm', 34, fill=mut, align='left', maxw=770)
        C.paste(t2, (160 - 8, h // 2 + 40 - t2.height // 2), t2)
    return C


@functools.lru_cache(None)
def bubble_img(text, mine, label=None):
    key = 'arch' if TH['bg'] == 'navy' else 'inter' if TH['bg'] in ('ink', 'pocket', 'ember') else 'corm'
    size = 44 if key == 'corm' else 40
    f = F(key, size); words = text.split(); lines, cur = [], ''
    for w_ in words:
        trial = (cur + ' ' + w_).strip()
        if f.getlength(trial) <= 700: cur = trial
        else: lines.append(cur); cur = w_
    lines.append(cur)
    if mine:
        fill, ink = (TH['acc2'] if TH['bg'] == 'navy' else TH['acc']), '#ffffff'
        if TH['bg'] == 'image': fill, ink = '#2a1f4d', '#f1e8d5'
    else:
        fill, ink = ('#E9EEF3', '#16202E') if TH['bg'] in ('navy', 'pocket', 'ember') else ('#cdc6ba', '#0d0c0b') if TH['bg'] == 'ink' else ('#14122e', '#f1e8d5')
    L = text_img('\n'.join(lines), key, size, fill=ink, align='left', spacing=1.18)
    B = rrect((L.width - 16 + 56, L.height - 16 + 44), 34, fill=fill)
    B.paste(L, (20, 14), L)
    return B


# ------------------------------------------------------------------ scenes
def words_in(sc):
    s = json.dumps({k: v for k, v in sc.items() if k not in ('type', 'bg', 'dur', 'dark', 'card')})
    return len(re.findall(r'[A-Za-z0-9$%]+', s))


def scene_duration(sc):
    if sc.get('dur'):
        return float(sc['dur'])
    t = sc['type']; n = words_in(sc)
    base = {'hook': 1.2, 'bullets': 1.6, 'big': 1.4, 'chat': 1.0, 'xlist': 1.8, 'card': 2.2, 'cta': 2.6, 'statement': 1.2}.get(t, 1.5)
    return max(2.6, min(7.5, base + n * 0.24))


def r_hook(img, sc, t, D):
    lines = sc.get('lines', [])
    n = len(lines)
    sizes = []
    for ln in lines:
        txt, star = split_star(ln)
        sizes.append(fit(txt, TH['head'], TH['maxHead'] * (1.12 if star else 1.0), 960))
    hs = [int(s * 1.05) for s in sizes]
    total = sum(hs) + 20 * (n - 1)
    y = 860 - total / 2 + (60 if sc.get('sub') else 0) - (60 if sc.get('kicker') else 0)
    if sc.get('kicker'):
        appear(img, T(sc['kicker'], TH['body'] if TH['bg'] != 'ink' else 'vt', 58 if TH['bg'] != 'ink' else 72, fill=TH['acc2'], maxw=960), W / 2, y - 90, t, 0.0, d=0.3)
    for i, ln in enumerate(lines):
        txt, star = split_star(ln)
        L = head(txt, sizes[i], TH['acc'] if star else TH['ink'])
        appear(img, L, W / 2, y + hs[i] / 2, t, 0.1 + i * 0.42)
        y += hs[i] + 20
    if sc.get('sub'):
        k = 0.1 + n * 0.42 + 0.35
        key = TH['body'] if TH['bg'] != 'ink' else 'vt'
        appear(img, T(sc['sub'], key, 52 if key != 'vt' else 66, fill=TH['acc2'] if TH['bg'] != 'image' else TH['acc'], maxw=960), W / 2, y + 70, t, k, d=0.4)


def r_statement(img, sc, t, D):
    txt = sc.get('text', '')
    key = TH.get('fancy') or TH['head']
    L = text_img(wrap_text(txt, key, 92, 940), key, 92, fill=TH['acc'] if TH['bg'] != 'image' else '#ffe7a8', align='center', spacing=1.1,
                 shadow=('#000000', 0, 5, 10), maxw=980)
    appear(img, L, W / 2, 860, t, 0.1, d=0.5)
    if sc.get('sub'):
        appear(img, T(sc['sub'], TH['body'], 48, fill=TH['acc2'], maxw=960), W / 2, 860 + L.height / 2 + 70, t, 0.9, d=0.4)


def wrap_text(text, key, size, maxw):
    f = F(key, size); out = []
    for para in text.split('\n'):
        cur = ''
        for w_ in para.split():
            trial = (cur + ' ' + w_).strip()
            if f.getlength(trial) <= maxw: cur = trial
            else: out.append(cur); cur = w_
        out.append(cur)
    return '\n'.join(out)


def r_bullets(img, sc, t, D):
    title = sc.get('title')
    items = sc.get('items', [])[:4]
    numbered = sc.get('numbered', False)
    has_sub = any(isinstance(it, (list, tuple)) and len(it) > 1 and it[1] for it in items)
    block = (170 if title else 0) + len(items) * 235 - 35 + (90 if sc.get('foot') else 0)
    top = max(220, 930 - block / 2)
    if title:
        appear(img, head(title, min(TH['maxHead'], 110)), W / 2, top + 60, t, 0.0)
    y0 = top + (170 if title else 0) + (100 if has_sub else 75)
    for i, it in enumerate(items):
        ttl, sub = (it[0], it[1] if len(it) > 1 else '') if isinstance(it, (list, tuple)) else (it, '')
        C = item_card(i, ttl, sub, numbered)
        st = 0.45 + i * 0.45
        k = eo(prog(t, st, st + 0.4))
        if k > 0:
            dx = (1 - k) * (1 if i % 2 == 0 else -1) * 1000
            put(img, shadow_of(C, 18, '#000000', 0.5), W / 2 + dx + 8, y0 + i * 235 + 12, a=k)
            put(img, C, W / 2 + dx, y0 + i * 235, a=k)
    if sc.get('foot'):
        appear(img, T(sc['foot'], TH['body'], 40, fill=TH['acc2'], maxw=960), W / 2, y0 + len(items) * 235 + 10, t, 0.45 + len(items) * 0.45 + 0.2)


def r_big(img, sc, t, D):
    if sc.get('kicker'):
        appear(img, T(sc['kicker'].upper(), hb('body') if TH['head'] != 'anton' else 'anton', 60, fill=TH['acc2'], maxw=960, tracking=2), W / 2, 430, t, 0.05)
    big = sc.get('big', '')
    key = 'archx' if TH['bg'] == 'navy' else TH.get('fancy') or TH['head']
    L = text_img(big, key, 300, fill=TH['acc'] if TH['bg'] != 'image' else None, grad=GOLDG if TH['bg'] == 'image' else None,
                 shadow=('#000000', 0, 8, 16), maxw=980)
    appear(img, L, W / 2, 640, t, 0.3, d=0.3 if TH['trans'] == 'soft' else 0.18, s0=1.6)
    if sc.get('sub'):
        appear(img, head(sc['sub'], 92), W / 2, 830, t, 0.45)
    for j, c in enumerate(sc.get('checks', [])[:4]):
        k = eo(prog(t, 1.0 + j * 0.3, 1.3 + j * 0.3))
        if k > 0:
            put(img, badge('check', 66), 160, 990 + j * 95 + (1 - k) * 20, a=k)
            put(img, T(c, TH['body'] if TH['body'] != 'cinzel' else 'corm', 46 if TH['body'] != 'cinzel' else 52, maxw=820), 215, 990 + j * 95 + (1 - k) * 20, a=k, anchor='l')


def r_chat(img, sc, t, D):
    msgs = sc.get('messages', [])[:6]
    bubbles = [bubble_img(m[1] if isinstance(m, (list, tuple)) else m, (m[0] if isinstance(m, (list, tuple)) else 'them') in ('me', 'ai', 'right')) for m in msgs]
    block = (150 if sc.get('title') else 0) + sum(b.height + 26 for b in bubbles)
    top = max(220, 920 - block / 2)
    if sc.get('title'):
        appear(img, head(sc['title'], min(TH['maxHead'], 100)), W / 2, top + 50, t, 0.0)
    y = top + (150 if sc.get('title') else 0)
    st = 0.4
    for i, m in enumerate(msgs[:6]):
        side, text = (m[0], m[1]) if isinstance(m, (list, tuple)) else ('them', m)
        mine = side in ('me', 'ai', 'right')
        B = bubbles[i]
        k = eback(prog(t, st, st + 0.25), 1.6)
        if k > 0:
            x = W - 60 - B.width / 2 if mine else 60 + B.width / 2
            put(img, B, x, y + B.height / 2, a=clamp(k), s=lerp(0.8, 1, clamp(k)))
        y += B.height + 26
        st += max(0.7, len(text.split()) * 0.22)
        if y > 1500:
            break


def r_xlist(img, sc, t, D):
    if sc.get('title'):
        appear(img, head(sc['title'], min(TH['maxHead'], 120)), W / 2, 330, t, 0.0)
    items = sc.get('items', [])[:6]
    pos = [(300, 640), (780, 640), (300, 830), (780, 830), (300, 1020), (780, 1020)]
    if len(items) % 2 == 1:
        pos[len(items) - 1] = (540, pos[len(items) - 1][1])
    for j, wd in enumerate(items):
        key = 'vt' if TH['bg'] == 'ink' else hb('body') if TH['head'] != 'anton' else 'anton'
        L0 = text_img(wd, key, 76 if key == 'vt' else 56, fill=TH['cardInk'], maxw=380)
        C = card_box(L0.width + 40, 130, TH['card'], TH['cardLine'], 22).copy()
        C.paste(L0, (C.width // 2 - L0.width // 2 - (7 if TH['bg'] == 'ink' else 0), 65 - L0.height // 2), L0)
        a = eo(prog(t, 0.3 + j * 0.08, 0.5 + j * 0.08))
        put(img, C, pos[j][0], pos[j][1] + (1 - a) * 30, a=a)
        xk = eo(prog(t, 0.9 + j * 0.3, 1.0 + j * 0.3))
        if xk > 0:
            X = Image.new('RGBA', ((C.width + 20) * 2, 300), (0, 0, 0, 0)); d = ImageDraw.Draw(X)
            d.line([(10, 10), (X.width - 10, 290)], fill=hexc('#e5322b'), width=26); d.line([(X.width - 10, 10), (10, 290)], fill=hexc('#e5322b'), width=26)
            X = X.resize((C.width + 20, 150), Image.LANCZOS)
            put(img, X, pos[j][0], pos[j][1], a=xk, s=lerp(1.8, 1, xk))
    if sc.get('after'):
        appear(img, T(sc['after'], 'vt' if TH['bg'] == 'ink' else TH['body'], 70 if TH['bg'] == 'ink' else 50, fill=TH['acc2'], maxw=960),
               W / 2, 1260, t, 0.9 + len(items) * 0.3 + 0.2, d=0.3)


@functools.lru_cache(None)
def tarot(path, h):
    im = load(path, 'RGBA'); w = int(im.width * h / im.height)
    im = im.resize((w, h), Image.LANCZOS)
    m = Image.new('L', (w * 2, h * 2), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, w * 2 - 1, h * 2 - 1], 36, fill=255)
    im.putalpha(ImageChops.multiply(im.getchannel('A'), m.resize((w, h), Image.LANCZOS)))
    return im


def r_card(img, sc, t, D):
    put(img, radial(1200, 1400, '#6b2277', 0.0, 1.8, 0.5), W / 2, 900)
    if sc.get('kicker'):
        put(img, text_img(sc['kicker'].upper(), 'cinzel', 42, fill='#d6a64b', tracking=10, glow='#000000', glow_r=8, glow_k=1.4), W / 2, 285, a=eo(prog(t, 0, 0.4)))
    if sc.get('name'):
        appear(img, head(sc['name'], 70), W / 2, 365, t, 0.05)
    path = VEIL + sc.get('card', '')
    if os.path.exists(path):
        k = eo(prog(t, 0.1, 0.6))
        C = tarot(path, 880)
        put(img, shadow_of(C, 30, '#000000', 0.85), W / 2 + 10, 905 + 26 + (1 - k) * 200, a=k * 0.9)
        put(img, C, W / 2, 905 + (1 - k) * 200 + 8 * math.sin(t * 2), a=min(1, k * 1.4), rot=(1 - k) * -6)
    words = sc.get('words', [])[:3]
    if words:
        size = 54
        while True:
            ws = [text_img(w_.upper(), 'cinzelb', size, fill='#ffe7a8', tracking=3, glow='#d6a64b', glow_r=12, shadow=('#000000', 0, 3, 8)) for w_ in words]
            total = sum(L.width - 88 for L in ws) + 2 * 90
            if total <= 940 or size <= 30: break
            size -= 2
        x = W / 2 - total / 2
        for j, L in enumerate(ws):
            wk = eback(prog(t, 0.9 + j * 0.45, 1.3 + j * 0.45), 2.0)
            lw = L.width - 88
            put(img, L, x + lw / 2, 1440, a=clamp(wk), s=lerp(0.6, 1, clamp(wk)))
            x += lw
            if j < len(ws) - 1:
                put(img, star_img(9, '#d6a64b', 4, 0.4), x + 45, 1440, a=clamp(wk)); x += 90
    if sc.get('sub'):
        put(img, text_img(sc['sub'], 'corm', 44, fill='#d8cff5', glow='#000000', glow_r=8, glow_k=1.3, maxw=960), W / 2, 1530, a=eo(prog(t, 2.2, 2.6)))


@functools.lru_cache(None)
def logo_layer(kind):
    if kind in ('veil', 'academy') and os.path.exists(VEIL + 'veil-logo.webp'):
        lg = load(VEIL + 'veil-logo.webp').resize((620, 620), Image.LANCZOS).convert('RGBA')
        lg.putalpha(radial(620, 620, '#ffffff', 0.55, 1.4, 1.0).getchannel('A'))
        return lg
    if kind == 'frickfake':
        a_ = text_img('FRICK', 'anton', 230, fill='#f3ece0'); b_ = text_img('FAKE', 'anton', 230, fill='#f3ece0')
        L = Image.new('RGBA', (max(a_.width, b_.width), a_.height + b_.height - 70), (0, 0, 0, 0))
        L.paste(a_, ((L.width - a_.width) // 2, 0), a_); L.paste(b_, ((L.width - b_.width) // 2, a_.height - 70), b_)
        bar = Image.new('RGBA', (620, 46), hexc('#e5322b')).rotate(10, expand=True, resample=Image.BICUBIC)
        L.paste(bar, (L.width // 2 - bar.width // 2, a_.height - 70 + b_.height // 2 - bar.height // 2 + 10), bar)
        return L
    if kind == 'uaom':
        T1 = text_img('Ultimate AI Office Master', 'archb', 56, fill='#ffffff')
        return T1
    if kind == 'outlaw':
        return text_img('OUTLAW BUILT MEDIA', 'rye', 70, fill='#d9a441', glow='#000000', glow_r=8, glow_k=1.3, maxw=900)
    if kind == 'pocket':
        return text_img('POCKET BUILT', 'anton', 170, fill='#f3ece0', shadow=('#e5322b', 7, 7, 0))
    return None


def r_cta(img, sc, t, D):
    lg = logo_layer(sc.get('logo') or '')
    y = 330
    if lg is not None:
        k = eo(prog(t, 0, 0.5))
        put(img, lg, W / 2, y + lg.height / 2 - 40, a=k, s=lerp(0.92, 1, k))
        y += lg.height + 10
    if sc.get('kicker'):
        appear(img, T(sc['kicker'], TH['body'] if TH['body'] != 'cinzel' else 'cinzel', 52, fill=TH['acc2'], maxw=960), W / 2, y + 30, t, 0.3)
        y += 100
    if sc.get('headline'):
        L = head(wrap_text(sc['headline'], TH['head'], min(TH['maxHead'], 120), 940), min(TH['maxHead'], 120), TH['acc'])
        appear(img, L, W / 2, y + L.height / 2, t, 0.45)
        y += L.height + 40
    y = max(y, 1080)
    if sc.get('url'):
        k = eback(prog(t, 0.9, 1.3), 1.6)
        if k > 0:
            if TH['bg'] == 'ink':
                u = text_img(sc['url'], 'vt', 84, fill='#0d0c0b', maxw=860)
                box = card_box(940, 170, '#cdc6ba', '#0d0c0b').copy()
                box.paste(u, (470 - u.width // 2 - 7, 85 - u.height // 2), u)
            else:
                key = 'cinzelb' if TH['bg'] == 'image' else 'archb' if TH['bg'] == 'navy' else 'grotb'
                u = text_img(sc['url'], key, 64, fill='#ffe7a8' if TH['bg'] == 'image' else '#ffffff', maxw=880)
                box = rrect((max(u.width + 40, 600), 130), 65, fill='#0b0b22' if TH['bg'] == 'image' else '#141111' if TH['bg'] in ('ember', 'pocket') else '#13263F',
                            outline=TH['acc'], width=4)
                box.paste(u, (box.width // 2 - u.width // 2, 65 - u.height // 2), u)
            put(img, box, W / 2, y + 70, a=clamp(k), s=lerp(0.8, 1, clamp(k)))
        y += 190
    if sc.get('button'):
        k = eback(prog(t, 1.3, 1.6), 1.8)
        if k > 0:
            lab = text_img(sc['button'], 'anton' if TH['head'] == 'anton' else hb('body'), 60, fill='#ffffff' if TH['bg'] != 'navy' else '#16202E')
            pill = rrect((lab.width + 70, 112), 56, fill=(TH['acc'] if TH['bg'] != 'navy' else '#FFFFFF'))
            pill.paste(lab, (35, 56 - lab.height // 2), lab)
            s = lerp(0.75, 1, clamp(k)) * (1 + 0.025 * math.sin(t * 6) * prog(t, 2.0, 2.3))
            put(img, pill, W / 2, y + 50, a=clamp(k), s=s)
        y += 140
    if sc.get('foot'):
        appear(img, T(sc['foot'], TH['body'] if TH['body'] != 'cinzel' else 'corm', 38, fill=TH['acc2'], maxw=980), W / 2, min(y + 20, 1540), t, 1.7)


RENDER = {'hook': r_hook, 'bullets': r_bullets, 'big': r_big, 'chat': r_chat, 'xlist': r_xlist, 'card': r_card, 'cta': r_cta, 'statement': r_statement}


# ------------------------------------------------------------------ sound
def build_audio(spec, starts, durs, path):
    total = sum(durs)
    m = A.Mix(total)
    style = TH['music']
    if style in ('jig', 'jig2'):
        E8 = 0.2 if style == 'jig' else 0.19; BAR = 6 * E8
        if style == 'jig':
            CH = {'a': (40, 47, 52, 55, 59), 'b': (38, 45, 50, 54, 57)}; seq = 'abababba'
            mel = [(76,1),(76,1),(83,1),(83,1),(81,1),(83,1),(86,1),(83,1),(81,1),(78,1),(76,1),(74,1),(76,1),(76,1),(83,1),(83,1),(81,1),(83,1),(81,1),(78,1),(74,1),(78,1),(76,2),
                   (88,1),(88,1),(86,1),(83,1),(81,1),(83,1),(86,1),(83,1),(81,1),(78,1),(81,1),(83,1),(88,1),(86,1),(83,1),(81,1),(78,1),(74,1),(78,1),(81,1),(78,1),(76,3)]
            drone = [40, 47, 52]
        else:
            CH = {'a': (38, 45, 50, 54, 57), 'b': (43, 50, 55, 59, 62), 'c': (45, 52, 57, 61, 64)}; seq = 'abacabca'
            mel = [(81,1),(78,1),(81,1),(86,1),(81,1),(78,1),(79,1),(76,1),(79,1),(83,1),(79,1),(76,1),(81,1),(78,1),(81,1),(86,1),(88,1),(90,1),(88,1),(85,1),(81,1),(81,3),
                   (81,1),(78,1),(81,1),(86,1),(81,1),(78,1),(79,1),(83,1),(86,1),(88,1),(86,1),(83,1),(81,1),(78,1),(74,1),(76,1),(78,1),(76,1),(74,3),(74,3)]
            drone = [38, 45, 50]
        for b in range(int(total / BAR) + 1):
            t0 = b * BAR; c = CH[seq[b % len(seq)]]
            for k, nt in enumerate([c[0], c[2], c[3], c[1], c[2], c[4]]):
                m.add(A.ks(A.mtof(nt + 12), 1.3, 0.997, 0.62), t0 + k * E8, 0.22 if k else 0.3, pan=-0.3 + 0.1 * k, bus='harp')
            if b >= 1:
                m.add(A.bodhran(), t0, 0.42, bus='drum'); m.add(A.bodhran(0.3, 80), t0 + 3 * E8, 0.3, bus='drum')
                for k in (1, 2, 4, 5): m.add(A.tap(), t0 + k * E8, 0.16, pan=0.2, bus='drum')
        m.add(A.pad([A.mtof(x) for x in drone], total, 1.5, 2.0, 1200), 0, 0.2, bus='pad')
        t = 2 * BAR
        while t < total:
            for nt, d in mel:
                if t >= total: break
                m.add(A.whistle(A.mtof(nt), d * E8 * 0.98), t, 0.3, pan=0.1, bus='lead'); t += d * E8
        m.process('lead', lambda x: A.reverb(x, 1.6, 0.27)); m.process('harp', lambda x: A.reverb(x, 2.0, 0.33))
    elif style == 'chip':
        BEAT = 60 / 140; BAR = 4 * BEAT; E8 = BEAT / 2
        roots = [45, 41, 48, 43]
        riff = [[69,72,76,81,79,76,72,76],[77,81,84,81,79,77,76,72],[76,79,84,79,76,74,72,76],[74,79,83,86,83,79,74,71]]
        for b in range(int(total / BAR) + 1):
            t0 = b * BAR; r = roots[b % 4]
            for k in range(8): m.add(A.tri(A.mtof(r - 12 + (12 if k % 2 else 0)), E8 * 0.9), t0 + k * E8, 0.35, bus='bass')
            for q in range(4):
                tb = t0 + q * BEAT
                if b >= 1:
                    if q in (0, 2): m.add(A.kick(0.3, 160, 50, 12, 0.4), tb, 0.6, bus='drums')
                    else: m.add(A.lp(A.noise(0.15) * np.exp(-A.tt(0.15) * 25), 6000), tb, 0.35, bus='drums')
                m.add(A.hat(0.04), tb + E8, 0.18, bus='drums')
            if b >= 2:
                for k, nt in enumerate(riff[b % 4]): m.add(A.square(A.mtof(nt), E8 * 0.85, 0.25, 4), t0 + k * E8, 0.13, pan=0.15, bus='lead')
        m.process('lead', lambda x: A.reverb(x, 0.8, 0.15))
    elif style == 'corp':
        BEAT = 0.6; BAR = 4 * BEAT; E8 = BEAT / 2
        prog_ = [(50, (62,66,69,74)), (45, (61,64,69,73)), (47, (62,66,71,74)), (43, (62,67,71,74))]
        for b in range(int(total / BAR) + 1):
            t0 = b * BAR; root, ch = prog_[b % 4]
            m.add(A.pad([A.mtof(root - 12), A.mtof(ch[0] - 12), A.mtof(ch[1] - 12)], BAR + 0.6, 0.4, 0.6, 1400), t0, 0.16, bus='pad')
            for k in range(8): m.add(A.ks(A.mtof(ch[[0,1,2,3,2,1,2,3][k]] + 12), 0.7, 0.995, 0.75), t0 + k * E8, 0.14, pan=(-0.35 if k % 2 else 0.35), bus='keys')
            m.add(A.bass_sine(A.mtof(root - 12), BAR * 0.95, 0.8), t0, 0.32, bus='bass')
            for q in range(4):
                tb = t0 + q * BEAT
                if q in (0, 2): m.add(A.kick(0.35, 110, 45, 9, 0.2), tb, 0.55, bus='drums')
                else: m.add(A.clap(0.25), tb, 0.22, bus='drums')
                for s16 in range(4): m.add(A.hat(0.03), tb + s16 * BEAT / 4, 0.1 if s16 % 2 else 0.13, pan=0.3, bus='drums')
        m.process('keys', lambda x: A.reverb(x, 1.6, 0.3))
    elif style == 'western':
        BEAT = 60 / 140; BAR = 4 * BEAT; E8 = BEAT / 2; S16 = BEAT / 4
        riffs = [[57, None, 60, 62, 64, None, 65, 64], [62, None, 60, 58, 57, None, None, 52]]
        for b in range(int(total / BAR) + 2):
            tb0 = b * BAR
            for k, nt in enumerate(riffs[b % 2]):
                if nt:
                    g = A.ks(A.mtof(nt), 1.2, 0.998, 0.95); g = g * (1 + 0.25 * np.sin(2 * np.pi * 7 * A.tt(len(g) / A.SR)))
                    m.add(g, tb0 + k * E8, 0.32, pan=-0.25, bus='gtr')
            m.add(A.pad([A.mtof(33), A.mtof(40)], BAR + 0.5, 0.3, 0.4, 600), tb0, 0.18, bus='pad')
            if b >= 1:
                m.add(A.k808(1.3, 55), tb0, 0.75, bus='drums'); m.add(A.k808(0.8, 55), tb0 + 1.5 * BEAT, 0.6, bus='drums')
                m.add(A.clap(), tb0 + 2 * BEAT, 0.6, bus='drums'); m.add(A.snare(0.2), tb0 + 2 * BEAT, 0.25, bus='drums')
                for k in range(8): m.add(A.hat(0.05), tb0 + k * E8, 0.2 if k % 2 == 0 else 0.13, pan=0.3, bus='drums')
        mel = [(76,2),(81,2),(83,1),(84,1),(83,2),(81,4),(None,2),(79,2),(77,2),(76,4),(None,4)]
        t = 2 * BAR
        while t < total:
            for nt, d in mel:
                if nt and t < total: m.add(A.whistle(A.mtof(nt), d * E8 * 0.97, vib=0.012, breath=0.03), t, 0.2, pan=0.15, bus='lead')
                t += d * E8
        m.process('gtr', lambda x: A.reverb(x, 2.2, 0.3)); m.process('lead', lambda x: A.reverb(x, 2.4, 0.4))
    else:  # pop
        BEAT = 60 / 104; BAR = 4 * BEAT; S16 = BEAT / 4
        prog_ = [(48, (60,64,67,72)), (43, (59,62,67,71)), (45, (60,64,69,72)), (41, (60,65,69,72))]
        for b in range(int(total / BAR) + 2):
            t0 = b * BAR; root, ch = prog_[b % 4]
            for q in range(4):
                tb = t0 + q * BEAT
                if q in (0, 2): m.add(A.kick(), tb, 0.8, bus='drums')
                else: m.add(A.clap(), tb, 0.5, bus='drums')
                m.add(A.hat(), tb + BEAT / 2, 0.28, pan=0.3, bus='drums'); m.add(A.hat(), tb, 0.16, pan=0.3, bus='drums')
            m.add(A.bass_sine(A.mtof(root - 12), BEAT * 1.9, 1.2), t0, 0.55, bus='bass'); m.add(A.bass_sine(A.mtof(root - 12), BEAT * 1.9, 1.2), t0 + 2 * BEAT, 0.5, bus='bass')
            for k, nt in enumerate([ch[0], ch[1], ch[2], ch[3], ch[2], ch[1], ch[2], ch[3]] * 2):
                m.add(A.ks(A.mtof(nt), 0.6, 0.994, 0.85), t0 + k * S16, 0.16, pan=(-0.4 if k % 2 else 0.4), bus='keys')
        m.process('keys', lambda x: A.reverb(x, 1.4, 0.25))
    # scene sound effects
    punchy = TH['trans'] in ('punch', 'glitch')
    for idx, (sc, t0, d) in enumerate(zip(spec['scenes'], starts, durs)):
        ty = sc['type']
        if idx > 0:
            m.add(A.whoosh(0.5, 0.6), t0 - 0.3, 0.35, bus='sfx')
        if ty == 'hook':
            for i in range(len(sc.get('lines', []))):
                if punchy:
                    m.add(A.kick(0.5, 160, 45, 8, 0.6), t0 + 0.1 + i * 0.42, 0.7, bus='sfx'); m.add(A.stamp(), t0 + 0.1 + i * 0.42, 0.35, bus='sfx')
            if idx == 0: m.add(A.boom(1.6), t0, 0.55 if punchy else 0.3, bus='sfx')
        elif ty in ('bullets',):
            for i in range(len(sc.get('items', [])[:4])): m.add(A.whoosh(0.35, 0.5, 700, 7000), t0 + 0.35 + i * 0.45, 0.22, bus='sfx')
        elif ty == 'big':
            m.add(A.boom(1.6), t0 + 0.3, 0.45, bus='sfx'); m.add(A.shimmer(1174.7, 1.6), t0 + 0.3, 0.12, bus='sfx')
        elif ty == 'chat':
            st = 0.4
            for msg in sc.get('messages', [])[:6]:
                text = msg[1] if isinstance(msg, (list, tuple)) else msg
                m.add(A.ping(), t0 + st, 0.4, bus='sfx'); st += max(0.7, len(text.split()) * 0.22)
        elif ty == 'xlist':
            for j in range(len(sc.get('items', [])[:6])): m.add(A.stamp(), t0 + 0.9 + j * 0.3, 0.5, bus='sfx')
        elif ty == 'card':
            for j in range(3): m.add(A.bell(A.mtof(86 + (0, 4, 7)[j]), 1.2, 3), t0 + 0.9 + j * 0.45, 0.16, bus='sfx')
        elif ty == 'cta':
            m.add(A.boom(1.8), t0 + 0.2, 0.4, bus='sfx'); m.add(A.ping(), t0 + 1.0, 0.3, bus='sfx')
    m.process('sfx', lambda x: A.reverb(x, 1.0, 0.12))
    return m.render(path, fade_out=1.0)


# ------------------------------------------------------------------ main
def build(spec, out_dir):
    TH.clear(); TH.update(THEMES[spec['theme']])
    os.makedirs(out_dir, exist_ok=True)
    lib.OUT = out_dir.rstrip('/') + '/'
    slug = spec.get('slug') or re.sub(r'[^a-z0-9]+', '-', spec.get('title', 'reel').lower()).strip('-')[:60]
    scenes = spec['scenes']
    durs = [round(scene_duration(sc) * FPS) / FPS for sc in scenes]
    starts = [sum(durs[:i]) for i in range(len(durs))]
    S = []
    for idx, (sc, d) in enumerate(zip(scenes, durs)):
        def mk(sc=sc, d=d, idx=idx):
            fn = RENDER[sc['type']]
            def frame(t, i):
                img = background(sc, t, t / d, idx)
                fn(img, sc, t, d)
                if idx == len(scenes) - 1 and t > d - 0.6 and TH['trans'] == 'soft':
                    pass
                return finish(img, t, i, idx)
            return frame
        S.append((f'{slug}_s{idx}', int(round(d * FPS)), mk()))
    wav = os.path.join(out_dir, slug + '.wav')
    build_audio(spec, starts, durs, wav)
    raw = render_all(slug + '_raw', S, wav, workers=int(os.environ.get('REEL_WORKERS', '4')))
    final = os.path.join(out_dir, slug + '.mp4'); tmp = final + '.tmp.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', raw, '-map', '0:v', '-map', '0:a', '-c:v', 'copy', '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11',
                    '-ar', '44100', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', tmp], check=True)
    os.replace(tmp, final)
    # cover image: end of the hook
    cov_t = min(durs[0] - 0.1, 0.1 + len(scenes[0].get('lines', [1, 1])) * 0.42 + 0.6)
    S[0][2](cov_t, int(cov_t * FPS)).convert('RGB').save(os.path.join(out_dir, slug + '.jpg'), quality=88)
    # tidy scene files
    for nm, _, _ in S:
        p = lib.OUT + nm + '.mp4'
        if os.path.exists(p): os.remove(p)
    for extra in (raw, lib.OUT + slug + '_raw_silent.mp4', lib.OUT + slug + '_raw_list.txt', wav):
        if os.path.exists(extra): os.remove(extra)
    return final, round(sum(durs), 2)


def stills(spec, out_dir, per_scene=1):
    TH.clear(); TH.update(THEMES[spec['theme']])
    os.makedirs(out_dir, exist_ok=True)
    ims = []
    for idx, sc in enumerate(spec['scenes']):
        d = scene_duration(sc)
        t = d * 0.8
        img = background(sc, t, t / d, idx); RENDER[sc['type']](img, sc, t, d); ims.append(finish(img, t, int(t * FPS), idx).convert('RGB'))
    th = 300; sh = int(th * H / W)
    sheet = Image.new('RGB', (th * len(ims), sh), 'white')
    for k, im in enumerate(ims): sheet.paste(im.resize((th, sh), Image.LANCZOS), (k * th, 0))
    p = os.path.join(out_dir, 'stills_' + (spec.get('slug') or 'reel') + '.jpg'); sheet.save(p, quality=85)
    return p


if __name__ == '__main__':
    spec = json.load(open(sys.argv[1]))
    out = sys.argv[2] if len(sys.argv) > 2 else lib.OUT
    if len(sys.argv) > 3 and sys.argv[3] == '--stills':
        print(stills(spec, out))
    else:
        f, d = build(spec, out)
        print(json.dumps({'video': f, 'cover': f[:-4] + '.jpg', 'seconds': d}))
