// SPDX-License-Identifier: MPL-2.0
// This Source Code Form is subject to the Mozilla Public License, v. 2.0.
// https://mozilla.org/MPL/2.0/
#include <COKit/COKitInit.h>
#include <cstdlib>
#include <iostream>

int main(int argc, char** argv)
{
    if (argc != 3)
        return EXIT_FAILURE;
    char* library = nullptr;
    void* handle = cok_dlopen(argv[1], &library);
    if (!handle)
        return EXIT_FAILURE;
    auto* preinit = reinterpret_cast<CokHookPreInit2*>(cok_dlsym(handle, "cok_preinit_2"));
    std::free(library);
    COKit* engine = nullptr;
    if (!preinit || preinit(argv[1], argv[2], &engine) != 0 || !engine)
        return EXIT_FAILURE;
    // The returned std::string crosses the engine ABI boundary. Its contents
    // and destructor must both work, otherwise a daemon worker will crash.
    const std::string version = engine->getVersionInfo();
    std::cout << version << '\n';
    return EXIT_SUCCESS;
}
