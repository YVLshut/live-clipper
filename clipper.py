#!/usr/bin/env python3
"""
clipper.py - Live -> clips verticaux sous-titres -> Instagram / TikTok

  python clipper.py clip URL [--max-clips 5] [--layout blur|crop] [--section 00:30:00-01:30:00]
  python clipper.py list
  python clipper.py approve ID [ID ...] | --all
  python clipper.py reject ID [ID ...]
  python clipper.py post [--platform tiktok instagram] [--publish] [--limit 3]

Par defaut, `post` prepare les publications dans ton Chrome sans cliquer sur
"Publier" (tu verifies et tu cliques). Avec --publish, le clic est automatique.
"""
import argparse, json, random, re, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK, OUT, MANIFEST = ROOT / "work", ROOT / "clips", ROOT / "manifest.json"

DEFAULTS = {
    "whisper_model": "large-v3", "device": "cuda", "compute_type": "float16",
    "language": "fr", "min_len": 15, "max_len": 60, "max_clips": 5,
    "layout": "blur", "font": "Arial Black", "words_per_line": 3,
    "encoder": "libx264", "cdp_url": "http://127.0.0.1:9222",
    "default_hashtags": ["#live", "#clip", "#fyp"],
    "delay_between_posts_sec": [90, 180],
}
CFG_FILE = ROOT / "config.json"
C = {**DEFAULTS, **(json.loads(CFG_FILE.read_text(encoding="utf-8")) if CFG_FILE.exists() else {})}


# ---------------------------------------------------------------- utils
def run(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd)[:200])
    return subprocess.run(cmd, check=True, **kw)

