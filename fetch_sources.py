"""Fetch selected corresponding-source artifacts; SPDX-License-Identifier: Apache-2.0."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import tarfile
import tempfile
import threading
from urllib.parse import urlsplit
from urllib.request import urlopen


def child(destination, name):
    root = destination.resolve()
    relative = PurePosixPath(name)
    if (not name or relative.is_absolute() or PureWindowsPath(name).drive
            or "\\" in name or ":" in name or ".." in relative.parts):
        raise ValueError("Source artifact path escapes destination")
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError("Source artifact path escapes destination")
    return target


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def temporary_output(target):
    """An exclusive file avoids shared .partial races and pre-existing symlinks."""
    target.parent.mkdir(parents=True, exist_ok=True)
    return tempfile.NamedTemporaryFile(mode="wb", dir=target.parent,
                                       prefix=target.name + ".", suffix=".partial", delete=False)


def publish(partial, target, checksum):
    try:
        partial.replace(target)
    except OSError:
        # Another process may have published the same verified file and opened it
        # on Windows, preventing replacement. Accept only the intended content.
        if not target.is_file() or sha(target) != checksum:
            raise


def download(item, target, timeout):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and sha(target) == item["sha256"]:
        return
    errors = []
    for url in item.get("urls", []):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise ValueError("Only credential-free HTTPS source URLs are accepted")
        partial = None
        try:
            with urlopen(url, timeout=timeout) as source, temporary_output(target) as output:
                partial = Path(output.name)
                shutil.copyfileobj(source, output)
            if sha(partial) != item["sha256"]:
                raise ValueError("Source checksum mismatch")
            publish(partial, target, item["sha256"])
            return
        except Exception as exc:
            errors.append(str(exc))
        finally:
            if partial is not None:
                partial.unlink(missing_ok=True)
    raise RuntimeError(f"Unable to obtain {item['file']}: {'; '.join(errors)}")


class BundleCache:
    """Verify a mirror once; copy only the requested regular archive member."""

    def __init__(self, bundles, destination, timeout):
        self.root = child(destination, ".source-bundles")
        self.timeout = timeout
        self.members = {}
        self.locks = {}
        self.archives = {}
        self.indexes = {}
        for bundle in bundles:
            child(self.root, bundle["file"])
            if bundle["file"] in self.locks:
                raise ValueError("Duplicate source bundle filename")
            self.locks[bundle["file"]] = threading.Lock()
            for name in bundle["artifacts"]:
                if name in self.members:
                    raise ValueError("Source artifact occurs in multiple bundles")
                self.members[name] = bundle

    def close(self):
        for name, lock in self.locks.items():
            with lock:
                archive = self.archives.pop(name, None)
                if archive is not None:
                    archive.close()
                self.indexes.pop(name, None)

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()

    def __del__(self):
        # Library callers using the original constructor API still release handles.
        for archive in getattr(self, "archives", {}).values():
            archive.close()

    def restore(self, item, target):
        bundle = self.members.get(item["file"])
        if bundle is None:
            raise ValueError("No source mirror contains this artifact")
        archive_path = child(self.root, bundle["file"])
        partial = None
        try:
            with self.locks[bundle["file"]]:
                if bundle["file"] not in self.archives:
                    download(dict(bundle, urls=[bundle["url"]]), archive_path, self.timeout)
                    archive = tarfile.open(archive_path, "r:*")
                    try:
                        index = {}
                        for member in archive.getmembers():
                            index.setdefault(member.name, []).append(member)
                    except Exception:
                        archive.close()
                        raise
                    self.archives[bundle["file"]] = archive
                    self.indexes[bundle["file"]] = index
                archive = self.archives[bundle["file"]]
                members = self.indexes[bundle["file"]].get(item["file"], [])
                if len(members) != 1 or not members[0].isfile():
                    raise ValueError("Source mirror member must be one regular file")
                if item.get("bytes") is not None and members[0].size != item["bytes"]:
                    raise ValueError("Source mirror member size mismatch")
                # A shared compressed reader must be held while copying. Reusing
                # it and the index avoids a full gzip member scan for every file.
                with archive.extractfile(members[0]) as source, temporary_output(target) as output:
                    partial = Path(output.name)
                    shutil.copyfileobj(source, output)
            if sha(partial) != item["sha256"]:
                raise ValueError("Source mirror artifact checksum mismatch")
            publish(partial, target, item["sha256"])
        finally:
            if partial is not None:
                partial.unlink(missing_ok=True)


def fetch(item, destination, timeout, bundles=None):
    target = child(destination, item["file"])
    try:
        download(item, target, timeout)
    except RuntimeError as original:
        if bundles is None:
            raise
        try:
            bundles.restore(item, target)
        except Exception as mirrored:
            raise RuntimeError(f"{original}; mirror: {mirrored}") from mirrored
    print(item["file"], flush=True)


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
    timeout = args.timeout or settings["timeout_seconds"]
    with BundleCache(catalog.get("bundles", []), args.destination, timeout) as bundles, \
            ThreadPoolExecutor(max_workers=args.workers or settings["workers"]) as pool:
        list(pool.map(lambda name: fetch(artifacts[name], args.destination,
                                        timeout, bundles), sorted(selected)))


if __name__ == "__main__":
    main()
