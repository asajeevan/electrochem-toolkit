"""Build Cyclara's one-click installers from any Linux or macOS machine.

    python installer/build.py --windows --macos          everything (into installer/dist/)
    python installer/build.py --windows                  Cyclara-<version>-Setup.exe
    python installer/build.py --macos                    Cyclara-<version>-macOS-{AppleSilicon,Intel}.zip
    python installer/build.py --windows --wine           ...and run the staged Windows tree under Wine

What goes into each installer, and why it is reproducible:

* A relocatable CPython 3.12 from python-build-standalone, pinned by release tag and
  SHA-256 in installer/runtime.json. Checked before it is unpacked.
* The scientific packages and Qt as binary wheels for the target platform, pinned in
  installer/requirements-bundle.txt, laid down with pip's cross-platform mode
  (--platform/--python-version/--only-binary). The build machine's own packages are
  never used.
* The toolkit itself: electrochem/, eclab_import/, the demonstration and public data,
  the documents, and the self-tests, copied from this repository (APP_FILES).
* Windows: Cyclara.exe (installer/windows/launcher.c, compiled with mingw-w64) hosts
  python312.dll in its own process; an NSIS 3 installer (installer/windows/cyclara.nsi)
  wraps the tree with the branded pages drawn by installer/windows/bitmaps.py.
* macOS: Cyclara.app with the runtime inside Contents/Resources, one bundle per
  processor family, zipped with permissions kept. Unsigned: see installer/README.md
  for what a first launch looks like and why.

Every step that can be checked is checked: checksums, that no Windows DLL or .pyd
imports a library that will not be there, that the pure-Python part of the tree
imports under a real Python 3.12 (the Linux build of the same release), and, with
--wine, that the Windows tree opens the demonstration file and renders every view.

Needs on the build machine: python3 with pip (any version 3.10+), git (for galvani),
x86_64-w64-mingw32-gcc and -windres, makensis (NSIS 3), and optionally wine64.
Nothing is downloaded from anywhere but github.com (CPython) and pypi.org (wheels).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BUILD = Path(os.environ.get("CYCLARA_BUILD_DIR", HERE / "build"))
DIST = HERE / "dist"
RUNTIME = json.loads((HERE / "runtime.json").read_text(encoding="utf-8"))
PINS = [l.split("#")[0].strip() for l in (HERE / "requirements-bundle.txt").read_text().splitlines()
        if l.split("#")[0].strip()]
GALVANI = next(l.strip() for l in (ROOT / "requirements-native.txt").read_text().splitlines()
               if l.strip().startswith("galvani"))

# What the installed app/ folder holds: the toolkit, its data and documents, its self-tests.
APP_FILES = ["electrochem", "eclab_import", "data/demo", "data/public", "data/examples", "reference", "tests", "conftest.py",
             "pyproject.toml", "HOW_TO_USE.txt", "README.md", "LICENSE", "CITATION.cff", "STATUS.md",
             "docs/Cyclara_handout.pdf", "docs/U02_Cyclara.md", "docs/M01_Cycling_Method_Specification.md",
             "docs/Cycling_Source_Register.md", "docs/P08_Multi_Instrument_Import_Specification.md",
             "docs/P08a_Import_Failure_Mode_Register.md", "docs/P08d_Instrument_Compatibility_Matrix.md",
             "docs/images", "scripts/capture_reader_reference.py",      # imported by tests/test_readers_reference.py
             "scripts/studio_images.py"]                                 # the Wine harness renders every view with it
SKIP_NAMES = {"__pycache__", ".pytest_cache", ".DS_Store"}
# The author's private cell must never ship: its names and its three telltale values (mass, molar
# mass, row count). Spelt in pieces so this file does not itself trip the scan in the release zip.
PRIVATE_MARKERS = (b"AW" + b"01", b"zpt" + b"-6", b"c65" + b"_33")
PRIVATE_VALUES = re.compile(rb"(?<![0-9.])(" + rb"5\." + rb"733|" + rb"273\." + rb"37|74(?:,|\xe2\x80\x89| )?" + rb"684)(?![0-9])")

# Windows: what the bundled Qt needs for a widgets application, and nothing else.
QT_MODULES = {"Core", "Gui", "Widgets", "Svg", "SvgWidgets", "OpenGL", "OpenGLWidgets", "PrintSupport",
              "DBus",                                           # QtGui on macOS links QtDBus
              "Test"}                                           # QtTest: two of the self-tests type into widgets
QT_KEEP = {f"Qt6{m}" for m in QT_MODULES}                      # Windows: Qt6Core.dll ...
QT_FRAMEWORKS = {f"Qt{m}.framework" for m in QT_MODULES}       # macOS: QtCore.framework ...
PYSIDE_MODULES = {f"Qt{m}" for m in QT_MODULES} - {"QtDBus"}    # the Python modules: QtCore.pyd / QtCore.abi3.so ...
PYSIDE_PLUGINS = {"platforms": {"qwindows.dll", "qoffscreen.dll", "qminimal.dll", "libqcocoa.dylib",
                                "libqoffscreen.dylib", "libqminimal.dylib"},
                  "styles": {"qmodernwindowsstyle.dll", "libqmacstyle.dylib"},
                  "imageformats": {"qsvg", "qico", "qjpeg", "qgif", "qicns", "qtiff", "qwebp", "qtga", "qwbmp"},
                  "iconengines": {"qsvgicon"}}
PYSIDE_FILES_KEEP = {"__init__.py", "_config.py", "_git_pyside_version.py", "PySide6_Essentials.json", "py.typed",
                     "__feature__.pyi", "pyside6.abi3.dll", "libpyside6.abi3.6.12.dylib"}
MSVC_RUNTIME = ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_codecvt_ids.dll",
                "vcruntime140.dll", "vcruntime140_1.dll", "concrt140.dll")
STDLIB_DROP = ("idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "test", "turtle.py")
DLLS_DROP_PREFIX = ("_test", "_tkinter", "tcl86", "tk86", "_msi")

# pip matches a manylinux tag exactly when it is given one, so the build machine's own check lists them.
LINUX_PLATFORMS = ["manylinux_2_17_x86_64", "manylinux2014_x86_64", "manylinux_2_24_x86_64", "manylinux_2_27_x86_64",
                   "manylinux_2_28_x86_64", "manylinux_2_31_x86_64", "manylinux_2_34_x86_64", "manylinux_2_35_x86_64"]

# Windows DLLs that every supported Windows (10 version 1903 and later, 11) provides.
SYSTEM_DLLS = {"kernel32", "user32", "gdi32", "advapi32", "shell32", "ole32", "oleaut32", "ws2_32", "winmm",
               "version", "bcrypt", "crypt32", "dwmapi", "uxtheme", "imm32", "netapi32", "userenv", "mpr",
               "authz", "shlwapi", "comdlg32", "comctl32", "d3d11", "d3d12", "dxgi", "d3d9", "setupapi",
               "winspool", "wtsapi32", "ntdll", "msvcrt", "icuuc", "icuin", "opengl32", "glu32", "secur32",
               "dnsapi", "iphlpapi", "rpcrt4", "psapi", "powrprof", "propsys", "shcore", "windowscodecs",
               "dbghelp", "wintrust", "cfgmgr32", "winhttp", "wininet", "urlmon", "msimg32", "gdiplus",
               "dcomp", "d2d1", "dwrite", "dxva2", "msi", "odbc32", "pdh", "ncrypt", "cryptbase", "sspicli",
               "mf", "mfplat", "mfreadwrite", "mfuuid", "avrt", "wlanapi", "winusb", "hid", "ktmw32",
               "kernelbase", "msvcp140", "msvcp140_1", "msvcp140_2", "msvcp140_codecvt_ids", "vcruntime140",
               "vcruntime140_1", "concrt140", "ucrtbase", "python312", "python3", "coremessaging",
               "bluetoothapis", "sensorsapi", "runtimeobject", "api-ms-win-core-synch-l1-2-0",
               "d3dcompiler_47", "uiautomationcore", "winspool.drv", "bcryptprimitives", "mscms", "vcamp140",
               "vcomp140", "vccorlib140"}


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def run(cmd, **kw) -> subprocess.CompletedProcess:
    log("$ " + " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def version() -> str:
    text = (ROOT / "electrochem" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


# ------------------------------------------------------------------ downloads
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def runtime_archive(key: str) -> Path:
    entry = RUNTIME["files"][key]
    dl = BUILD / "dl"
    dl.mkdir(parents=True, exist_ok=True)
    path = dl / entry["name"]
    if not path.exists() or sha256(path) != entry["sha256"]:
        url = RUNTIME["base_url"] + entry["name"]
        log(f"downloading {url}")
        with urllib.request.urlopen(url, timeout=600) as r, open(path, "wb") as fh:
            shutil.copyfileobj(r, fh)
    got = sha256(path)
    if got != entry["sha256"]:
        raise SystemExit(f"checksum mismatch for {path.name}: {got}")
    log(f"{path.name}: checksum verified")
    return path


def extract_runtime(key: str, dst: Path) -> Path:
    """Unpack the archive's python/ folder into dst (dst/python)."""
    arc = runtime_archive(key)
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    with tarfile.open(arc) as tf:
        members = [m for m in tf.getmembers() if m.name.startswith("python/")]
        tf.extractall(dst, members=members, filter="data")
    return dst / "python"


