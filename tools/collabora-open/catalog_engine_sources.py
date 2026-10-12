"""Extract actual engine dependency source URLs and hashes from packaged SPDX 3 SBOMs.

SPDX-License-Identifier: MPL-2.0
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
https://mozilla.org/MPL/2.0/
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def catalog(engine: Path, revision: str, download_list: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    embedded = []
    evidence = []
    for source in sorted(engine.glob("*-sbom.spdx.json")):
        graph = json.loads(source.read_text())["@graph"]
        index = {node["spdxId"]: node for node in graph if "spdxId" in node}
        relationships = [node for node in graph if node.get("type") == "Relationship"]
        licenses = {}
        for node in relationships:
            if node.get("relationshipType") == "hasDeclaredLicense":
                licenses[node["from"]] = [index[identifier]["simplelicensing_licenseExpression"]
                                           for identifier in node["to"] if "simplelicensing_licenseExpression" in index[identifier]]
        for node in graph:
            if node.get("software_primaryPurpose") != "source":
                continue
            urls = [ref["locator"] for ref in node.get("externalRef", []) if ref.get("externalRefType") == "SourceArtifact"]
            hashes = [item["hashValue"] for item in node.get("verifiedUsing", []) if item.get("algorithm") == "sha256"]
            if not urls or not hashes:
                embedded.append({"urls": urls, "evidence": source.name,
                                 "note": "Upstream references a source-tree file; verify it in the pinned monorepo archive rather than treating this URL as a separately hashed tarball."})
                continue
            for relation in relationships:
                if relation.get("relationshipType") != "generates" or relation.get("from") != node["spdxId"]:
                    continue
                for identifier in relation["to"]:
                    package = index[identifier]
                    key = (package["name"], hashes[0])
                    item = artifacts.setdefault(key, {"name": package["name"], "version": package.get("software_packageVersion"),
                        "declared_licenses": licenses.get(identifier, []), "urls": urls, "sha256": hashes[0], "sbom_evidence": []})
                    if source.name not in item["sbom_evidence"]:
                        item["sbom_evidence"].append(source.name)
        target = output / source.name
        if target.exists():
            target.chmod(0o644)
        shutil.copyfile(source, target)
        evidence.append({"path": source.name, "sha256": digest(source)})
    for name in ("LICENSE", "LICENSE.html", "NOTICE"):
        source = engine / name
        if source.is_file():
            shutil.copy2(source, output / name)
            evidence.append({"path": name, "sha256": digest(source)})
    shutil.copy2(download_list, output / "engine-download.lst")
    payload = {"schema_version": 1, "source_revision": revision,
               "note": "The monorepo archive does not embed these external source tarballs. Fetch the declared URLs and verify SHA256, then apply the matching monorepo engine/external patches and build recipes. License alternatives require an explicit selection; this catalog is evidence, not a claim that every listed dependency requires source distribution.",
               "download_list": {"path": "engine-download.lst", "sha256": digest(download_list)},
               "source_patch_directory": "engine/external", "evidence_files": evidence,
               "embedded_source_references": embedded,
               "external_sources": sorted(artifacts.values(), key=lambda item: item["name"])}
    (output / "engine-source-catalog.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"components": len(artifacts), "output": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--download-list", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalog(args.engine, args.source_revision, args.download_list, args.output)
