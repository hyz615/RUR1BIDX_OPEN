"""Compile configured C helpers and record the exact static-library provenance.

The builder reference must be an immutable container digest. This script never
installs or upgrades packages; it records the toolchain already present in that
builder, copies only the configured helper source and licensing/build material,
and writes a manifest beside those files for distribution and later relinking.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def capture(*command: str) -> str:
    return subprocess.check_output(command, text=True, encoding="utf-8").strip()


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def package_for(path: Path) -> dict:
    package = capture("dpkg-query", "-S", str(path.resolve())).split(": ", 1)[0]
    fields = capture("dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}", package).split("\t")
    return dict(zip(("binary_package", "binary_version", "source_package", "source_version"), fields))


def build(config: Path, source_root: Path, destination: Path, builder: str) -> dict:
    if not re.search(r"@sha256:[0-9a-f]{64}$", builder):
        raise ValueError("The static-helper builder must be identified by an immutable SHA256 digest")
    policy = json.loads(config.read_text(encoding="utf-8"))
    if policy["schema_version"] != 1:
        raise ValueError("Unsupported helper build schema")
    compiler = shutil.which(policy["compiler"])
    if compiler is None:
        raise ValueError("Configured C compiler is not available")
    destination.mkdir(parents=True, exist_ok=True)
    source_root = source_root.resolve()
    libraries = []
    for name in policy["libraries"]:
        path = Path(capture(compiler, "-print-file-name=" + name)).resolve()
        if not path.is_file():
            raise ValueError("Compiler did not resolve the configured static input: " + name)
        libraries.append({"name": name, "path": str(path), "sha256": sha256(path),
                          "provider": package_for(path)})
    results = []
    for helper in policy["helpers"]:
        source = (source_root / helper["source"]).resolve()
        if not source.is_relative_to(source_root):
            raise ValueError("Helper source escapes the configured source root")
        output = Path(helper["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [compiler, *policy["flags"], "-o", str(output), str(source)]
        subprocess.run(command, check=True)
        output.chmod(int(policy["mode"], 8))
        copied = destination / "sources" / helper["source"]
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, copied)
        results.append({"name": helper["name"], "source": "sources/" + helper["source"],
                        "source_sha256": sha256(source), "output": str(output), "sha256": sha256(output),
                        "bytes": output.stat().st_size, "command": command,
                        "elf_program_headers": capture("readelf", "-lW", str(output))})
    shutil.copy2(config, destination / "build-config.json")
    shutil.copy2(__file__, destination / "build-static-helpers.py")
    for name in policy["license_files"]:
        shutil.copy2(source_root / name, destination / name)
    packages = {item["provider"]["binary_package"]: item["provider"] for item in libraries}
    copyright_dir = destination / "library-licenses"
    copyright_dir.mkdir(exist_ok=True)
    for name in packages:
        copyright_file = Path("/usr/share/doc") / name.split(":", 1)[0] / "copyright"
        if not copyright_file.is_file():
            raise ValueError("Static-input provider has no copyright file: " + name)
        shutil.copy2(copyright_file, copyright_dir / (name.replace(":", "_") + ".txt"))
        # Debian copyright files can refer to standard license texts instead of
        # embedding them. Preserve the exact referenced text, including symlinks.
        for reference in re.findall(r"/usr/share/common-licenses/[A-Za-z0-9_.-]+", copyright_file.read_text(encoding="utf-8")):
            license_path = Path(reference.rstrip("."))
            if license_path.is_file():
                shutil.copy2(license_path, copyright_dir / license_path.resolve().name)
    manifest = {"schema_version": 1, "builder": builder,
                "architecture": capture(compiler, "-dumpmachine"),
                "compiler": {"path": compiler, "version": capture(compiler, "--version").splitlines()[0],
                             "provider": package_for(Path(compiler))},
                "configuration_sha256": sha256(config), "flags": policy["flags"],
                "static_inputs": libraries, "corresponding_source_packages": list(packages.values()),
                "helpers": results}
    (destination / "BUILD.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destination / "REBUILD.txt").write_text(
        "The helper sources and original compiler flags are included. To rebuild with a modified LGPL library, "
        "install a compatible development toolchain containing that library, adapt the output paths in build-config.json, "
        "and run the included build-static-helpers.py with --config build-config.json --source-root sources "
        "--output-dir <new-provenance-directory> --builder <your-immutable-builder-reference>. "
        "Copy LICENSE and NOTICE into sources/ before that command. BUILD.json identifies the exact original "
        "libc and GCC runtime source packages, static-input hashes, compiler commands and output hashes. "
        "The application's build provenance does not prohibit replacing these helpers with your rebuilt versions.\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--builder", required=True)
    args = parser.parse_args()
    result = build(args.config, args.source_root, args.output_dir, args.builder)
    print(json.dumps({"builder": result["builder"], "helpers": [{"name": item["name"], "sha256": item["sha256"]} for item in result["helpers"]]}))
