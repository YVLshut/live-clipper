"""3. Pics de volume (rires, cris...) — repris tel quel de clipper.loudness_peaks."""
from __future__ import annotations

from pathlib import Path


def loudness_peaks(d: Path, top: int = 60) -> list[dict]:
    import numpy as np
    a = np.memmap(d / "audio.wav", dtype=np.int16, mode="r", offset=44)
    n = len(a) // 16000
    if n == 0:
        return []
    db = np.empty(n, dtype=np.float32)
    for i in range(0, n, 600):
        blk = np.asarray(a[i * 16000:min(n, i + 600) * 16000], dtype=np.float32) / 32768
        blk = blk.reshape(-1, 16000)
        db[i:i + len(blk)] = 20 * np.log10(np.sqrt((blk ** 2).mean(1)) + 1e-6)
    sm = np.convolve(db, np.ones(5) / 5, mode="same")
    z = (sm - sm.mean()) / (sm.std() + 1e-6)
    picked: list[int] = []
    for i in np.argsort(-z):
        if all(abs(int(i) - p) > 45 for p in picked):
            picked.append(int(i))
        if len(picked) >= top:
            break
    return [{"t": p, "z": round(float(z[p]), 2)} for p in sorted(picked)]
