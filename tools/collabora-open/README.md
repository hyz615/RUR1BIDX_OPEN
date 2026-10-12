# Open Collabora build

`config/collabora_build.json` pins the upstream source commit, engine version,
POCO source checksum, Node build tool, base image digest and original brand assets.
Build the server and browser from MPL source; never use an official branded image
as a base and never fetch `online-branding` or install `code-brand`.

Run in Ubuntu matching `config/collabora_runtime.json`'s package target:

```sh
python3 scripts/build_collabora_source.py \
  --project "$PROJECT" --config "$PROJECT/config/collabora_build.json" \
  --work-dir "$BUILD_DIRECTORY" --phase all
```

The host needs the standard C/C++ and autotools toolchain, CMake, Git, curl,
pkg-config, libcap/libpam/libpng/libssl/libzstd development headers, Python polib
and lxml, dpkg-dev, fontconfig and Docker Engine. Build logs and all source caches
should be retained in the working directory. `parallel_jobs` is configurable.

The engine packages are reused from the matching verified dependency bundle.
Their `program/versionrc` build ID must match the source commit. Upstream's
`docker/README` at that commit explicitly documents a "100% open source" build
from packages with `nobrand=yes`. The engine's MPL source is `engine/` in the same
monorepo; retain its LICENSE, NOTICE, external source references and complete
corresponding source alongside the binary package record.

The resulting `rur1-coolwsd` package replaces the stock daemon. Its own brand JS
and CSS are licensed under MPL-2.0. Package generation retains upstream installer
scripts, detects the new binaries' dynamic library dependencies, and records
source and binary hashes. Product names and colors come from `config/product.json`.
The clean image starts from a pinned Ubuntu image and installs only the open
engine packages and newly built daemon; proprietary brand resources never enter
any image layer.

After validating the service, rebuild both release bundles with
`scripts/build_collabora_package_bundle.py` and
`scripts/build_collabora_image_bundle.py`. Both use the verified source-build
manifest. Runtime installation requires those verified bundles; it cannot
silently fall back to a branded upstream image. Remote user-managed services
remain independently configurable.

Publish the exact monorepo source archive, the POCO source archive and these build
files and original brand assets under the source release recorded in the build
manifest. Include all applicable upstream licenses and notices. `RUR1BIDX_OPEN`
contains only these covered components and build materials, not RVX business code.
