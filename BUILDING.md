# Building the disclosed components

Use the exact source versions, distribution patches and build records for the
binary being inspected. A matching version string alone does not establish a
bit-for-bit reproducible build. General build tools and proprietary SDKs are
obtained separately under their own licenses.

## Debian and Ubuntu source packages

Download every artifact listed for the selected source package, retaining its
directory layout. The `.dsc` identifies the original archive and distribution
patch archive. Run `dpkg-source -x <package>.dsc` in a suitable Debian/Ubuntu build
environment, install the package's declared build dependencies, and use its
`debian/rules` / `dpkg-buildpackage` workflow. Do not substitute a different
distribution revision for a binary with the same upstream version.

## Fedora source packages

The source RPM includes the spec, distribution patches and upstream archives.
Use a matching Fedora build root and `rpmbuild --rebuild <package>.src.rpm` with
the spec's build dependencies. Consult each package's license files.

## Alpine source packages

Each package contains its `APKBUILD` and adjacent patches/scripts from the
recorded aports Git commit. Original source files were checked against the
APKBUILD checksums. Rebuild with the corresponding Alpine toolchain and `abuild`;
review an upstream build script before executing it.

## MinIO

The source catalog contains the exact main module and compiled dependency module
versions observed in the distributed binary. Every module ZIP was checked against
its Go `h1` content checksum; SHA-256 values and `.mod` / `.info` files are also
recorded. `restore_go_proxy.py` can restore a local Go module proxy from the
downloaded files. The original build uses Go 1.24.8, `CGO_ENABLED=0`,
`GOTOOLCHAIN=local` and `go install` for the pinned main module version. Select
that version from the catalog rather than building the repository's current HEAD.

## Collabora Online

The public build policy, upstream-package catalog, standalone build script,
adapter, branding and verification tools are included under their original
relative paths. The policy pins the source commit, matched Collabora Office core,
dependencies and clean base image. Follow `tools/collabora-open/README.md`.
The build uses the MPL source and original replacement branding; it does not
inherit the proprietary branding layer from the official CODE image.

## Static sandbox helpers

Only the two C helpers and their necessary build/provenance material are included
under `components/sandbox-helpers`. Use their recorded build environment and
library-source versions when relinking. The remainder of RUR1 BIDX is not needed
to modify these helpers.

## Other native components

The relevant source catalogs include upstream build recipes and pinned native
dependency versions where available. See the accompanying native-source audit
for any unresolved exact-build correspondence; a JavaScript wrapper alone is
not represented as complete source for a bundled native library or WASM binary.

## Bun and WebKit / JavaScriptCore

The `bun` source group contains the observed Bun versions and the exact WebKit
fork commits pinned by each version's `scripts/build/deps/webkit.ts`. Fetch the
group or select the required Bun version with `fetch_sources.py`. Preserve the
fork modifications and original per-file licenses; the WebKit code is not
covered solely by Bun's own MIT declaration.

Place the matching WebKit source at `vendor/WebKit` in the Bun checkout, or use
its `BUN_WEBKIT_PATH` option. Follow the preserved Bun local WebKit and release
build scripts, including the target architecture and ABI settings. The source
scope and Git-blob records describe each reconstructed WebKit archive. Git
history, unrelated test trees and compiled outputs are excluded; generated
source, legal notices and build resources are retained. No complete offline or
byte-identical Bun rebuild was performed in this audit. See `evidence/bun/` and
`PUBLICATION_LIMITATIONS.json`.