def to_sec(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = 0.0
    for p in str(v).strip().split(":"):
        s = s * 60 + float(p)
    return s

def hms(s):
    s = int(s)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"

def safe(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(s))[:60]

def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else []

def save_manifest(m):
    MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


# ---------------------------------------------------------------- 1. source + telechargement
def download(url, section=None):
    WORK.mkdir(exist_ok=True)
    info = json.loads(subprocess.run(["yt-dlp", "-J", "--no-warnings", url],
                                     capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    vid = safe(info.get("id") or "live")
    d = WORK / vid
    d.mkdir(exist_ok=True)
    src = {
        "id": vid,
        "url": info.get("webpage_url") or url,
        "author": info.get("uploader") or info.get("channel") or info.get("uploader_id") or "inconnu",
        "author_url": info.get("uploader_url") or info.get("channel_url"),
        "title": info.get("title"),
        "platform": info.get("extractor_key"),
        "date": info.get("upload_date") or info.get("release_date"),
        "was_live": bool(info.get("is_live") or info.get("was_live")),
    }
    (d / "source.json").write_text(json.dumps(src, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Source : {src['author']} - {src['title']} ({src['url']})")

    video = d / "video.mp4"
    if not video.exists():
        cmd = ["yt-dlp", "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
               "--merge-output-format", "mp4", "-o", str(video)]
        if section:
            cmd += ["--download-sections", f"*{section}"]
        if info.get("is_live"):
            print("  Live en cours : l'enregistrement continue jusqu'a la fin du live (Ctrl+C pour couper).")
            cmd += ["--live-from-start"]
        run(cmd + [url])
    audio = d / "audio.wav"
    if not audio.exists():
        run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-ac", "1", "-ar", "16000", str(audio)])
    return d, src


# ---------------------------------------------------------------- 2. transcription
def transcribe(d):
    out = d / "transcript.json"
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))
    print("Transcription (Whisper)...")
    from faster_whisper import WhisperModel
    model = WhisperModel(C["whisper_model"], device=C["device"], compute_type=C["compute_type"])
    segs, _ = model.transcribe(str(d / "audio.wav"), language=C["language"],
                               word_timestamps=True, vad_filter=True)
    data = []
    for s in segs:
        data.append({"start": s.start, "end": s.end, "text": s.text.strip(),
                     "words": [{"s": w.start, "e": w.end, "w": w.word.strip()} for w in (s.words or [])]})
        print(f"\r  {hms(s.end)}", end="", flush=True)
    print()
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


# ---------------------------------------------------------------- 3. pics de volume (rires, cris...)
def loudness_peaks(d, top=60):
    import numpy as np
    a = np.memmap(d / "audio.wav", dtype=np.int16, mode="r", offset=44)
    n = len(a) // 16000
    db = np.empty(n, dtype=np.float32)
    for i in range(0, n, 600):
        blk = np.asarray(a[i * 16000:min(n, i + 600) * 16000], dtype=np.float32) / 32768
        blk = blk.reshape(-1, 16000)
        db[i:i + len(blk)] = 20 * np.log10(np.sqrt((blk ** 2).mean(1)) + 1e-6)
    sm = np.convolve(db, np.ones(5) / 5, mode="same")
    z = (sm - sm.mean()) / (sm.std() + 1e-6)
    picked = []
    for i in np.argsort(-z):
        if all(abs(int(i) - p) > 45 for p in picked):
            picked.append(int(i))
        if len(picked) >= top:
            break
    return [{"t": p, "z": round(float(z[p]), 2)} for p in sorted(picked)]


# ---------------------------------------------------------------- 4. reperage des moments forts
PROMPT = """Tu es monteur de clips viraux TikTok / Reels.
Voici la transcription horodatee d'un extrait du live de {author} ("{title}"), de {a} a {b}.
Pics de volume audio (rires, cris, reactions), z-score entre parentheses : {peaks}

Trouve jusqu'a {k} moments forts qui marchent SEULS, sans contexte : punchline, fou rire,
reaction forte, histoire courte avec une chute, clash, info surprenante.
Chaque clip dure entre {mn} et {mx} secondes, commence juste avant l'action (pas de blanc)
et se termine juste apres la chute. Sois exigeant : mieux vaut 1 excellent clip que 5 moyens.

Reponds UNIQUEMENT avec un tableau JSON :
[{{"start":"HH:MM:SS","end":"HH:MM:SS","score":1-10,"title":"titre court",
  "hook":"accroche affichee 3 s en haut de la video, 8 mots max",
  "caption":"legende de 1-2 phrases","hashtags":["#...","#..."]}}]
Si rien n'est assez bon, reponds [].
"""

def ask_claude(text):
    exe = shutil.which("claude")
    if not exe:
        return None
    r = subprocess.run([exe, "-p", "Analyse le contenu fourni sur l'entree standard et reponds "
                        "uniquement avec le tableau JSON demande.", "--output-format", "json"],
                       input=text, capture_output=True, text=True, encoding="utf-8", timeout=900)
    if r.returncode:
        print("  claude -p a echoue :", r.stderr[:300])
        return None
    try:
        res = json.loads(r.stdout).get("result", "")
    except json.JSONDecodeError:
        res = r.stdout
    m = re.search(r"\[.*\]", res, re.S)
    try:
        return json.loads(m.group(0)) if m else []
    except json.JSONDecodeError:
        return []

def snap(h, segs, total):
    st, en = to_sec(h["start"]), to_sec(h["end"])
    for s in segs:
        if s["start"] <= st < s["end"]:
            st = s["start"]; break
    for s in segs:
        if s["start"] < en <= s["end"]:
            en = s["end"]; break
    st, en = max(0.0, st - 0.3), min(total, en + 0.4)
    en = min(en, st + C["max_len"])
    if en - st < C["min_len"]:
        en = min(total, st + C["min_len"])
    return {**h, "start": round(st, 2), "end": round(en, 2)}

def find_highlights(segs, peaks, src, n, total):
    window, cands = 1500, []
    use_claude = shutil.which("claude") is not None
    if not use_claude:
        print("  'claude' introuvable : reperage uniquement sur les pics de volume.")
    t = 0.0
    while use_claude and t < total:
        a, b = t, t + window
        lines = [f"[{hms(s['start'])}] {s['text']}" for s in segs if a <= s["start"] < b]
        t = b
        if len(lines) < 10:
            continue
        pk = ", ".join(f"{hms(p['t'])} ({p['z']})" for p in peaks if a <= p["t"] < b and p["z"] > 1.2) or "aucun"
        print(f"  Analyse {hms(a)} -> {hms(min(b, total))}...")
        prompt = PROMPT.format(author=src["author"], title=src["title"], a=hms(a), b=hms(min(b, total)),
                               peaks=pk, k=max(2, n), mn=C["min_len"], mx=C["max_len"])
        res = ask_claude(prompt + "\nTRANSCRIPTION :\n" + "\n".join(lines))
        for h in res or []:
            try:
                cands.append(snap(h, segs, total))
            except (KeyError, ValueError):
                pass
    if not cands:  # secours : pics de volume
        for p in sorted(peaks, key=lambda p: -p["z"])[:n * 2]:
            cands.append(snap({"start": max(0, p["t"] - 20), "end": p["t"] + 12, "score": p["z"],
                               "title": f"Moment {hms(p['t'])}", "hook": "", "caption": "",
                               "hashtags": []}, segs, total))
    out = []
    for c in sorted(cands, key=lambda x: -float(x.get("score", 0))):
        if all(c["end"] <= o["start"] or c["start"] >= o["end"] for o in out):
            out.append(c)
        if len(out) >= n:
            break
    return sorted(out, key=lambda x: x["start"])


# ---------------------------------------------------------------- 5. montage (9:16 + sous-titres + hook)
def ass_time(t):
    cs = int(round(max(0, t) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"

def esc(t):
    return t.replace("\\", "").replace("{", "(").replace("}", ")").upper()

def write_ass(path, words, t0, dur, hook, layout):
    y = 1480 if layout == "blur" else 1380
    f = C["font"]
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
        if cur and (len(cur) >= C["words_per_line"] or w["s"] - cur[-1]["e"] > 0.6):
            groups.append(cur); cur = []
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

def render(d, src, segs, h, idx, layout):
    cid = f"{src['id']}_{idx:02d}"
    cdir = OUT / cid
    cdir.mkdir(parents=True, exist_ok=True)
    st, dur = h["start"], h["end"] - h["start"]
    words = [w for s in segs for w in s["words"] if w["s"] >= st - 0.05 and w["e"] <= h["end"] + 0.05]
    write_ass(cdir / "subs.ass", words, st, dur, h.get("hook", ""), layout)
    if layout == "crop":
        graph = "[0:v]crop=ih*9/16:ih,scale=1080:1920,setsar=1,ass=subs.ass[v]"
    else:  # blur : video entiere au centre, fond flou
        graph = ("[0:v]split=2[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,"
                 "crop=1080:1920,boxblur=25:2,eq=brightness=-0.08[bg];[b]scale=1080:-2[fg];"
                 "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,ass=subs.ass[v]")
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{st:.2f}", "-i", str((d / "video.mp4").resolve()),
         "-t", f"{dur:.2f}", "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
         "-c:v", C["encoder"], "-preset", "veryfast" if C["encoder"] == "libx264" else "p4",
         "-crf" if C["encoder"] == "libx264" else "-cq", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "clip.mp4"], cwd=cdir)
    return {"id": cid, "file": str(cdir / "clip.mp4"), "source": src,
            "start": hms(st), "end": hms(h["end"]), "duration": round(dur, 1),
            "score": h.get("score"), "title": h.get("title", ""), "hook": h.get("hook", ""),
            "caption": h.get("caption", ""), "hashtags": h.get("hashtags", []),
            "status": "pending", "posted": {}}


# ---------------------------------------------------------------- 6. publication (Chrome ouvert)
def build_caption(c):
    s = c["source"]
    tags = " ".join(dict.fromkeys((c.get("hashtags") or []) + C["default_hashtags"]))
    credit = f"🎥 Source : {s['author']}" + (f" — {s['url']}" if s.get("url") else "")
    return f"{c.get('caption') or c.get('title', '')}\n\n{credit}\n\n{tags}".strip()[:2150]

def click_text(page, pattern, timeout=4000):
    try:
        page.get_by_role("button", name=re.compile(pattern, re.I)).first.click(timeout=timeout)
        return True
    except Exception:
        return False

def post_tiktok(page, video, caption, publish):
    from playwright.sync_api import expect
    page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="domcontentloaded")
    page.locator('input[type="file"]').first.set_input_files(video, timeout=60000)
    editor = page.locator('div[contenteditable="true"]').first
    editor.wait_for(timeout=120000)
    editor.click()
    page.keyboard.press("Control+A"); page.keyboard.press("Delete")
    page.keyboard.insert_text(caption)
    page.keyboard.press("Escape")  # ferme le menu de suggestions de hashtags
    btn = page.locator('button[data-e2e="post_video_button"]')
    expect(btn).to_be_enabled(timeout=600000)  # attend la fin de l'upload
    if publish:
        btn.click()
        page.wait_for_timeout(10000)

def post_instagram(page, video, caption, publish):
    page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
    page.locator('svg[aria-label="Nouvelle publication"], svg[aria-label="New post"], '
                 'svg[aria-label="Créer"], svg[aria-label="Create"]').first.click(timeout=20000)
    try:
        page.get_by_text(re.compile(r"^(Publication|Post)$")).first.click(timeout=3000)
    except Exception:
        pass
    page.locator('input[type="file"]').first.set_input_files(video, timeout=30000)
    click_text(page, r"^OK$", 6000)  # "Les videos sont desormais partagees en reels"
    try:  # recadrage -> format original (garde le 9:16)
        page.locator('svg[aria-label="Sélectionner le recadrage"], svg[aria-label="Select crop"]').first.click(timeout=6000)
        page.get_by_text(re.compile(r"^(Original|D’origine|D'origine)$")).first.click(timeout=4000)
    except Exception:
        pass
    for _ in range(2):
        if not click_text(page, r"^(Suivant|Next)$", 20000):
            raise RuntimeError("Bouton Suivant introuvable")
        page.wait_for_timeout(1500)
    box = page.locator('div[aria-label^="Écrivez une légende"], div[aria-label^="Write a caption"]').first
    box.click(timeout=20000)
    page.keyboard.insert_text(caption)
    if publish:
        if not click_text(page, r"^(Partager|Share)$", 20000):
            raise RuntimeError("Bouton Partager introuvable")
        page.get_by_text(re.compile(r"(a été partagé|has been shared)", re.I)).first.wait_for(timeout=600000)

def cmd_post(a):
    from playwright.sync_api import sync_playwright
    m = load_manifest()
    todo = [c for c in m if c["status"] == "approved"][:a.limit]
    if not todo:
        print("Aucun clip approuve. Lance `python clipper.py list` puis `approve`.")
        return
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(C["cdp_url"])
        except Exception:
            sys.exit("Chrome injoignable. Lance Chrome avec --remote-debugging-port=9222 (voir README).")
        ctx = browser.contexts[0]
        for c in todo:
            for plat in a.platform:
                if c["posted"].get(plat) in ("published", "prepared"):
                    continue
                print(f"[{plat}] {c['id']} - {c['title']}")
                page = ctx.new_page()
                try:
                    fn = post_tiktok if plat == "tiktok" else post_instagram
                    fn(page, str(Path(c["file"]).resolve()), build_caption(c), a.publish)
                    c["posted"][plat] = "published" if a.publish else "prepared"
                    print("  ->", "publie" if a.publish else "pret : verifie l'onglet et clique sur Publier")
                    if a.publish:
                        page.close()
                except Exception as e:
                    shot = Path(c["file"]).parent / f"erreur_{plat}.png"
                    try:
                        page.screenshot(path=str(shot))
                    except Exception:
                        pass
                    print(f"  ERREUR : {e}\n  capture : {shot}")
                save_manifest(m)
                if a.publish:
                    time.sleep(random.uniform(*C["delay_between_posts_sec"]))
            if all(c["posted"].get(pl) == "published" for pl in a.platform):
                c["status"] = "posted"
            save_manifest(m)


# ---------------------------------------------------------------- CLI
def cmd_clip(a):
    d, src = download(a.url, a.section)
    segs = transcribe(d)
    total = duration(d / "video.mp4")
    print("Reperage des moments forts...")
    hl = find_highlights(segs, loudness_peaks(d), src, a.max_clips, total)
    m = load_manifest()
    for i, h in enumerate(hl, 1):
        print(f"Montage {i}/{len(hl)} : {hms(h['start'])} -> {hms(h['end'])}  {h.get('title', '')}")
        clip = render(d, src, segs, h, i, a.layout)
        m = [x for x in m if x["id"] != clip["id"]] + [clip]
        save_manifest(m)
    print(f"\n{len(hl)} clip(s) dans {OUT}. Verifie-les puis : python clipper.py approve <id> | --all")

def cmd_list(a):
    for c in load_manifest():
        posted = ",".join(f"{k}:{v}" for k, v in c["posted"].items()) or "-"
        print(f"{c['id']:<28} {c['status']:<9} score={c.get('score')}  {c['duration']}s  "
              f"{c['source']['author']}  | {c['title']}  [{posted}]")

def cmd_status(a, status):
    m = load_manifest()
    for c in m:
        if (getattr(a, "all", False) and c["status"] == "pending") or c["id"] in a.ids:
            c["status"] = status
            print(f"{c['id']} -> {status}")
    save_manifest(m)

def main():
    ap = argparse.ArgumentParser(description="Clipping de lives + publication")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("clip"); p.add_argument("url")
    p.add_argument("--max-clips", type=int, default=C["max_clips"])
    p.add_argument("--layout", choices=["blur", "crop"], default=C["layout"])
    p.add_argument("--section", help="ex: 01:00:00-02:30:00 (ne telecharge que ce passage)")
    sp.add_parser("list")
    p = sp.add_parser("approve"); p.add_argument("ids", nargs="*"); p.add_argument("--all", action="store_true")
    p = sp.add_parser("reject"); p.add_argument("ids", nargs="+")
    p = sp.add_parser("post")
    p.add_argument("--platform", nargs="+", choices=["tiktok", "instagram"], default=["tiktok", "instagram"])
    p.add_argument("--publish", action="store_true", help="clique vraiment sur Publier")
    p.add_argument("--limit", type=int, default=3)
    a = ap.parse_args()
    {"clip": cmd_clip, "list": cmd_list, "post": cmd_post,
     "approve": lambda a: cmd_status(a, "approved"),
     "reject": lambda a: cmd_status(a, "rejected")}[a.cmd](a)

if __name__ == "__main__":
    main()