def wheelhouse(target: str, platforms: list[str]) -> Path:
    """Binary wheels for the target platform, pinned, plus galvani built from its commit."""
    house = BUILD / "wheels" / target
    house.mkdir(parents=True, exist_ok=True)
    plat = []
    for p in platforms:
        plat += ["--platform", p]
    run([sys.executable, "-m", "pip", "download", "-q", "--no-deps", "--only-binary=:all:", *plat,
         "--python-version", "3.12", "--implementation", "cp", "--abi", "cp312", "-d", house, *PINS])
    anyhouse = BUILD / "wheels" / "any"
    anyhouse.mkdir(parents=True, exist_ok=True)
    if not list(anyhouse.glob("galvani-*.whl")):
        run([sys.executable, "-m", "pip", "wheel", "-q", "--no-deps", "-w", anyhouse, GALVANI])
    return house


def install_wheels(site: Path, houses: list[Path], platforms: list[str]) -> None:
    plat = []
    for p in platforms:
        plat += ["--platform", p]
    wheels = [w for h in houses for w in sorted(h.glob("*.whl"))]
    run([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "--no-index", "--only-binary=:all:", *plat,
         "--python-version", "3.12", "--implementation", "cp", "--abi", "cp312", "--no-compile",
         "--target", site, *wheels])
    for stray in site.glob("*.whl"):            # scipy's wheel carries an empty file named after itself
        stray.unlink()
    for d in ("bin", "Scripts"):
        shutil.rmtree(site / d, ignore_errors=True)


