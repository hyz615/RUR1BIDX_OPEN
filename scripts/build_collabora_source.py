"""Build the configured open Collabora sources and original branding on Linux.

SPDX-License-Identifier: MPL-2.0
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
https://mozilla.org/MPL/2.0/

The working directory is explicit: use an adequately sized filesystem. No
proprietary brand repository, code-brand package or official image is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(args, *, cwd=None, env=None, capture=False):
    return subprocess.run([str(arg) for arg in args], cwd=cwd, env=env,
                          check=True, text=True, capture_output=capture)


def download(url: str, path: Path, digest: str | None = None):
    if not path.is_file():
        partial = path.with_name(path.name + ".partial")
        with urllib.request.urlopen(url) as source, partial.open("wb") as target:
            shutil.copyfileobj(source, target)
        partial.replace(path)
    if digest and sha256(path) != digest:
        raise ValueError(f"Download checksum mismatch: {path.name}")


def unpack(archive: Path, destination: Path):
    if destination.is_dir():
        return
    destination.mkdir(parents=True)
    with tarfile.open(archive) as stream:
        for member in stream:
            parts = Path(member.name).parts
            if len(parts) <= 1:
                continue
            member.name = str(Path(*parts[1:]))
            stream.extract(member, destination, filter="data")


def prepare(project: Path, recipe: dict, work: Path):
    source = work / "online"
    details = recipe["source"]
    archive = work / "upstream.tar.gz"
    download(details["archive_url"], archive, details["archive_sha256"])
    receipt = source / ".source-archive-sha256"
    if not receipt.is_file() or receipt.read_text().strip() != details["archive_sha256"]:
        source.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as stream:
            for member in stream:
                parts = Path(member.name).parts[1:]
                if not parts:
                    continue
                relative = Path(*parts).as_posix()
                if parts[0] == "engine" and not any(
                        relative == "engine/" + name or relative.startswith("engine/" + name + "/")
                        for name in details["archive_engine_directories"]):
                    continue
                member.name = relative
                stream.extract(member, source, filter="data")
        receipt.write_text(details["archive_sha256"] + "\n")
    # Supported upstream tarball-build mechanism; no private Git history needed.
    (source / "dist_git_hash").write_text(details["commit"][:details["version_hash_length"]] + "\n")
    for component, filename in (("node", "node.tar.xz"), ("poco", "poco.tar.bz2")):
        details = recipe[component]
        download(details["url"], work / filename, details["sha256"])
        unpack(work / filename, work / component)
    return source


def compile_sources(project: Path, recipe: dict, work: Path):
    source = prepare(project, recipe, work)
    jobs = str(recipe["parallel_jobs"])
    poco_prefix = work / "poco-install"
    run(["cmake", "-S", work / "poco", "-B", work / "poco-build",
         f"-DCMAKE_INSTALL_PREFIX={poco_prefix}", *recipe["poco"]["cmake_arguments"]])
    run(["cmake", "--build", work / "poco-build", "-j", jobs])
    run(["cmake", "--install", work / "poco-build"])
    env = dict(os.environ)
    env["PATH"] = str(work / "node" / "bin") + os.pathsep + env["PATH"]
    env["CPPFLAGS"] = f"-I{poco_prefix / 'include'}"
    env["LDFLAGS"] = f"-L{poco_prefix / 'lib'}"
    env["CXXFLAGS"] = " ".join([env.get("CXXFLAGS", ""),
                                 *["-D" + item for item in recipe["server_adapter"].get("compile_definitions", [])]]).strip()
    product = json.loads((project / recipe["branding"]["product_config"]).read_text(encoding="utf-8-sig"))
    run(["./autogen.sh"], cwd=source, env=env)
    run(["./configure", *recipe["configure_arguments"],
         f"--with-lokit-path={source / recipe['source']['include_path']}",
         f"--with-vendor={product['product_name']}",
         f"--with-build-id={recipe['build_id']}"], cwd=source, env=env)
    run(["make", "-C", "browser", "-j", jobs], cwd=source, env=env)
    adapter = recipe["server_adapter"]
    recipe_snapshot = work / "build-recipe.json"
    recipe_snapshot.write_text(json.dumps(recipe, indent=2) + "\n")
    run([sys.executable, project / adapter["script"], "--source", source,
         "--output", work / "server-cmake", "--config", recipe_snapshot], env=env)
    run(["cmake", "-S", work / "server-cmake", "-B", work / "server-build",
         f"-DCMAKE_PREFIX_PATH={poco_prefix}"])
    run(["cmake", "--build", work / "server-build", "-j", jobs])
    for name in adapter["executables"]:
        shutil.copy2(work / "server-build" / name, source / name)
    stage = work / "package-stage"
    stage.mkdir(exist_ok=True)
    # The binaries were built from the upstream target lists by the adapter.
    # Keep upstream install rules, suppressing only their duplicate C++ build.
    run(["make", "install", *recipe["install_make_arguments"], f"DESTDIR={stage}"], cwd=source, env=env)
    (stage / "usr/bin").mkdir(parents=True, exist_ok=True)
    for name in adapter["executables"]:
        shutil.copy2(work / "server-build" / name, stage / "usr/bin" / name)
    return stage


def component_inventory(recipe: dict, work: Path, stage: Path, destination: Path):
    """Inventory actual adapter outputs; do not claim an engine gbuild SBOM."""
    browser = work / "online/browser"
    shipped = browser / "sbom-shipped-js.txt"
    names = set()
    for line in shipped.read_text().splitlines():
        parts = Path(line).parts
        if parts and parts[0] == "node_modules":
            names.add("/".join(parts[1:3]) if parts[1].startswith("@") else parts[1])
    components = []
    licenses = destination / "licenses"
    for name in sorted(names):
        module = browser / "node_modules" / name
        package = json.loads((module / "package.json").read_text())
        components.append({"ecosystem": "npm", "name": package["name"], "version": package["version"],
                           "license": package.get("license", "NOASSERTION"), "source": package.get("repository")})
        for asset in module.iterdir():
            if asset.is_file() and asset.name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE")):
                target = licenses / "npm" / name / asset.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(asset, target)
    for asset in (work / "poco").rglob("*"):
        if asset.is_file() and asset.name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE")):
            target = licenses / "poco" / asset.relative_to(work / "poco")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset, target)
    executables = []
    for name in recipe["server_adapter"]["executables"]:
        binary = stage / "usr/bin" / name
        result = run(["ldd", binary], capture=True)
        dependencies = sorted(set(re.findall(r"^\s*(\S+)\s+=>", result.stdout, re.MULTILINE)))
        executables.append({"path": "usr/bin/" + name, "sha256": sha256(binary), "needed_shared_libraries": dependencies})
    payload = {"schema_version": 1, "coverage": "Source-built online service and browser; engine packages are recorded separately",
               "source": recipe["source"], "poco_source": recipe["poco"], "npm": components, "executables": executables}
    (destination / "COMPONENTS.json").write_text(json.dumps(payload, indent=2) + "\n")


def package(project: Path, recipe: dict, work: Path):
    stage = work / "package-stage"
    if not (stage / "usr/bin/coolwsd").is_file():
        raise ValueError("Compile the server before packaging")
    original = work / "original-debs"
    original.mkdir(exist_ok=True)
    upstream = json.loads((project / recipe["engine"]["upstream_packages"]).read_text(encoding="utf-8-sig"))
    for item in upstream["files"]:
        if Path(item["path"]).name != item["path"]:
            raise ValueError("Invalid upstream package filename")
        download(upstream["repository_url"].rstrip("/") + "/" + item["path"],
                 original / item["path"], item["sha256"])
    engine_root = work / "engine-runtime"
    version_file = engine_root / recipe["engine"]["runtime_path"].lstrip("/") / recipe["engine"]["version_file"]
    if not version_file.is_file():
        for path in original.glob(recipe["engine"]["packages_glob"]):
            run(["dpkg-deb", "-x", path, engine_root])
    build_id = re.search(r"^buildid=(.+)$", version_file.read_text(), re.MULTILINE)
    if not build_id or build_id.group(1) != recipe["source"]["commit"]:
        raise ValueError("Engine binary build ID does not match its corresponding source")
    template, = original.glob(recipe["package"]["template_package_glob"])
    control = stage / "DEBIAN"
    run(["dpkg-deb", "-e", template, control])
    original_fields = (control / "control").read_text()
    settings = recipe["package"]
    for relative, installed in settings["source_install_files"].items():
        destination = stage / installed
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(work / "online" / relative, destination)
    from lxml import etree
    configuration_file = stage / settings["configuration_file"]
    tree = etree.parse(str(configuration_file))
    for selector, value in settings["configuration_values"].items():
        node = tree.find(selector)
        if node is None:
            raise ValueError(f"Configured editor setting is missing: {selector}")
        node.text = value
        if "relative" in node.attrib:
            node.set("relative", "false")
    tree.write(str(configuration_file), encoding="utf-8", xml_declaration=True)
    binaries = []
    for path in (stage / "usr/bin").iterdir():
        if path.is_file():
            with path.open("rb") as stream:
                if stream.read(4) == b"\x7fELF":
                    binaries.append(path)
    dependency_output = run(["dpkg-shlibdeps", "-O", *["-e" + str(path) for path in binaries]],
                            cwd=work / "online", capture=True).stdout
    generated_dependencies = dependency_output.strip().removeprefix("shlibs:Depends=")
    previous_dependencies = re.search(r"^Depends: (.*)$", original_fields, re.MULTILINE).group(1)
    if run(["dpkg", "--print-architecture"], capture=True).stdout.strip() != settings["architecture"]:
        raise ValueError("Build host architecture does not match the configured package target")
    fields = {"Package": settings["name"], "Version": settings["version"], "Architecture": settings["architecture"],
              "Maintainer": settings["maintainer"], "Description": settings["description"],
              "Depends": previous_dependencies + ", " + generated_dependencies + ", libcap2-bin",
              "Provides": ", ".join(settings["replaces"]),
              "Conflicts": ", ".join(settings["replaces"]), "Replaces": ", ".join(settings["replaces"])}
    for key, value in fields.items():
        pattern = rf"^{re.escape(key)}:.*(?:\n[ \t].*)*"
        replacement = f"{key}: {value}"
        if re.search(pattern, original_fields, re.MULTILINE):
            original_fields = re.sub(pattern, lambda _: replacement, original_fields, flags=re.MULTILINE)
        else:
            original_fields = original_fields.rstrip() + "\n" + replacement + "\n"
    (control / "control").write_text(original_fields.rstrip() + "\n")
    postinst = control / "postinst"
    capability_commands = [f"setcap {value} {path}" for path, value in settings["capabilities"].items()]
    postinst.write_text(postinst.read_text() + '\nif [ "$1" = configure ]; then\n' +
                       "\n".join("    " + command for command in capability_commands) + "\nfi\n")
    # A new file set must never inherit checksums from the binary template.
    (control / "md5sums").unlink(missing_ok=True)
    product = json.loads((project / recipe["branding"]["product_config"]).read_text(encoding="utf-8-sig"))
    brand_target = stage / recipe["branding"]["install_directory"]
    brand_target.mkdir(parents=True, exist_ok=True)
    for asset in (project / recipe["branding"]["source_directory"]).iterdir():
        if asset.suffix not in {".js", ".css"}:
            continue
        contents = asset.read_text(encoding="utf-8")
        for key, value in {"PRODUCT_NAME": json.dumps(product["product_name"], ensure_ascii=True)[1:-1],
                           "PRIMARY_COLOR": product["primary_color"]}.items():
            contents = contents.replace("{{" + key + "}}", value)
        (brand_target / asset.name).write_text(contents, encoding="utf-8")
    provenance = {"source": recipe["source"], "package": settings,
                  "source_url": recipe["branding"]["source_url"],
                  "branding": "Original branding distributed under MPL-2.0; no code-brand package"}
    document_dir = stage / "usr/share/doc" / settings["name"]
    document_dir.mkdir(parents=True, exist_ok=True)
    (document_dir / "SOURCE.json").write_text(json.dumps(provenance, indent=2) + "\n")
    for name in ("COPYING", "LICENSE", "NOTICE"):
        path = work / "online" / name
        if path.is_file():
            shutil.copy2(path, document_dir / name)
    component_inventory(recipe, work, stage, document_dir)
    output = project / recipe["output"]["package_directory"]
    output.mkdir(parents=True, exist_ok=True)
    name = f"{settings['name']}_{settings['version']}_{settings['architecture']}.deb"
    # DrvFS cannot reliably retain POSIX modes. Normalize in a small native
    # temporary stage so neither data nor maintainer scripts become world-writable.
    with tempfile.TemporaryDirectory(prefix="open-editor-package-") as temporary:
        native = Path(temporary) / "package"
        shutil.copytree(stage, native, symlinks=True)
        for path in [native, *native.rglob("*")]:
            if path.is_symlink():
                continue
            relative = path.relative_to(native)
            executable = (relative.parts[:2] == ("usr", "bin") or
                          relative.parts[:1] == ("DEBIAN",) and path.name in {"preinst", "postinst", "prerm", "postrm", "config"})
            path.chmod(0o755 if path.is_dir() or executable else 0o644)
        run(["dpkg-deb", "--root-owner-group", "--build", native, output / name])
    manifest = {"schema_version": 1, "source": recipe["source"], "package": settings,
                "recipe_sha256": hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest(),
                "source_url": recipe["branding"]["source_url"], "configure_arguments": recipe["configure_arguments"],
                "files": [{"path": name, "sha256": sha256(output / name), "bytes": (output / name).stat().st_size}],
                "executable_sha256": sha256(stage / "usr/bin/coolwsd"),
                "poco": recipe["poco"], "engine": recipe["engine"], "upstream_packages": upstream,
                "package_notice_files": [{"path": "/" + path.relative_to(stage).as_posix(), "sha256": sha256(path)}
                                         for path in sorted(document_dir.rglob("*")) if path.is_file()]}
    engine_location = engine_root / recipe["engine"]["runtime_path"].lstrip("/")
    manifest["engine_notice_files"] = [{"path": recipe["engine"]["runtime_path"] + "/" + path.name,
                                       "sha256": sha256(path)} for path in sorted(engine_location.iterdir())
                                      if path.name in {"LICENSE", "LICENSE.html", "NOTICE"} or path.name.endswith("-sbom.spdx.json")]
    (output / recipe["output"]["manifest_name"]).write_text(json.dumps(manifest, indent=2) + "\n")
    return output


def build_image(project: Path, recipe: dict, work: Path):
    output = project / recipe["output"]["package_directory"]
    manifest = json.loads((output / recipe["output"]["manifest_name"]).read_text())
    context = work / "image-context"
    packages = context / "packages"
    packages.mkdir(parents=True, exist_ok=True)
    for path in (work / "original-debs").glob(recipe["engine"]["packages_glob"]):
        expected = next(item["sha256"] for item in manifest["upstream_packages"]["files"] if item["path"] == path.name)
        if sha256(path) != expected:
            raise ValueError("Engine package changed after source verification")
        shutil.copy2(path, packages / path.name)
    for item in manifest["files"]:
        path = output / item["path"]
        if sha256(path) != item["sha256"]:
            raise ValueError("Built package changed after manifest creation")
        shutil.copy2(path, packages / path.name)
    image = recipe["docker"]
    shutil.copy2(project / image["dockerfile"], context / "Dockerfile")
    shutil.copy2(project / image["entrypoint"], context / "entrypoint.sh")
    run(["docker", "build", "--build-arg", f"BASE_IMAGE={image['base_image']}",
         "--build-arg", "RUNTIME_PACKAGES=" + " ".join(image["runtime_packages"]),
         "--build-arg", f"SOURCE_URL={recipe['branding']['source_url']}",
         "--build-arg", f"SOURCE_REVISION={recipe['source']['commit']}", "-t", image["tag"], context])
    manifest["image"] = {"tag": image["tag"], "id": run(["docker", "image", "inspect", "--format",
                         "{{.Id}}", image["tag"]], capture=True).stdout.strip()}
    installed = run(["docker", "run", "--rm", "--entrypoint", "dpkg-query", image["tag"],
                     "-W", "-f=${binary:Package}\t${Version}\n"], capture=True).stdout
    manifest["image"]["packages"] = [{"name": line.split("\t")[0], "version": line.split("\t")[1]}
                                      for line in installed.splitlines()]
    (output / recipe["output"]["manifest_name"]).write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--phase", choices=["compile", "package", "image", "all"], default="all")
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("Run this build inside Linux/WSL; paths must be Linux paths")
    project, work = args.project.resolve(), args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    recipe = json.loads(args.config.read_text(encoding="utf-8-sig"))
    if args.phase in {"compile", "all"}:
        compile_sources(project, recipe, work)
    if args.phase in {"package", "all"}:
        package(project, recipe, work)
    if args.phase in {"image", "all"}:
        build_image(project, recipe, work)


if __name__ == "__main__":
    main()
