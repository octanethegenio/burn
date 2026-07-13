"""Build a browser-first Burn executable for the current platform."""

from __future__ import annotations

import hashlib
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
VERSION = "0.1.0-beta.6"


def _run(*command: str, cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _platform_tag() -> tuple[str, str]:
    system = platform.system().lower()
    names = {"darwin": "macOS", "windows": "Windows", "linux": "Linux"}
    if system not in names:
        raise RuntimeError(f"Unsupported packaging platform: {system}")
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "x64"
    return names[system], arch


def main() -> None:
    npm = "npm.cmd" if os.name == "nt" else "npm"
    _run(npm, "ci", cwd=ROOT / "web")
    _run(npm, "run", "check", cwd=ROOT / "web")

    build_dir = ROOT / "build" / "package"
    dist_dir = build_dir / "dist"
    release_dir = ROOT / "release"
    shutil.rmtree(build_dir, ignore_errors=True)
    release_dir.mkdir(exist_ok=True)

    args = [
        str(ROOT / "server" / "launcher.py"),
        "--clean",
        "--noconfirm",
        "--onefile",
        "--name",
        "Burn",
        "--paths",
        str(ROOT),
        "--add-data",
        f"{ROOT / 'web' / 'dist'}{os.pathsep}web/dist",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir / "work"),
        "--specpath",
        str(build_dir),
    ]
    if os.name == "nt":
        args.append("--noconsole")
    PyInstaller.__main__.run(args)

    system, arch = _platform_tag()
    executable = dist_dir / ("Burn.exe" if os.name == "nt" else "Burn")
    if os.name != "nt":
        executable.chmod(0o755)

    payloads = [executable]
    if system == "macOS":
        app_dir = dist_dir / "Burn.app"
        executable_dir = app_dir / "Contents" / "MacOS"
        executable_dir.mkdir(parents=True)
        bundled_executable = executable_dir / "Burn"
        executable.replace(bundled_executable)
        with (app_dir / "Contents" / "Info.plist").open("wb") as plist:
            plistlib.dump(
                {
                    "CFBundleDisplayName": "Burn",
                    "CFBundleExecutable": "Burn",
                    "CFBundleIdentifier": "app.burn.cursor-usage",
                    "CFBundleInfoDictionaryVersion": "6.0",
                    "CFBundleName": "Burn",
                    "CFBundlePackageType": "APPL",
                    "CFBundleShortVersionString": "0.1.0",
                    "CFBundleVersion": "6",
                    "LSMinimumSystemVersion": "13.0",
                    "LSUIElement": True,
                },
                plist,
                sort_keys=False,
            )
        _run("codesign", "--force", "--deep", "--sign", "-", str(app_dir))
        payloads = [app_dir]

    archive = release_dir / f"Burn-{VERSION}-{system}-{arch}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for payload in payloads:
            if payload.is_dir():
                for child in payload.rglob("*"):
                    if child.is_file():
                        output.write(child, child.relative_to(dist_dir))
            else:
                output.write(payload, payload.name)

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="utf-8"
    )
    print(archive)


if __name__ == "__main__":
    main()