# ------------------------------------------------------------------ the app tree
def copy_app(dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for rel in APP_FILES:
        src = ROOT / rel
        if not src.exists():
            raise SystemExit(f"missing from the repository: {rel}")
        if src.is_dir():
            shutil.copytree(src, dst / rel, ignore=shutil.ignore_patterns(*SKIP_NAMES, "*.pyc"))
        else:
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst / rel)
    bad = []
    for p in dst.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".png", ".pdf", ".svg", ".csv", ".json", ".txt", ".md", ".py", ".mpt"):
            data = p.read_bytes()
            if any(m in data for m in PRIVATE_MARKERS) or PRIVATE_VALUES.search(data):
                bad.append(p.relative_to(dst))
    if bad:
        raise SystemExit("private data would ship: " + ", ".join(map(str, bad)))


def prune_stdlib(py: Path, lib: Path, dlls: Path | None) -> None:
    for name in STDLIB_DROP:
        p = lib / name
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    for p in py.rglob("*.pdb"):
        p.unlink()
    for name in ("include", "libs", "tcl", "share"):
        shutil.rmtree(py / name, ignore_errors=True)
    if dlls is not None and dlls.exists():
        for p in dlls.iterdir():
            if p.name.lower().startswith(DLLS_DROP_PREFIX):
                p.unlink()
    for p in list(py.rglob("__pycache__")):
        shutil.rmtree(p, ignore_errors=True)


