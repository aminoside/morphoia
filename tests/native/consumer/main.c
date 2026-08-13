/* SPDX-FileCopyrightText: 2026 Olivier Ami */
/* SPDX-License-Identifier: Apache-2.0 OR MIT */

#include "morphoia/engine.h"

#include <stdio.h>
#include <string.h>

static morphoia_string_view_t view_of(const char* const value) {
  morphoia_string_view_t view;
  view.data = value;
  view.size = strlen(value);
  return view;
}

int main(void) {
  morphoia_version_info_t version = {0};
  morphoia_diagnostic_t diagnostic = {0};
  morphoia_capability_info_t capability = {0};
  morphoia_engine_ir_unit_t unit = {0};
  morphoia_engine_ir_unit_validation_t unit_validation = {0};
  morphoia_context_t* context = NULL;
  uint8_t digest[MORPHOIA_SHA256_DIGEST_SIZE] = {0};
  char canonical[16] = {0};
  size_t required_size = 0U;
  version.struct_size = (uint32_t)sizeof(version);
  version.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  diagnostic.struct_size = (uint32_t)sizeof(diagnostic);
  diagnostic.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  capability.struct_size = (uint32_t)sizeof(capability);
  capability.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  unit.struct_size = (uint32_t)sizeof(unit);
  unit.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  unit.code = view_of("mm");
  unit.dimensions[0] = 1;
  unit.si_factor_coefficient = 1;
  unit.si_factor_scale = -3;
  unit_validation.struct_size = (uint32_t)sizeof(unit_validation);
  unit_validation.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  if (morphoia_engine_get_version(&version, &diagnostic) != MORPHOIA_STATUS_OK) {
    return 1;
  }
  if (morphoia_context_create(NULL, &context, &diagnostic) != MORPHOIA_STATUS_OK) {
    return 1;
  }
  if (morphoia_context_query_capability(
          context,
          view_of(MORPHOIA_CAPABILITY_ENGINE_IR_MANIFEST),
          &capability,
          &diagnostic) != MORPHOIA_STATUS_OK ||
      capability.supported != 1U) {
    return 1;
  }
  capability.struct_size = (uint32_t)sizeof(capability);
  capability.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  if (morphoia_context_query_capability(
          context,
          view_of(MORPHOIA_CAPABILITY_ENGINE_IR_CORE_SI),
          &capability,
          &diagnostic) != MORPHOIA_STATUS_OK ||
      capability.supported != 1U) {
    return 1;
  }
  if (morphoia_context_validate_engine_ir_unit(
          context, &unit, &unit_validation, &diagnostic) != MORPHOIA_STATUS_OK ||
      unit_validation.qualified != 1U) {
    return 1;
  }
  if (morphoia_canonical_json_profile1(
          context,
          view_of("{\"b\":2,\"a\":1}"),
          NULL,
          NULL,
          0U,
          &required_size,
          digest,
          &diagnostic) != MORPHOIA_STATUS_BUFFER_TOO_SMALL ||
      required_size != strlen("{\"a\":1,\"b\":2}")) {
    return 1;
  }
  if (morphoia_canonical_json_profile1(
          context,
          view_of("{\"b\":2,\"a\":1}"),
          NULL,
          canonical,
          sizeof(canonical),
          &required_size,
          digest,
          &diagnostic) != MORPHOIA_STATUS_OK ||
      memcmp(canonical, "{\"a\":1,\"b\":2}", required_size) != 0) {
    return 1;
  }
  if (morphoia_context_destroy(&context, &diagnostic) != MORPHOIA_STATUS_OK) {
    return 1;
  }
  (void)printf(
      "installed_consumer: PASS (ABI %u, engine %.*s)\n",
      version.engine_abi_version,
      (int)version.version_string.size,
      version.version_string.data);
  return 0;
}
