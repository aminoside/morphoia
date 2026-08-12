/* SPDX-FileCopyrightText: 2026 Olivier Ami */
/* SPDX-License-Identifier: Apache-2.0 OR MIT */

#include "morphoia/engine.h"

#include <stdio.h>

int main(void) {
  morphoia_version_info_t version = {0};
  morphoia_diagnostic_t diagnostic = {0};
  version.struct_size = (uint32_t)sizeof(version);
  version.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  diagnostic.struct_size = (uint32_t)sizeof(diagnostic);
  diagnostic.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  if (morphoia_engine_get_version(&version, &diagnostic) != MORPHOIA_STATUS_OK) {
    return 1;
  }
  (void)printf(
      "installed_consumer: PASS (ABI %u, engine %.*s)\n",
      version.engine_abi_version,
      (int)version.version_string.size,
      version.version_string.data);
  return 0;
}