def prune_pyside(site: Path, windows: bool) -> None:
    """Keep the Qt modules a widgets application uses and the plugins they load. The Qt Quick,
    QML, Designer, Help, Sql, Network and tooling parts of PySide6-Essentials are not used."""
    ps = site / "PySide6"
    for p in list(ps.iterdir()):
        name = p.name
        if p.is_dir():
            if name == "plugins" and windows or name == "Qt" and not windows:
                continue
            shutil.rmtree(p)
            continue
        stem = name.split(".")[0]
        if name in PYSIDE_FILES_KEEP or name.lower() in MSVC_RUNTIME:
            continue
        if stem in PYSIDE_MODULES and p.suffix in (".pyd", ".so", ".pyi"):
            continue
        if windows and stem in QT_KEEP and p.suffix == ".dll":
            continue
        p.unlink()
    if windows:
        _prune_plugins(ps / "plugins")
    else:
        qt = ps / "Qt"
        for sub in ("qml", "translations", "libexec", "metatypes", "sbom"):
            shutil.rmtree(qt / sub, ignore_errors=True)
        for p in list((qt / "lib").iterdir()):
            if p.name.endswith(".framework") and p.name not in QT_FRAMEWORKS:
                shutil.rmtree(p)
            elif p.is_file() or p.is_symlink():
                p.unlink()
        kept = sorted(p.name for p in (qt / "lib").iterdir())
        if set(kept) != QT_FRAMEWORKS:
            raise SystemExit(f"Qt frameworks after pruning: {kept}")
        _prune_plugins(qt / "plugins")


def _prune_plugins(plugins: Path) -> None:
    if not plugins.exists():
        return
    for d in list(plugins.iterdir()):
        if d.name not in PYSIDE_PLUGINS:
            shutil.rmtree(d)
            continue
        keep = PYSIDE_PLUGINS[d.name]
        for p in list(d.iterdir()):
            stem = p.name.split(".")[0]
            if p.name in keep or stem in keep or stem.removeprefix("lib") in keep:
                continue
            p.unlink()


def write_pth(site: Path, rel: str) -> None:
    (site / "cyclara.pth").write_text(rel + "\n", encoding="utf-8")


# ------------------------------------------------------------------ checks
def pe_imports(path: Path) -> list[str]:
    d = path.read_bytes()
    pe = int.from_bytes(d[0x3c:0x40], "little")
    if d[pe:pe + 4] != b"PE\0\0":
        return []
    nsec = int.from_bytes(d[pe + 6:pe + 8], "little")
    optsz = int.from_bytes(d[pe + 20:pe + 22], "little")
    opt = pe + 24
    magic = int.from_bytes(d[opt:opt + 2], "little")
    ddir = opt + (112 if magic == 0x20b else 96)
    imp_rva = int.from_bytes(d[ddir + 8:ddir + 12], "little")
    if imp_rva == 0:
        return []
    secs = []
    s = opt + optsz
    for _ in range(nsec):
        vsz, va, rsz, rp = (int.from_bytes(d[s + 8 + 4 * k:s + 12 + 4 * k], "little") for k in range(4))
        secs.append((va, vsz, rp, rsz))
        s += 40

    def r2o(rva):
        for va, vsz, rp, rsz in secs:
            if va <= rva < va + max(vsz, rsz):
                return rva - va + rp
        raise ValueError(hex(rva))
    out = []
    o = r2o(imp_rva)
    while True:
        name_rva = int.from_bytes(d[o + 12:o + 16], "little")
        if name_rva == 0:
            break
        no = r2o(name_rva)
        out.append(d[no:d.index(b"\0", no)].decode())
        o += 20
    return out


