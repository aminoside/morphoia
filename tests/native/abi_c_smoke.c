/* SPDX-FileCopyrightText: 2026 Olivier Ami */
/* SPDX-License-Identifier: Apache-2.0 OR MIT */

#include "morphoia/engine.h"

#include <stddef.h>
#include <stdio.h>
#include <string.h>

_Static_assert(sizeof(morphoia_status_t) == 4U, "status ABI must remain 32-bit");
_Static_assert(
    MORPHOIA_DIAGNOSTIC_MESSAGE_CAPACITY == 256U,
    "diagnostic storage capacity changed unexpectedly");
_Static_assert(
    offsetof(morphoia_diagnostic_t, abi_version) == sizeof(uint32_t),
    "diagnostic ABI prefix changed");
_Static_assert(
    offsetof(morphoia_version_info_t, abi_version) == sizeof(uint32_t),
    "version ABI prefix changed");
_Static_assert(
    offsetof(morphoia_allocator_t, abi_version) == sizeof(uint32_t),
    "allocator ABI prefix changed");
_Static_assert(
    offsetof(morphoia_context_options_t, abi_version) == sizeof(uint32_t),
    "context options ABI prefix changed");
_Static_assert(
    MORPHOIA_CONTEXT_OPTIONS_V1_SIZE ==
        offsetof(morphoia_context_options_t, allocator) + MORPHOIA_ALLOCATOR_V1_SIZE,
    "context options v1 must freeze its nested allocator prefix");

static int require_true(const int condition, const char* const message) {
  if (condition != 0) {
    return 0;
  }
  (void)fprintf(stderr, "abi_c_smoke: %s\n", message);
  return 1;
}

static int view_equals(const morphoia_string_view_t view, const char* const expected) {
  const size_t expected_size = strlen(expected);
  return view.data != NULL && view.size == expected_size &&
         memcmp(view.data, expected, expected_size) == 0;
}

int main(void) {
  morphoia_diagnostic_t diagnostic = {0};
  morphoia_version_info_t version = {0};
  morphoia_context_t* context = NULL;
  uint32_t context_abi = 0U;
  int failures = 0;

  diagnostic.struct_size = (uint32_t)sizeof(diagnostic);
  diagnostic.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  version.struct_size = (uint32_t)sizeof(version);
  version.abi_version = MORPHOIA_ENGINE_ABI_VERSION;

  failures += require_true(
      morphoia_engine_get_version(&version, &diagnostic) == MORPHOIA_STATUS_OK,
      "version query failed");
  failures += require_true(
      version.engine_abi_version == MORPHOIA_ENGINE_ABI_VERSION,
      "unexpected engine ABI version");
  failures += require_true(view_equals(version.version_string, "0.0.1"), "version mismatch");

  failures += require_true(
      morphoia_context_create(NULL, &context, &diagnostic) == MORPHOIA_STATUS_OK,
      "default context creation failed");
  failures += require_true(context != NULL, "context is null after successful creation");
  failures += require_true(
      morphoia_context_get_abi_version(context, &context_abi, &diagnostic) ==
          MORPHOIA_STATUS_OK,
      "context ABI query failed");
  failures += require_true(
      context_abi == MORPHOIA_ENGINE_ABI_VERSION,
      "context ABI does not match public ABI");
  failures += require_true(
      view_equals(morphoia_status_name(MORPHOIA_STATUS_OK), "MORPHOIA_STATUS_OK"),
      "stable status name mismatch");

  failures += require_true(
      morphoia_context_destroy(&context, &diagnostic) == MORPHOIA_STATUS_OK,
      "context destruction failed");
  failures += require_true(context == NULL, "context was not consumed by destruction");
  failures += require_true(
      morphoia_context_destroy(NULL, &diagnostic) == MORPHOIA_STATUS_OK,
      "null context destruction failed");

  if (failures != 0) {
    return 1;
  }
  (void)printf(
      "abi_c_smoke: PASS (ABI %u, engine %.*s)\n",
      version.engine_abi_version,
      (int)version.version_string.size,
      version.version_string.data);
  return 0;
}
