"""Fetch selected corresponding-source artifacts; SPDX-License-Identifier: Apache-2.0."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
from urllib.parse import urlsplit
from urllib.request import urlopen


def fetch(item, destination, timeout):
    root = destination.resolve()
    target = (root / item["file"]).resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError("Source artifact path escapes destination")
    target.parent.mkdir(parents=True, exist_ok=True)

    def sha(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    if target.is_file() and sha(target) == item["sha256"]:
        return
    errors = []
    for url in item["urls"]:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise ValueError("Only credential-free HTTPS source URLs are accepted")
        partial = target.with_name(target.name + ".partial")
        try:
            with urlopen(url, timeout=timeout) as source, partial.open("wb") as output:
                shutil.copyfileobj(source, output)
            if sha(partial) != item["sha256"]:
                raise ValueError("Source checksum mismatch")
            partial.replace(target)
            print(item["file"], flush=True)
            return
        except Exception as exc:
            errors.append(str(exc))
        finally:
            partial.unlink(missing_ok=True)
    raise RuntimeError(f"Unable to obtain {item['file']}: {'; '.join(errors)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--list", action="store_true")
    selection.add_argument("--component")
    selection.add_argument("--group")
    selection.add_argument("--all", action="store_true")
    parser.add_argument("--version")
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--timeout", type=float)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8-sig"))
    if args.list:
        for item in catalog["components"]:
            print(item["name"], item["version"], item.get("group", ""))
        return
    if args.destination is None:
        parser.error("--destination is required for downloads")
    settings = json.loads((args.catalog.parent / "download-settings.json").read_text(encoding="utf-8"))
    components = [item for item in catalog["components"]
                  if (args.all or item["name"] == args.component or item.get("group") == args.group)
                  and (not args.version or item["version"] == args.version)]
    if not components:
        parser.error("No matching component/version/group; use --list")
    selected = {name for item in components for name in item["artifacts"]}
    artifacts = {item["file"]: item for item in catalog["artifacts"]}
    with ThreadPoolExecutor(max_workers=args.workers or settings["workers"]) as pool:
        list(pool.map(lambda name: fetch(artifacts[name], args.destination,
                                        args.timeout or settings["timeout_seconds"]), sorted(selected)))


if __name__ == "__main__":
    main()
