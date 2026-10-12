"""Restore a local Go source proxy; SPDX-License-Identifier: Apache-2.0."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def escape(value):
    # Go module proxy protocol encodes upper-case letters as !lowercase.
    return "".join("!" + char.lower() if char.isupper() else char for char in value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    root = args.destination.resolve()
    for item in json.loads(args.catalog.read_text(encoding="utf-8"))["artifacts"]:
        if "module" not in item:
            continue
        source = (args.sources / item["file"]).resolve()
        if not source.is_relative_to(args.sources.resolve()):
            raise ValueError("Source path escapes download directory")
        with source.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                raise ValueError(f"Source checksum mismatch: {item['file']}")
        relative = f"{escape(item['module'])}/@v/{escape(item['module_version'])}.{item['module_extension']}"
        target = (root / relative).resolve()
        if not target.is_relative_to(root):
            raise ValueError("Invalid Go module path")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    print("Local module proxy:", root.as_uri())


if __name__ == "__main__":
    main()