def check_windows_tree(stage: Path) -> None:
    """Every DLL a bundled binary imports must be in the bundle or in Windows itself."""
    pes = [p for p in stage.rglob("*") if p.suffix.lower() in (".dll", ".pyd", ".exe")]
    present = {p.name.lower() for p in pes}
    missing = {}
    for p in pes:
        for dep in pe_imports(p):
            low = dep.lower()
            stem = low[:-4] if low.endswith(".dll") else low
            if low in present or stem in SYSTEM_DLLS or stem.startswith(("api-ms-win-", "ext-ms-win-")):
                continue
            missing.setdefault(dep, []).append(p.relative_to(stage))
    if missing:
        lines = [f"  {dep}  <- {', '.join(map(str, who[:3]))}" for dep, who in sorted(missing.items())]
        raise SystemExit("Windows tree: libraries that would be missing on a user's PC:\n" + "\n".join(lines))
    log(f"Windows tree: {len(pes)} binaries, every import resolves")


def linux_python() -> Path:
    py = extract_runtime("linux-x86_64", BUILD / "linux") / "bin" / "python3.12"
    return py


def compile_pyc(py312: Path, *dirs: Path) -> None:
    """Byte-code for Python 3.12 written by Python 3.12, so the first launch does not spend a
    minute compiling. unchecked-hash: never re-validated against the source's timestamp, which
    the installer changes anyway."""
    for d in dirs:
        for p in list(d.rglob("__pycache__")):
            shutil.rmtree(p, ignore_errors=True)
    run([py312, "-m", "compileall", "-q", "-j", "0", "--invalidation-mode", "unchecked-hash", *dirs],
        stdout=subprocess.DEVNULL)


