"""The installer build script: what it ships, what it refuses to ship, and that its pins agree with the
repository's. The build itself needs mingw, NSIS and network and runs outside the suite."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INST = ROOT / "installer"
if not (INST / "build.py").exists():
    pytest.skip("the installer sources are not part of this installation", allow_module_level=True)

def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("cyclara_installer_build", INST / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_shipped_path_exists_and_the_private_scan_runs(tmp_path):
    b = _load()
    for rel in b.APP_FILES:
        assert (ROOT / rel).exists(), rel
    b.copy_app(tmp_path / "app")
    assert (tmp_path / "app" / "electrochem" / "readers" / "builtin.py").exists()
    assert (tmp_path / "app" / "data" / "demo" / "cyclara_demo_synthetic.mpt").exists()
    assert (tmp_path / "app" / "tests" / "test_cycling.py").exists()        # Help > Check this installation
    assert not list((tmp_path / "app").rglob("__pycache__"))
    private = tmp_path / "app" / "data" / "demo" / "note.txt"
    private.write_text("cell " + "AW" + "01 weighed " + "5." + "733 mg")   # spelt apart: the scan reads this file too
    import shutil
    (tmp_path / "src").mkdir()
    b2 = _load()
    b2.ROOT = tmp_path / "src"
    for rel in ("electrochem", "data/demo"):
        shutil.copytree(ROOT / rel, tmp_path / "src" / rel, ignore=shutil.ignore_patterns("__pycache__"))
    b2.APP_FILES = ["electrochem", "data/demo"]
    shutil.copy2(private, tmp_path / "src" / "data" / "demo" / "note.txt")
    with pytest.raises(SystemExit, match="private data would ship"):
        b2.copy_app(tmp_path / "app2")


def test_the_bundle_pins_agree_with_the_repository_pins():
    pins = {}
    for line in (INST / "requirements-bundle.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            name, ver = line.split("==")
            pins[name.lower().replace("_", "-")] = ver
    for req in ("requirements.txt", "requirements-gui.txt"):
        for line in (ROOT / req).read_text().splitlines():
            line = line.split("#")[0].strip()
            if "==" in line:
                name, ver = line.split("==")
                assert pins.get(name.lower().replace("_", "-")) == ver, f"{req}: {line} differs from the bundle"
    assert pins["pyside6-essentials"] == pins["shiboken6"]
    rt = json.loads((INST / "runtime.json").read_text())
    assert set(rt["files"]) == {"windows-x86_64", "macos-arm64", "macos-x86_64", "linux-x86_64"}
    for entry in rt["files"].values():
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) and rt["release"] in entry["name"]


def test_the_nsis_script_and_the_launcher_agree_on_the_layout():
    nsi = (INST / "windows" / "cyclara.nsi").read_text()
    for needed in ('File "${STAGE}\\Cyclara.exe"', 'File /r "${STAGE}\\python"', 'File /r "${STAGE}\\app"',
                   "RequestExecutionLevel user", "WriteUninstaller", "MUI_FINISHPAGE_RUN", "OpenWithProgids"):
        assert needed in nsi, needed
    assert "HKLM" not in nsi                                       # per user: never the machine hive
    launcher = (INST / "windows" / "launcher.c").read_text()
    assert 'L"%ls\\\\python"' in launcher and '"Py_SetPythonHome"' in launcher and '"Py_Main"' in launcher
    assert "argv[1][1] != L'-'" in launcher                        # single-dash: Python's; double-dash: Cyclara's
    assert 'L"electrochem.studio"' in launcher and 'L"-I"' in launcher
    mac = (INST / "macos" / "Cyclara.sh").read_text()
    assert "MacOS/cyclara-python" in mac and "-m electrochem.studio" in mac and "-I" in mac


def test_a_universal_binary_is_thinned_to_one_slice(tmp_path):
    """A fat Mach-O file is a header of big-endian (cputype, subtype, offset, size, align) records followed
    by the slices; the right slice must come out byte for byte, and a missing one must stop the build."""
    import struct
    b = _load()
    arm = b"\xcf\xfa\xed\xfe" + struct.pack("<I", 0x0100000C) + b"A" * 60      # 64-bit magic, little-endian cputype
    x86 = b"\xcf\xfa\xed\xfe" + struct.pack("<I", 0x01000007) + b"X" * 100
    header = struct.pack(">II", 0xCAFEBABE, 2)
    off_arm, off_x86 = 4096, 8192
    header += struct.pack(">IIIII", 0x0100000C, 0, off_arm, len(arm), 12)
    header += struct.pack(">IIIII", 0x01000007, 3, off_x86, len(x86), 12)
    blob = header + b"\0" * (off_arm - len(header)) + arm + b"\0" * (off_x86 - off_arm - len(arm)) + x86
    f = tmp_path / "QtCore"
    f.write_bytes(blob); f.chmod(0o755)
    assert b.thin_fat(f, "x86_64") is True
    assert f.read_bytes() == x86 and f.stat().st_mode & 0o111
    assert b.thin_fat(f, "x86_64") is False                     # already thin: left alone
    f.write_bytes(blob)
    assert b.thin_fat(f, "arm64") is True and f.read_bytes() == arm
    only = tmp_path / "only_x86"
    only.write_bytes(struct.pack(">II", 0xCAFEBABE, 1) + struct.pack(">IIIII", 0x01000007, 3, 4096, len(x86), 12)
                     + b"\0" * (4096 - 28) + x86)
    with pytest.raises(SystemExit, match="no arm64 slice"):
        b.thin_fat(only, "arm64")


def test_the_macos_check_sees_a_missing_framework(tmp_path):
    """The load-command check must fail when a referenced framework binary is not in the bundle (the
    pruning once removed every Qt framework and an earlier check let it through)."""
    import struct
    b = _load()
    app = tmp_path / "Cyclara.app"
    (app / "Contents" / "lib").mkdir(parents=True)

    def macho(loads):
        cmds = b""
        for name in loads:
            s = name.encode() + b"\0"
            s += b"\0" * ((8 - len(s) % 8) % 8)
            cmds += struct.pack("<IIIIII", 0xC, 24 + len(s), 24, 0, 0, 0) + s      # LC_LOAD_DYLIB
        return struct.pack("<IIIIIII", 0xFEEDFACF, 0x0100000C, 0, 6, len(loads), len(cmds), 0) + b"\0" * 4 + cmds

    so = app / "Contents" / "lib" / "QtCore.abi3.so"
    so.write_bytes(macho(["@rpath/QtCore.framework/Versions/A/QtCore", "/usr/lib/libSystem.B.dylib"]))
    assert b.macho_loads(so) == ["@rpath/QtCore.framework/Versions/A/QtCore", "/usr/lib/libSystem.B.dylib"]
    with pytest.raises(SystemExit, match="QtCore.framework"):
        b.check_macos_tree(app)
    fw = app / "Contents" / "lib" / "QtCore.framework" / "Versions" / "A"
    fw.mkdir(parents=True)
    (fw / "QtCore").write_bytes(macho(["/usr/lib/libSystem.B.dylib"]))
    b.check_macos_tree(app)                                     # now every load resolves


@pytest.mark.skipif(not __import__("shutil").which("x86_64-w64-mingw32-gcc"), reason="needs the mingw-w64 cross-compiler")
def test_the_launcher_builds_to_the_same_bytes_twice(tmp_path):
    """Two builds of the same sources give the same Cyclara.exe (no link time in the PE header)."""
    import hashlib
    import struct
    import time
    b = _load()
    first = b.build_launcher(tmp_path / "one", "0.8.0").read_bytes()
    time.sleep(1.1)                                       # a time stamp, if one were written, would differ
    second = b.build_launcher(tmp_path / "two", "0.8.0").read_bytes()
    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
    pe = struct.unpack_from("<I", first, 0x3C)[0]
    assert first[pe:pe + 4] == b"PE\0\0" and struct.unpack_from("<I", first, pe + 8)[0] == 0
