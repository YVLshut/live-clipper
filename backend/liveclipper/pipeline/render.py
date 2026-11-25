"""5. Montage 9:16 + sous-titres karaoké + accroche (repris de clipper.render)."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .utils import CancelCheck, never_cancel, run, tool

log = logging.getLogger("liveclipper.render")


def ass_time(t: float) -> str:
    cs = int(round(max(0, t) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def esc(t: str) -> str:
    return t.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").upper()


def write_ass(path: Path, words: list[dict], t0: float, dur: float, hook: str, layout: str,
              font: str = "Arial Black", words_per_line: int = 3) -> None:
    y = 1480 if layout == "blur" else 1380
    f = font
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{f},82,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,5,60,60,0,1
Style: Hook,{f},62,&H00000000,&H00000000,&H0000D7FF,&H0000D7FF,-1,0,0,0,100,100,0,0,3,20,0,8,90,90,250,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    groups, cur = [], []
    for w in words:
        if cur and (len(cur) >= words_per_line or w["s"] - cur[-1]["e"] > 0.6):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    ev = []
    for g in groups:
        for i, w in enumerate(g):
            st = w["s"] - t0
            en = (g[i + 1]["s"] if i + 1 < len(g) else w["e"]) - t0
            if en <= 0 or st >= dur:
                continue
            txt = " ".join(("{\\c&H0000E5FF&}" + esc(x["w"]) + "{\\c&H00FFFFFF&}") if j == i else esc(x["w"])
                           for j, x in enumerate(g))
            ev.append(f"Dialogue: 0,{ass_time(st)},{ass_time(min(en, dur))},Sub,,0,0,0,,"
                      f"{{\\pos(540,{y})\\fscx108\\fscy108\\t(0,90,\\fscx100\\fscy100)}}{txt}")
    if hook:
        ev.append(f"Dialogue: 1,{ass_time(0)},{ass_time(min(3.5, dur))},Hook,,0,0,0,,{esc(hook)}")
    path.write_text(head + "\n".join(ev) + "\n", encoding="utf-8")


def render_clip(video: Path, segs: list[dict], start: float, end: float, hook: str, layout: str,
                out_dir: Path, cfg: dict, cancel: CancelCheck = never_cancel) -> Path:
    """Monte un clip dans out_dir/clip.mp4 et renvoie son chemin."""
    out_dir.mkdir(parents=True, exist_ok=True)
    st, dur = start, end - start
    words = [w for s in segs for w in s.get("words", []) if w["s"] >= st - 0.05 and w["e"] <= end + 0.05]
    write_ass(out_dir / "subs.ass", words, st, dur, hook or "", layout,
              cfg.get("font") or "Arial Black", int(cfg.get("words_per_line") or 3))
    ass = "ass=subs.ass"  # chemin relatif (cwd=out_dir) : évite l'échappement des chemins Windows
    if layout == "crop":
        graph = f"[0:v]crop=ih*9/16:ih,scale=1080:1920,setsar=1,{ass}[v]"
    else:  # blur : vidéo entière au centre, fond flou
        graph = ("[0:v]split=2[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,"
                 "crop=1080:1920,boxblur=25:2,eq=brightness=-0.08[bg];[b]scale=1080:-2[fg];"
                 f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,{ass}[v]")
    tmp = out_dir / "clip.tmp.mp4"

    def encode(encoder: str) -> None:
        run([tool("ffmpeg"), "-y", "-v", "error", "-ss", f"{st:.2f}", "-i", str(Path(video).resolve()),
             "-t", f"{dur:.2f}", "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
             "-c:v", encoder, "-preset", "veryfast" if encoder == "libx264" else "p4",
             "-crf" if encoder == "libx264" else "-cq", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", tmp.name], cwd=out_dir, cancel=cancel)

    enc = cfg.get("encoder") or "libx264"
    try:
        encode(enc)
    except subprocess.CalledProcessError as e:
        if enc == "libx264":
            raise
        log.warning("Encodeur %s indisponible (%s) : repli sur libx264", enc, (e.stderr or "")[-200:])
        encode("libx264")
    final = out_dir / "clip.mp4"
    tmp.replace(final)
    return final
