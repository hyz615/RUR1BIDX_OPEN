"""Read upstream gbuild object lists and build Online without rebuilding its engine.

SPDX-License-Identifier: MPL-2.0
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
https://mozilla.org/MPL/2.0/

The engine is loaded through COKit at runtime. This adapter preserves the upstream
translation-unit lists, library boundaries and whole-archive registrations. It
does not copy a historical hand-maintained list of server source files.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path


def block(text: str, action: str, target: str) -> str:
    match = re.search(r"\$\(eval \$\(call gb_(?:Executable|StaticLibrary)_" + action +
                      "," + re.escape(target) + r",\s*\\\n(.*?)\n\)\)", text, re.DOTALL)
    return match.group(1).replace("\\", " ") if match else ""


def generate(source: Path, destination: Path, settings: dict):
    entries = {}
    for path in (source / "gbuild").glob("*.mk"):
        if path.stem.startswith(("StaticLibrary_", "Executable_")):
            kind, name = path.stem.split("_", 1)
            entries[name] = (kind, path.read_text())
    needed = set(settings["executables"])
    pending = list(needed)
    while pending:
        name = pending.pop()
        kind, content = entries[name]
        dependencies = block(content, "use_static_libraries", name).split()
        for dependency in dependencies:
            if dependency in entries and dependency not in needed:
                needed.add(dependency)
                pending.append(dependency)
        for dependency in settings.get("additional_libraries", {}).get(name, []):
            if dependency not in needed:
                needed.add(dependency)
                pending.append(dependency)
    cmake = ["cmake_minimum_required(VERSION 3.24)", "project(OnlineOpen LANGUAGES C CXX)",
             "set(CMAKE_CXX_STANDARD 20)", "set(CMAKE_CXX_STANDARD_REQUIRED ON)",
             "set(CMAKE_POSITION_INDEPENDENT_CODE ON)", "set(CMAKE_BUILD_TYPE Release)",
             "find_package(Poco REQUIRED COMPONENTS Foundation XML Util Net NetSSL Crypto JSON Zip)",
             "find_package(OpenSSL REQUIRED)", "find_package(PNG REQUIRED)", "find_package(ZLIB REQUIRED)",
             "find_package(EXPAT REQUIRED)", "find_package(Threads REQUIRED)",
             "add_compile_definitions(HAVE_CONFIG_H POCO_STATIC $<$<COMPILE_LANGUAGE:C>:_DEFAULT_SOURCE>)"]
    include_dirs = [source, *[source / item for item in settings["include_directories"]]]
    cmake.append("include_directories(" + " ".join(json.dumps(str(p)) for p in include_dirs) + ")")
    cmake.append("add_compile_definitions(" + " ".join(settings.get("compile_definitions", [])) + ")")
    for name in sorted(needed):
        kind, content = entries[name]
        files = []
        for action, suffix in (("add_generated_exception_objects", ".cpp"), ("add_generated_cobjects", ".c")):
            payload = block(content, action, name)
            # Upstream's optional fuzzer-main conditional contains a source path;
            # production builds include it. Unknown expressions are rejected.
            for relative in re.findall(r"[A-Za-z_][A-Za-z0-9_-]*/[A-Za-z0-9_./-]+", payload):
                path = source / (relative + suffix)
                if not path.is_file():
                    raise ValueError(f"Missing upstream source: {path}")
                files.append(path)
        if not files:
            raise ValueError(f"No upstream translation units for {name}")
        constructor = "add_executable" if kind == "Executable" else "add_library"
        library_type = " STATIC" if kind != "Executable" else ""
        cmake.append(f"{constructor}({name}{library_type} " + " ".join(json.dumps(str(p)) for p in files) + ")")
        flags = settings.get("compile_options", {}).get(name, [])
        if flags:
            cmake.append(f"target_compile_options({name} PRIVATE " + " ".join(flags) + ")")
        # CMake's imported Poco targets supply their bundled-library defines and
        # generated include paths even when this library does not link Poco yet.
        cmake.append(f"target_include_directories({name} SYSTEM PRIVATE $<TARGET_PROPERTY:Poco::Foundation,INTERFACE_INCLUDE_DIRECTORIES>)")
        cmake.append(f"target_compile_definitions({name} PRIVATE $<TARGET_PROPERTY:Poco::Foundation,INTERFACE_COMPILE_DEFINITIONS>)")
    for name in settings["executables"]:
        _, content = entries[name]
        dependencies = [p for p in block(content, "use_static_libraries", name).split() if p in entries]
        dependencies += settings.get("additional_libraries", {}).get(name, [])
        whole = settings.get("whole_archive", {}).get(name, [])
        normal = [p for p in dependencies if p not in whole]
        all_poco = ["$<TARGET_FILE:Poco::" + p + ">" for p in settings["poco_components"]]
        links = ["-Wl,--start-group", *normal, "-Wl,--whole-archive", *whole, *all_poco,
                 "-Wl,--no-whole-archive", "OpenSSL::SSL", "OpenSSL::Crypto", "PNG::PNG", "ZLIB::ZLIB",
                 "EXPAT::EXPAT", "zstd", "cap", "Threads::Threads", "${CMAKE_DL_LIBS}", "rt", "-Wl,--end-group"]
        cmake.append(f"target_link_libraries({name} PRIVATE " + " ".join(links) + ")")
        cmake.append(f"target_link_options({name} PRIVATE -Wl,-E)")
        cmake.append(f"install(TARGETS {name} RUNTIME DESTINATION bin)")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "CMakeLists.txt").write_text("\n".join(cmake) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    generate(args.source.resolve(), args.output.resolve(), json.loads(args.config.read_text())["server_adapter"])
