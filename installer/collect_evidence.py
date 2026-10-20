"""Gather the build's evidence into docs/evidence/p13_installers/ after a build:

    python installer/collect_evidence.py BUILD_DIR [SHOTS_DIR]

Copies the build logs (pip's long command lines stripped), the Wine run log's summary,
the checksum files, and the installer page photographs if a SHOTS_DIR is given.
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidence" / "p13_installers"


def trimmed(log: Path) -> str:
    lines = []
    for line in log.read_text(errors="replace").splitlines():
        if re.search(r"\$ .*pip (download|install)", line):
            line = line.split("pip")[0] + "pip " + line.split("pip")[1].split(" -d ")[0][:60] + " ... (pins in installer/requirements-bundle.txt)"
        if line.startswith("WARNING: Running pip as the 'root'"):
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"


def main(build: Path, shots: Path | None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("build_windows.log", "build_macos.log"):
        src = build / name
        if src.exists():
            (OUT / name).write_text(trimmed(src))
    run = build / "winetest" / "run.log"
    if run.exists():
        text = run.read_text(errors="replace")
        keep = [l for l in text.splitlines() if re.search(r"passed|failed|FAILED|imports ok|written to|wine_run done|^\[|%\]", l)]
        (OUT / "wine_run_summary.txt").write_text("\n".join(keep) + "\n")
    for f in (ROOT / "installer" / "dist").glob("*.sha256"):
        shutil.copy2(f, OUT / f.name)
    if shots is not None:
        for f in sorted(shots.glob("*_crop.png")):
            shutil.copy2(f, OUT / f.name.replace("_crop", ""))
    print("evidence in", OUT, sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
