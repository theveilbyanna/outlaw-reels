"""Tiny numpy synth: instruments, drums, SFX and a mixer for the reels."""
import numpy as np
from scipy import signal
import wave

SR = 44100
_rng = np.random.default_rng(7)


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def tt(d):
    return np.arange(int(d * SR)) / SR


def env(n, a=0.01, r=0.05, hold=None):
    e = np.ones(n)
    na, nr = max(1, int(a * SR)), max(1, int(r * SR))
    e[:na] = np.linspace(0, 1, na)
    if nr < n:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def lp(x, f, order=2):
    sos = signal.butter(order, min(f, SR / 2 - 100), 'low', fs=SR, output='sos')
    return signal.sosfilt(sos, x)


def hp(x, f, order=2):
    sos = signal.butter(order, f, 'high', fs=SR, output='sos')
    return signal.sosfilt(sos, x)


def bp(x, lo, hi, order=2):
    sos = signal.butter(order, [lo, min(hi, SR / 2 - 100)], 'band', fs=SR, output='sos')
    return signal.sosfilt(sos, x)


def noise(d, seed=None):
    r = np.random.default_rng(seed) if seed is not None else _rng
    return r.uniform(-1, 1, int(d * SR))


# ------------------------------------------------------------ instruments
def ks(freq, dur, decay=0.996, bright=0.7, seed=None):
    n = int(dur * SR); N = max(2, int(round(SR / freq)))
    r = np.random.default_rng(seed) if seed is not None else _rng
    buf = r.uniform(-1, 1, N)
    if bright < 1:
        for _ in range(int((1 - bright) * 6)):
            buf = 0.5 * (buf + np.roll(buf, 1))
    out = np.zeros(n + N + 1)
    out[1:N + 1] = buf
    i = N + 1
    while i < n + 1:
        j = min(i + N, n + 1)
        out[i:j] = decay * 0.5 * (out[i - N:j - N] + out[i - N - 1:j - N - 1])
        i = j
    y = out[1:n + 1]
    y = y - np.mean(y)
    return y * env(n, 0.002, 0.03)


def whistle(freq, dur, vib=0.006, breath=0.06, seed=None):
    t = tt(dur); n = len(t)
    vr = np.clip((t - 0.12) / 0.15, 0, 1)
    f = freq * (1 + vib * np.sin(2 * np.pi * 5.6 * t) * vr)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) + 0.10 * np.sin(2 * ph) + 0.035 * np.sin(3 * ph)
    b = bp(noise(dur, seed), freq * 0.8, freq * 2.5) * breath * 3
    y = y + b
    return y * env(n, 0.018, 0.06)


def pad(freqs, dur, a=1.2, r=1.5, bright=1800):
    t = tt(dur); y = np.zeros(len(t))
    for f in freqs:
        for det in (-0.004, 0.0, 0.005):
            ph = 2 * np.pi * f * (1 + det) * t + _rng.uniform(0, 6)
            # soft saw-ish via a few harmonics
            y += np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.15 * np.sin(3 * ph)
    y = lp(y, bright)
    y /= max(1e-9, np.abs(y).max())
    return y * env(len(t), a, r)


def square(freq, dur, duty=0.5, vol_dec=3.0):
    t = tt(dur)
    ph = (freq * t) % 1.0
    y = np.where(ph < duty, 1.0, -1.0)
    y = lp(y, 7000, 1)
    return y * env(len(t), 0.003, 0.02) * np.exp(-t * vol_dec)


def tri(freq, dur):
    t = tt(dur)
    ph = (freq * t) % 1.0
    y = 4 * np.abs(ph - 0.5) - 1
    return y * env(len(t), 0.003, 0.02)


def bass_sine(freq, dur, dec=1.5):
    t = tt(dur)
    y = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(4 * np.pi * freq * t)
    return y * env(len(t), 0.005, 0.05) * np.exp(-t * dec)


def bell(freq, dur=2.0, dec=2.5):
    t = tt(dur); y = np.zeros(len(t))
    for ratio, amp, dk in ((1, 1, 1), (2.756, .45, 1.6), (5.404, .25, 2.4), (8.93, .12, 3.5)):
        y += amp * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-t * dec * dk)
    return y * env(len(t), 0.002, 0.1)


# ------------------------------------------------------------ drums
def kick(d=0.5, f0=130, f1=45, dec=7.0, click=0.3):
    t = tt(d)
    f = f1 + (f0 - f1) * np.exp(-t * 25)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * dec)
    y[:200] += noise(200 / SR)[:200] * click * np.linspace(1, 0, 200)
    return y


def k808(d=1.2, f=55):
    t = tt(d)
    fr = f + f * np.exp(-t * 30)
    y = np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-t * 2.2)
    return np.tanh(y * 1.8) * 0.8


def snare(d=0.25, tone=190):
    t = tt(d)
    y = bp(noise(d), 1500, 9000) * np.exp(-t * 22) * 0.9
    y += np.sin(2 * np.pi * tone * t) * np.exp(-t * 30) * 0.5
    return y


def clap(d=0.3):
    t = tt(d)
    e = np.zeros(len(t))
    for o in (0, 0.011, 0.022):
        i = int(o * SR); e[i:] += np.exp(-(t[:len(t) - i]) * 60)
    e += np.exp(-t * 14) * 0.4
    return bp(noise(d), 900, 6000) * e * 0.8


def hat(d=0.06, open_=False):
    t = tt(0.3 if open_ else d)
    return hp(noise(len(t) / SR), 7000) * np.exp(-t * (12 if open_ else 70)) * 0.5


