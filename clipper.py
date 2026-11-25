#!/usr/bin/env python3
"""
clipper.py - interface en ligne de commande de Live Clipper.

Le pipeline vit désormais dans backend/liveclipper (partagé avec l'application de bureau) ;
ce script utilise la même base de données que l'application (%APPDATA%\\LiveClipper).

  python clipper.py clip URL [--max-clips 5] [--layout blur|crop] [--section 00:30:00-01:30:00]
  python clipper.py list
  python clipper.py approve ID [ID ...] | --all
  python clipper.py reject ID [ID ...]

La publication se fait depuis l'application (onglets Comptes et Publication).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from sqlmodel import select  # noqa: E402

from liveclipper import config, db  # noqa: E402
from liveclipper.errors import humanize  # noqa: E402
from liveclipper.events import bus  # noqa: E402
from liveclipper.logging_setup import setup_logging  # noqa: E402
from liveclipper.models import Clip, Source  # noqa: E402
from liveclipper.pipeline.utils import hms  # noqa: E402
from liveclipper.services import job_queue  # noqa: E402


def cmd_clip(a):
    opts = {"max_clips": a.max_clips, "layout": a.layout, "section": a.section}
    job = job_queue.submit("clip", url=a.url, options={k: v for k, v in opts.items() if v})
    last = [None]

    def printer(msg):
        d = msg["data"] if msg["type"] == "job.updated" else None
        if d and d.get("id") == job.id and d.get("message") != last[0]:
            last[0] = d.get("message")
            print(f"  [{d['progress'] * 100:5.1f} %] {d.get('message') or ''}")

    orig = bus.publish

    def publish(t, data=None):
        orig(t, data)
        printer(bus.history[-1])

    bus.publish = publish
    j = job_queue.run_sync(job.id)
    if j.status != "done":
        sys.exit(f"Échec : {j.error}")
    for w in j.warnings or []:
        print("  ⚠", w)
    print(f"\n{j.clips_count} clip(s) dans {config.clips_dir()}. "
          "Vérifie-les puis : python clipper.py approve <id> | --all")


def cmd_list(_a):
    with db.session() as s:
        clips = s.exec(select(Clip).order_by(Clip.created_at)).all()
        srcs = {x.id: x for x in s.exec(select(Source)).all()}
    for c in clips:
        src = srcs.get(c.source_id)
        print(f"{c.id:<34} {c.status:<9} score={c.score}  {hms(c.start)}  {c.duration}s  "
              f"{src.author if src else '?'}  | {c.title}")


def cmd_status(a, status):
    with db.session() as s:
        for c in s.exec(select(Clip)).all():
            if (getattr(a, "all", False) and c.status == "pending") or c.id in a.ids:
                c.status = status
                s.add(c)
                print(f"{c.id} -> {status}")
        s.commit()


def main():
    setup_logging()
    ap = argparse.ArgumentParser(description="Clipping de lives (CLI de Live Clipper)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("clip")
    p.add_argument("url")
    p.add_argument("--max-clips", type=int)
    p.add_argument("--layout", choices=["blur", "crop"])
    p.add_argument("--section", help="ex: 01:00:00-02:30:00 (ne télécharge que ce passage)")
    sp.add_parser("list")
    p = sp.add_parser("approve")
    p.add_argument("ids", nargs="*")
    p.add_argument("--all", action="store_true")
    p = sp.add_parser("reject")
    p.add_argument("ids", nargs="+")
    sp.add_parser("post", help="(déplacé dans l'application)")
    a = ap.parse_args()
    if a.cmd == "post":
        sys.exit("La publication se fait maintenant depuis l'application Live Clipper (onglet Publication).")
    try:
        {"clip": cmd_clip, "list": cmd_list,
         "approve": lambda a: cmd_status(a, "approved"),
         "reject": lambda a: cmd_status(a, "rejected")}[a.cmd](a)
    except Exception as e:  # noqa: BLE001
        sys.exit(humanize(e))


if __name__ == "__main__":
    main()
