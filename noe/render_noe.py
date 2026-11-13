#!/usr/bin/env python3
"""Assemble la vidéo « Le prophète Noé » (FR) : narration + illustrations 3D
stylisées avec panoramiques et zooms lents (effet Ken Burns), fondus
enchaînés et sous-titres SRT.

Dépendances : pillow, imageio-ffmpeg  (pip install pillow imageio-ffmpeg)
Usage       : python3 render_noe.py
"""
import os, re, subprocess, wave, zipfile
from PIL import Image
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "images")
AUD = os.path.join(HERE, "audio")
OUT_MP4 = os.path.join(HERE, "prophete_noe_fr_5min.mp4")
OUT_SRT = os.path.join(HERE, "noe_video_fr.srt")
OUT_ZIP = os.path.join(HERE, "prophete_noe_fr_package.zip")
SCRIPT = os.path.join(HERE, "script_noe_fr.md")

W, H, FPS = 1920, 1080, 25
SR = 24000
INTRO, GAP, OUTRO = 1.5, 1.2, 3.5   # silences (s)
XFADE = 1.2                           # fondu enchaîné entre images (s)

# Images par partie de narration, avec mouvement de caméra.
# Mouvements : zin / zout (zoom avant/arrière), pl / pr (panoramique gauche/droite),
#              pu / pd (panoramique haut/bas)
PARTS = [
    [("01_vallee", "zin"), ("02_idoles", "pr")],
    [("03_appel", "zout"), ("04_ciel", "pl")],
    [("05_notables", "zin"), ("06_croyants", "pr"), ("07_refus", "zout")],
    [("05_notables", "pl"), ("08_priere", "zin")],
    [("09_bois", "pr"), ("10_arche_construction", "zout"), ("11_planches_clous", "zin")],
    [("12_four", "zin"), ("13_animaux", "pl"), ("14_pluie", "zout"), ("15_vagues", "pr")],
    [("16_fils", "zin"), ("15_vagues", "zout"), ("08_priere", "pd")],
    [("17_calme", "zout"), ("18_joudi", "zin"), ("19_descente", "pr")],
]
# Remplacements si une image dédiée n'existe pas encore.
FALLBACK = {"16_fils": "14_pluie", "17_calme": "04_ciel",
            "18_joudi": "01_vallee", "19_descente": "01_vallee"}


def img_path(name):
    p = os.path.join(IMG, name + ".jpg")
    if not os.path.exists(p) and name in FALLBACK:
        return img_path(FALLBACK[name])
    return p


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def decode(mp3):
    wav = mp3[:-4] + ".wav"
    run([FF, "-y", "-i", mp3, "-ac", "1", "-ar", str(SR), "-sample_fmt", "s16", wav])
    with wave.open(wav) as w:
        data = w.readframes(w.getnframes())
    os.remove(wav)
    return data


def silence(sec):
    return b"\x00\x00" * int(sec * SR)


# ---------- audio ----------
pcm = bytearray(silence(INTRO))
part_spans = []
for i in range(len(PARTS)):
    data = decode(os.path.join(AUD, f"p{i+1}.mp3"))
    start = len(pcm) / 2 / SR
    pcm += data
    end = len(pcm) / 2 / SR
    part_spans.append((start, end))
    pcm += silence(GAP if i < len(PARTS) - 1 else OUTRO)