def bodhran(d=0.35, f0=95):
    t = tt(d)
    f = 60 + (f0 - 60) * np.exp(-t * 18)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 11)
    y += lp(noise(d), 600) * np.exp(-t * 25) * 0.6
    return y


def tap(d=0.12):
    t = tt(d)
    return bp(noise(d), 300, 1800) * np.exp(-t * 45) * 0.6


# ------------------------------------------------------------ sfx
def whoosh(d=0.7, peak=0.6, lo=300, hi=5000, seed=None):
    t = tt(d)
    x = noise(d, seed)
    low = bp(x, lo, lo * 3); high = bp(x, hi / 3, hi)
    k = np.clip(t / (d * peak), 0, 1)
    y = low * (1 - k) + high * k
    e = np.where(t < d * peak, (t / (d * peak)) ** 2, np.exp(-(t - d * peak) * 9))
    return y * e * 1.4


def riser(d=1.0):
    t = tt(d)
    f = 300 + 2500 * (t / d) ** 2
    y = bp(noise(d), 400, 6000) * (t / d) ** 2
    y += 0.2 * np.sin(2 * np.pi * np.cumsum(f) / SR) * (t / d) ** 2
    return y


def boom(d=1.8):
    t = tt(d)
    y = np.sin(2 * np.pi * np.cumsum(40 + 50 * np.exp(-t * 8)) / SR) * np.exp(-t * 2.4)
    y += lp(noise(d), 300) * np.exp(-t * 5) * 0.6
    return y


def shimmer(base=1318.5, d=2.4):
    y = np.zeros(int(d * SR))
    for k, m in enumerate((0, 4, 7, 12, 16, 19)):
        b = bell(base * 2 ** (m / 12), d - k * 0.06, 2.0) * 0.5
        i = int(k * 0.06 * SR); y[i:i + len(b)] += b
    return y


def ping(d=0.35):
    t = tt(d)
    y = np.sin(2 * np.pi * 1318.5 * t) * np.exp(-t * 18)
    t2 = t[int(0.07 * SR):]
    y2 = np.sin(2 * np.pi * 1975.5 * (t2 - t2[0])) * np.exp(-(t2 - t2[0]) * 14)
    y[int(0.07 * SR):] += y2
    return y * 0.6


def blip_uh_oh(d=0.45):
    t = tt(d); y = np.zeros(len(t))
    for st, f in ((0.0, 880), (0.16, 659)):
        i = int(st * SR); tl = t[:len(t) - i]
        y[i:] += square(f, len(tl) / SR, 0.5, 9)[:len(tl)] * 0.5
    return y


def stamp(d=0.5):
    t = tt(d)
    y = kick(d, 160, 50, 12, 0.6) * 0.9
    y += lp(noise(d), 2500) * np.exp(-t * 35) * 0.8
    return y


def click(d=0.05):
    t = tt(d)
    return hp(noise(d), 2000) * np.exp(-t * 200)


def whip(d=0.45):
    t = tt(d)
    f = 400 + 6000 * (t / 0.08).clip(0, 1)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-((t - 0.08) / 0.03) ** 2) * 0.6
    n = hp(noise(d), 2500) * np.exp(-np.abs(t - 0.085) * 60)
    return y + n * 1.4


def crackle(d, density=12, seed=3):
    r = np.random.default_rng(seed)
    y = np.zeros(int(d * SR))
    for _ in range(int(d * density)):
        i = r.integers(0, len(y) - 600)
        L = r.integers(80, 500)
        y[i:i + L] += hp(r.uniform(-1, 1, L), 1500) * np.exp(-np.arange(L) / (L / 4)) * r.uniform(0.2, 1)
    return y


def reverb(x, secs=1.8, mix=0.25, lpf=5000, seed=11):
    n = int(secs * SR)
    r = np.random.default_rng(seed)
    ir = r.uniform(-1, 1, n) * np.exp(-np.arange(n) / SR * (6.9 / secs))
    ir = lp(ir, lpf)
    ir /= np.sqrt((ir ** 2).sum())
    wet = signal.fftconvolve(x, ir)[:len(x)]
    return x * (1 - mix) + wet * mix * 1.2


# ------------------------------------------------------------ mixer
class Mix:
    def __init__(self, dur):
        self.n = int(dur * SR)
        self.buses = {}

    def bus(self, name):
        if name not in self.buses:
            self.buses[name] = np.zeros((self.n, 2))
        return self.buses[name]

    def add(self, sig, t0, gain=1.0, pan=0.0, bus='main'):
        b = self.bus(bus)
        i = int(t0 * SR)
        if i >= self.n or i + len(sig) <= 0:
            return
        s = sig
        if i < 0:
            s = s[-i:]; i = 0
        L = min(len(s), self.n - i)
        gl = gain * np.sqrt((1 - pan) / 2) * 1.414
        gr = gain * np.sqrt((1 + pan) / 2) * 1.414
        b[i:i + L, 0] += s[:L] * gl
        b[i:i + L, 1] += s[:L] * gr

    def process(self, name, fn):
        if name in self.buses:
            b = self.buses[name]
            b[:, 0] = fn(b[:, 0]); b[:, 1] = fn(b[:, 1])

    def render(self, path, fade_in=0.02, fade_out=0.8, peak_db=-1.0):
        out = np.zeros((self.n, 2))
        for b in self.buses.values():
            out += b
        out = np.tanh(out / max(1e-9, np.abs(out).max()) * 1.25)
        out /= np.abs(out).max()
        out *= 10 ** (peak_db / 20)
        fi, fo = int(fade_in * SR), int(fade_out * SR)
        out[:fi] *= np.linspace(0, 1, fi)[:, None]
        out[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5
        pcm = (out * 32767).astype(np.int16)
        with wave.open(path, 'wb') as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        return path