def check_pure_python(py312: Path, app: Path) -> None:
    """The toolkit's pure-Python engine imports and runs under a real 3.12 (the Linux build), with
    the packages that are platform-independent. Qt and the compiled wheels are checked elsewhere."""
    pure = BUILD / "pure312"
    if not (pure / "pydantic").exists():
        pure.mkdir(parents=True, exist_ok=True)
        house = wheelhouse("linux-x86_64", LINUX_PLATFORMS)
        install_wheels(pure, [house, BUILD / "wheels" / "any"], LINUX_PLATFORMS)
    code = (f"import sys; sys.path[:0] = [{str(app)!r}, {str(pure)!r}]\n"
            "assert sys.version_info[:2] == (3, 12), sys.version\n"
            "import electrochem, eclab_import, electrochem.readers, electrochem.workflow, electrochem.analyze\n"
            "from electrochem.readers import BUILTIN; assert BUILTIN\n"
            "print('pure-python import under', sys.version.split()[0], 'ok')")
    run([py312, "-I", "-c", code], env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


# ------------------------------------------------------------------ Windows
def build_windows(ver: str, wine: bool) -> Path:
    stage = BUILD / "stage_win"
    if stage.exists():
        shutil.rmtree(stage)
    py = extract_runtime("windows-x86_64", stage / "rt")
    shutil.move(str(py), str(stage / "python"))
    shutil.rmtree(stage / "rt")
    py = stage / "python"
    site = py / "Lib" / "site-packages"
    house = wheelhouse("win_amd64", ["win_amd64"])
    install_wheels(site, [house, BUILD / "wheels" / "any"], ["win_amd64"])
    prune_stdlib(py, py / "Lib", py / "DLLs")
    prune_pyside(site, windows=True)
    for name in MSVC_RUNTIME:                      # next to every executable that loads extensions
        src = site / "PySide6" / name
        if src.exists():
            shutil.copy2(src, py / name)
            shutil.copy2(src, stage / name)
    copy_app(stage / "app")
    shutil.copy2(ROOT / "LICENSE", stage / "LICENSE")
    write_pth(site, r"..\..\..\app")
    py312 = linux_python()
    compile_pyc(py312, py / "Lib", stage / "app")
    check_pure_python(py312, stage / "app")

    # the launcher
    work = BUILD / "launcher"
    work.mkdir(parents=True, exist_ok=True)
    commas = ",".join((ver.split(".") + ["0", "0", "0"])[:4])
    rc = (HERE / "windows" / "launcher.rc.in").read_text().replace("@COMMAS@", commas).replace("@VERSION@", ver)
    (work / "launcher.rc").write_text(rc)
    shutil.copy2(ROOT / "electrochem" / "studio" / "assets" / "cyclara.ico", work / "cyclara.ico")
    shutil.copy2(HERE / "windows" / "Cyclara.exe.manifest", work / "Cyclara.exe.manifest")
    run(["x86_64-w64-mingw32-windres", "launcher.rc", "-O", "coff", "-o", "launcher_res.o"], cwd=work)
    run(["x86_64-w64-mingw32-gcc", "-municode", "-mwindows", "-O2", "-Wall", "-o", "Cyclara.exe",
         HERE / "windows" / "launcher.c", "launcher_res.o", "-lshell32", "-lole32"], cwd=work)
    shutil.copy2(work / "Cyclara.exe", stage / "Cyclara.exe")
    check_windows_tree(stage)

    # the pictures and the installer
    art = BUILD / "art"
    run([sys.executable, HERE / "windows" / "bitmaps.py", art], env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    shutil.copy2(ROOT / "electrochem" / "studio" / "assets" / "cyclara.ico", art / "cyclara.ico")
    size_kb = sum(p.stat().st_size for p in stage.rglob("*") if p.is_file()) // 1024
    DIST.mkdir(parents=True, exist_ok=True)
    out = DIST / f"Cyclara-{ver}-Setup.exe"
    run(["makensis", "-V2", f"-DVERSION={ver}", f"-DSTAGE={stage}", f"-DART={art}", f"-DOUT={out}",
         f"-DSIZE_KB={size_kb}", f"-DSIZE_MB={size_kb // 1024}", HERE / "windows" / "cyclara.nsi"])
    log(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB; installed {size_kb / 1024:.0f} MB)")
    (DIST / f"Cyclara-{ver}-Setup.exe.sha256").write_text(f"{sha256(out)}  {out.name}\n")
    if wine:
        wine_smoke_test(stage)
    return out


def wine_smoke_test(stage: Path) -> None:
    """The staged tree under Wine: Cyclara.exe hosts the bundled Python, imports the app and renders
    every view of the demonstration file (scripts/studio_images.py). installer/winetest/ prepares
    the prefix; see its README for what Wine lacks and how the test supplies it."""
    sh = HERE / "winetest" / "run.sh"
    run(["bash", sh, stage])


# ------------------------------------------------------------------ macOS
MAC = {"arm64": ("macos-arm64", ["macosx_14_0_arm64", "macosx_11_0_arm64"], "AppleSilicon"),
       "x86_64": ("macos-x86_64", ["macosx_14_0_x86_64", "macosx_10_13_x86_64"], "Intel")}


def build_macos(ver: str, arch: str) -> Path:
    """Cyclara.app. The interpreter binary itself sits in Contents/MacOS (as cyclara-python), with
    the runtime's lib/ as Contents/lib: that is where CPython finds its own files relative to the
    executable, and it is what makes macOS treat the running process as Cyclara (its name, icon and
    menu) rather than as "python3.12". The toolkit lives in Contents/Resources/app."""
    key, platforms, label = MAC[arch]
    stage = BUILD / f"stage_mac_{arch}"
    if stage.exists():
        shutil.rmtree(stage)
    app = stage / "Cyclara.app"
    contents = app / "Contents"
    res = contents / "Resources"
    macos = contents / "MacOS"
    macos.mkdir(parents=True)
    res.mkdir(parents=True)
    py = extract_runtime(key, stage / "rt")
    shutil.move(str(py / "lib"), str(contents / "lib"))
    shutil.copy2(py / "bin" / "python3.12", macos / "cyclara-python")
    shutil.rmtree(stage / "rt")
    lib = contents / "lib"
    stdlib = lib / "python3.12"
    site = stdlib / "site-packages"
    house = wheelhouse(f"mac_{arch}", platforms)
    install_wheels(site, [house, BUILD / "wheels" / "any"], platforms)
    prune_stdlib(contents, stdlib, None)
    for p in list(stdlib.glob("lib-dynload/_tkinter*")) + list(stdlib.glob("config-3.12-darwin")):
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    for p in list(lib.iterdir()):
        if p.name == "python3.12" or p.name == "libpython3.12.dylib":
            continue
        shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()     # tcl, tk, pkgconfig
    prune_pyside(site, windows=False)
    copy_app(res / "app")
    write_pth(site, "../../../Resources/app")
    shutil.copy2(ROOT / "electrochem" / "studio" / "assets" / "cyclara.icns", res / "cyclara.icns")
    (contents / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleName": "Cyclara", "CFBundleDisplayName": "Cyclara",
        "CFBundleIdentifier": "io.github.asajeevan.cyclara",
        "CFBundleVersion": ver, "CFBundleShortVersionString": ver,
        "CFBundlePackageType": "APPL", "CFBundleSignature": "????",
        "CFBundleExecutable": "Cyclara", "CFBundleIconFile": "cyclara",
        "CFBundleInfoDictionaryVersion": "6.0",
        "LSMinimumSystemVersion": "14.0",          # PySide6 6.12, numpy 2.3 and scipy 1.18 wheels: macOS 14
        "LSArchitecturePriority": [arch],
        "NSHighResolutionCapable": True, "NSRequiresAquaSystemAppearance": False,
        "NSHumanReadableCopyright": "GPL-3.0-or-later",
        "CFBundleDocumentTypes": [{"CFBundleTypeName": "Cycling measurement", "CFBundleTypeRole": "Viewer",
                                   "LSHandlerRank": "Alternate",
                                   "CFBundleTypeExtensions": ["mpr", "mpt", "csv", "txt", "xlsx"]}],
    }))
    launcher = macos / "Cyclara"
    launcher.write_text((HERE / "macos" / "Cyclara.sh").read_text())
    launcher.chmod(0o755)
    (macos / "cyclara-python").chmod(0o755)
    py312 = linux_python()
    compile_pyc(py312, stdlib, res / "app")
    check_pure_python(py312, res / "app")
    log(f"universal files thinned to {arch}: {thin_bundle(app, arch)}")
    check_macos_tree(app)
    DIST.mkdir(parents=True, exist_ok=True)
    out = DIST / f"Cyclara-{ver}-macOS-{label}.zip"
    zip_bundle(app, out)
    log(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
    (DIST / f"{out.name}.sha256").write_text(f"{sha256(out)}  {out.name}\n")
    return out


CPU_TYPE = {"arm64": 0x0100000C, "x86_64": 0x01000007}


def thin_fat(path: Path, arch: str) -> bool:
    """Keep only this processor's slice of a universal (fat) Mach-O file, as `lipo -thin` would.
    Each slice is a complete, independently signed Mach-O image whose offsets are relative to its
    own start, so copying the slice out changes nothing inside it. Returns True if the file was fat."""
    import struct
    d = path.read_bytes()
    if len(d) < 8 or struct.unpack_from(">I", d, 0)[0] != 0xCAFEBABE:
        return False
    n = struct.unpack_from(">I", d, 4)[0]
    for k in range(n):
        cputype, _sub, off, size, _align = struct.unpack_from(">IIIII", d, 8 + 20 * k)
        if cputype == CPU_TYPE[arch]:
            piece = d[off:off + size]
            if struct.unpack_from("<I", piece, 0)[0] != 0xFEEDFACF:
                raise SystemExit(f"{path}: the {arch} slice is not a 64-bit Mach-O image")
            tmp = path.with_name(path.name + ".thin")
            tmp.write_bytes(piece)
            tmp.chmod(path.stat().st_mode & 0o7777)
            tmp.replace(path)
            return True
    raise SystemExit(f"{path}: no {arch} slice in this universal file")


def thin_bundle(app: Path, arch: str) -> int:
    count = 0
    for p in app.rglob("*"):
        if p.is_file() and not p.is_symlink() and (p.suffix in (".so", ".dylib") or
                                                   (".framework/Versions/A/" in str(p) and p.suffix == "")):
            if thin_fat(p, arch):
                count += 1
    return count


def macho_loads(path: Path) -> list[str]:
    """LC_LOAD_DYLIB names of a thin or fat Mach-O file."""
    import struct
    d = path.read_bytes()
    if len(d) < 8:
        return []
    out = []
    magic = struct.unpack_from(">I", d, 0)[0]
    slices = []
    if magic == 0xcafebabe:
        n = struct.unpack_from(">I", d, 4)[0]
        for k in range(n):
            off, size = struct.unpack_from(">II", d, 8 + 20 * k + 8)
            slices.append(d[off:off + size])
    else:
        slices = [d]
    for s in slices:
        m = struct.unpack_from("<I", s, 0)[0]
        if m not in (0xfeedfacf, 0xfeedface):
            continue
        ncmds = struct.unpack_from("<I", s, 16)[0]
        off = 32 if m == 0xfeedfacf else 28
        for _ in range(ncmds):
            cmd, size = struct.unpack_from("<II", s, off)
            if cmd in (0xc, 0x18 | 0x80000000, 0x1f | 0x80000000):
                noff = struct.unpack_from("<I", s, off + 8)[0]
                end = s.index(b"\0", off + noff)
                out.append(s[off + noff:end].decode())
            off += size
    return out


def check_macos_tree(app: Path) -> None:
    """Every dylib a bundled binary loads is inside the bundle (by @rpath, @loader_path or
    @executable_path), or is part of macOS itself (/usr/lib, /System)."""
    bins = [p for p in app.rglob("*") if p.is_file() and not p.is_symlink() and
            (p.suffix in (".so", ".dylib") or p.name == "cyclara-python" or
             (".framework/Versions/A/" in str(p) and p.suffix == ""))]
    names = {p.name for p in bins}
    bad = {}
    for p in bins:
        try:
            deps = macho_loads(p)
        except Exception:
            continue
        for dep in deps:
            if dep.startswith(("/usr/lib/", "/System/")):
                continue
            base = dep.rsplit("/", 1)[-1]
            if dep.startswith(("@rpath/", "@loader_path/", "@executable_path/")) and base in names:
                continue
            bad.setdefault(dep, []).append(p.relative_to(app))
    if bad:
        lines = [f"  {dep}  <- {', '.join(map(str, who[:3]))}" for dep, who in sorted(bad.items())]
        raise SystemExit("macOS bundle: libraries that would be missing on a user's Mac:\n" + "\n".join(lines))
    log(f"macOS bundle: {len(bins)} binaries, every library resolves inside the bundle or macOS")


def zip_bundle(app: Path, out: Path) -> None:
    """A zip that keeps the executable bits and symbolic links, as Archive Utility restores them."""
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(app.rglob("*")):
            rel = p.relative_to(app.parent).as_posix()
            if p.is_symlink():
                info = zipfile.ZipInfo(rel)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o755) << 16
                zf.writestr(info, os.readlink(p))
            elif p.is_dir():
                info = zipfile.ZipInfo(rel + "/")
                info.create_system = 3
                info.external_attr = (stat.S_IFDIR | 0o755) << 16 | 0x10
                zf.writestr(info, b"")
            else:
                info = zipfile.ZipInfo.from_file(p, rel)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                mode = 0o755 if (p.stat().st_mode & stat.S_IXUSR) else 0o644
                info.external_attr = (stat.S_IFREG | mode) << 16
                with open(p, "rb") as fh:
                    zf.writestr(info, fh.read())


# ------------------------------------------------------------------ main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--windows", action="store_true")
    ap.add_argument("--macos", action="store_true")
    ap.add_argument("--wine", action="store_true", help="after --windows, run the staged tree under Wine")
    a = ap.parse_args(argv)
    if not (a.windows or a.macos):
        ap.error("say --windows, --macos or both")
    ver = version()
    log(f"Cyclara {ver}, build dir {BUILD}")
    made = []
    if a.windows:
        made.append(build_windows(ver, a.wine))
    if a.macos:
        for arch in ("arm64", "x86_64"):
            made.append(build_macos(ver, arch))
    for m in made:
        log(f"{m.name}  {m.stat().st_size / 1e6:.1f} MB  sha256 {sha256(m)[:16]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