TOTAL = len(pcm) / 2 / SR
narr_wav = os.path.join(HERE, "_narration.wav")
with wave.open(narr_wav, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(bytes(pcm))
print(f"Durée totale : {TOTAL:.1f}s ({TOTAL/60:.2f} min)")

# ---------- plan des images ----------
shots = []  # (t0, t1, image, move)
for i, imgs in enumerate(PARTS):
    s0 = 0.0 if i == 0 else part_spans[i][0] - GAP / 2
    s1 = TOTAL if i == len(PARTS) - 1 else part_spans[i][1] + GAP / 2
    step = (s1 - s0) / len(imgs)
    for k, (name, mv) in enumerate(imgs):
        shots.append([s0 + k * step, s0 + (k + 1) * step, name, mv])

cache = {}
def load(name):
    if name not in cache:
        im = Image.open(img_path(name)).convert("RGB")
        # recadrage 16:9 puis agrandissement pour un mouvement fluide
        iw, ih = im.size
        tw = min(iw, int(ih * 16 / 9)); th = int(tw * 9 / 16)
        im = im.crop(((iw - tw) // 2, (ih - th) // 2, (iw - tw) // 2 + tw, (ih - th) // 2 + th))
        cache[name] = im.resize((int(W * 1.4), int(H * 1.4)), Image.LANCZOS)
    return cache[name]


def ease(x):
    return x * x * (3 - 2 * x)


def frame_of(shot, t):
    t0, t1, name, mv = shot
    im = load(name)
    iw, ih = im.size
    p = ease(min(max((t - (t0 - XFADE / 2)) / (t1 - t0 + XFADE), 0), 1))
    z0, z1 = 1.0, 1.0
    cx0 = cy0 = cx1 = cy1 = 0.5
    if mv == "zin":  z0, z1 = 1.0, 1.25
    if mv == "zout": z0, z1 = 1.25, 1.0
    if mv in ("pl", "pr", "pu", "pd"):
        z0 = z1 = 1.18
        d = 0.5 - 0.5 / z0  # amplitude max
        if mv == "pl": cx0, cx1 = 0.5 + d, 0.5 - d
        if mv == "pr": cx0, cx1 = 0.5 - d, 0.5 + d
        if mv == "pu": cy0, cy1 = 0.5 + d, 0.5 - d
        if mv == "pd": cy0, cy1 = 0.5 - d, 0.5 + d
    z = z0 + (z1 - z0) * p
    cw, ch = iw / z, ih / z
    cx = (cx0 + (cx1 - cx0) * p) * iw
    cy = (cy0 + (cy1 - cy0) * p) * ih
    cx = min(max(cx, cw / 2), iw - cw / 2); cy = min(max(cy, ch / 2), ih - ch / 2)
    box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
    return im.resize((W, H), Image.BILINEAR, box=box)


# ---------- vidéo ----------
enc = subprocess.Popen([FF, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                        "-r", str(FPS), "-i", "-", "-i", narr_wav,
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-shortest",
                        "-movflags", "+faststart", OUT_MP4],
                       stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
black = Image.new("RGB", (W, H))
nframes = int(TOTAL * FPS)
for f in range(nframes):
    t = f / FPS
    idx = next(i for i, s in enumerate(shots) if t < s[1] or i == len(shots) - 1)
    fr = frame_of(shots[idx], t)
    # fondu enchaîné avec l'image suivante
    if idx + 1 < len(shots) and t > shots[idx][1] - XFADE / 2:
        a = (t - (shots[idx][1] - XFADE / 2)) / XFADE
        fr = Image.blend(fr, frame_of(shots[idx + 1], t), ease(min(a, 1)))
    elif idx > 0 and t < shots[idx][0] + XFADE / 2:
        a = 0.5 + (t - shots[idx][0]) / XFADE
        fr = Image.blend(frame_of(shots[idx - 1], t), fr, ease(min(max(a, 0), 1)))
    # fondu au noir début / fin
    if t < 1.5:
        fr = Image.blend(black, fr, t / 1.5)
    elif t > TOTAL - 2.5:
        fr = Image.blend(black, fr, max((TOTAL - t) / 2.5, 0))
    enc.stdin.write(fr.tobytes())
    if f % (FPS * 30) == 0:
        print(f"  {t:6.1f}s / {TOTAL:.1f}s", flush=True)
enc.stdin.close(); enc.wait()
os.remove(narr_wav)

# ---------- sous-titres ----------
txt = open(SCRIPT, encoding="utf-8").read()
paras = re.findall(r"## Partie \d+ — .*?\n\n(.*?)\n\n\[", txt, re.S)


def chunks(p):
    # découpe en phrases puis en morceaux courts (≤ ~90 caractères)
    sents = re.findall(r"[^.!?»]+(?:[.!?]+(?:\s*»)?|»|$)", p)
    out = []
    for s in (x.strip() for x in sents):
        if not s:
            continue
        while len(s) > 90:
            cut = s.rfind(" ", 0, 80)
            for sep in (", ", " : ", " ; "):
                c = s.rfind(sep, 30, 88)
                if c > 0:
                    cut = c + len(sep.rstrip()); break
            out.append(s[:cut].strip()); s = s[cut:].strip()
        out.append(s)
    return out


def ts(x):
    ms = int(round(x * 1000))
    return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"


lines, n = [], 1
for (s, e), p in zip(part_spans, paras):
    cs = chunks(p)
    total_chars = sum(len(c) for c in cs)
    t = s
    for c in cs:
        d = (e - s) * len(c) / total_chars
        lines.append(f"{n}\n{ts(t)} --> {ts(t + d - 0.05)}\n{c}\n")
        t += d; n += 1
open(OUT_SRT, "w", encoding="utf-8").write("\n".join(lines))

with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    for f in (OUT_MP4, SCRIPT, OUT_SRT):
        z.write(f, os.path.basename(f))
print("OK :", OUT_MP4, OUT_SRT, OUT_ZIP)
