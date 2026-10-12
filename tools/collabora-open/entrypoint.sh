#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the Mozilla Public License, v. 2.0.
# See https://mozilla.org/MPL/2.0/.
set -eu
if [ -n "${aliasgroup1:-}" ]; then
    coolconfig set 'storage.wopi.alias_groups[@mode]' groups
    coolconfig set 'storage.wopi.alias_groups.group[0].host' "$aliasgroup1"
    coolconfig set 'storage.wopi.alias_groups.group[0].host[@allow]' true
fi
# extra_params follows the documented Collabora image contract. It is supplied
# by the installation configuration, not from document content or a web request.
set -f
exec /usr/bin/coolwsd ${extra_params:-} "$@"
