/* SPDX-FileCopyrightText: 2026 Olivier Ami */
/* SPDX-License-Identifier: Apache-2.0 OR MIT */

#include "morphoia/engine.h"

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

_Static_assert(
    offsetof(morphoia_capability_info_t, abi_version) == sizeof(uint32_t),
    "capability ABI prefix changed");
_Static_assert(
    offsetof(morphoia_canonical_json_options_t, abi_version) == sizeof(uint32_t),
    "canonical options ABI prefix changed");
_Static_assert(
    MORPHOIA_SHA256_DIGEST_SIZE == 32U,
    "SHA-256 output size changed");

static int require_true(const int condition, const char* const message) {
  if (condition != 0) {
    return 0;
  }
  (void)fprintf(stderr, "canonical_json_c_api_test: %s\n", message);
  return 1;
}

static morphoia_string_view_t view_of(const char* const value) {
  morphoia_string_view_t view;
  view.data = value;
  view.size = strlen(value);
  return view;
}

static int view_equals(const morphoia_string_view_t view, const char* const expected) {
  const size_t expected_size = strlen(expected);
  return view.data != NULL && view.size == expected_size &&
         memcmp(view.data, expected, expected_size) == 0;
}

static int bytes_are(const uint8_t* const value, const uint8_t expected, const size_t size) {
  size_t index = 0U;
  for (; index < size; ++index) {
    if (value[index] != expected) {
      return 0;
    }
  }
  return 1;
}

static int diagnostic_is_structured(
    const morphoia_diagnostic_t* const diagnostic,
    const morphoia_status_t status) {
  return diagnostic->status == status &&
         diagnostic->severity == MORPHOIA_DIAGNOSTIC_ERROR &&
         diagnostic->message_length != 0U && diagnostic->context_length != 0U &&
         diagnostic->cause_length != 0U &&
         diagnostic->affected_elements_length != 0U &&
         diagnostic->recommendation_length != 0U;
}

int main(void) {
  static const uint8_t expected_digest[MORPHOIA_SHA256_DIGEST_SIZE] = {
      0x43U, 0x25U, 0x8cU, 0xffU, 0x78U, 0x3fU, 0xe7U, 0x03U,
      0x6dU, 0x8aU, 0x43U, 0x03U, 0x3fU, 0x83U, 0x0aU, 0xdfU,
      0xc6U, 0x0eU, 0xc0U, 0x37U, 0x38U, 0x24U, 0x73U, 0x54U,
      0x8aU, 0xc7U, 0x42U, 0xb8U, 0x88U, 0x29U, 0x27U, 0x77U,
  };
  const char* const input = "{\"b\":2,\"a\":1}";
  const char* const canonical = "{\"a\":1,\"b\":2}";
  morphoia_diagnostic_t diagnostic = {0};
  morphoia_context_t* context = NULL;
  morphoia_capability_info_t capability = {0};
  morphoia_canonical_json_options_t options = {0};
  uint8_t digest[MORPHOIA_SHA256_DIGEST_SIZE];
  char output[64];
  size_t required_size = 0U;
  int failures = 0;
  union query_alias_storage {
    morphoia_capability_info_t info;
    morphoia_diagnostic_t diagnostic;
  } query_alias;
  struct capability_future_storage {
    morphoia_capability_info_t info;
    uint64_t future_field;
  } capability_future;
  union canonical_alias_storage {
    morphoia_diagnostic_t diagnostic;
    unsigned char bytes[sizeof(morphoia_diagnostic_t)];
  } canonical_alias;
  unsigned char alias_snapshot[sizeof(canonical_alias)];

  diagnostic.struct_size = (uint32_t)sizeof(diagnostic);
  diagnostic.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  failures += require_true(
      morphoia_context_create(NULL, &context, &diagnostic) == MORPHOIA_STATUS_OK,
      "context creation failed");

  capability.struct_size = (uint32_t)sizeof(capability);
  capability.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  failures += require_true(
      morphoia_context_query_capability(
          context,
          view_of(MORPHOIA_CAPABILITY_ENGINE_IR_MANIFEST),
          &capability,
          &diagnostic) == MORPHOIA_STATUS_OK,
      "known capability query failed");
  failures += require_true(capability.supported == 1U, "known capability is unsupported");
  failures += require_true(
      view_equals(capability.format_identifier, "morphoia.engine.ir-manifest"),
      "format identifier mismatch");
  failures += require_true(
      view_equals(capability.format_version, MORPHOIA_ENGINE_IR_FORMAT_VERSION),
      "format version mismatch");
  failures += require_true(
      view_equals(capability.media_type, MORPHOIA_ENGINE_IR_MEDIA_TYPE),
      "media type mismatch");
  failures += require_true(
      view_equals(capability.canonical_profile, MORPHOIA_CANONICAL_JSON_PROFILE1),
      "canonical profile mismatch");
  failures += require_true(
      capability.maximum_input_bytes ==
          MORPHOIA_CANONICAL_JSON_DEFAULT_MAXIMUM_INPUT_BYTES,
      "default input limit mismatch");
  failures += require_true(
      capability.extension_keys.size == 0U,
      "capability unexpectedly announced a specific extension key");

  memset(&capability_future, 0x4b, sizeof(capability_future));
  capability_future.info.struct_size = (uint32_t)sizeof(capability_future);
  capability_future.info.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  capability_future.future_field = UINT64_C(0x1122334455667788);
  failures += require_true(
      morphoia_context_query_capability(
          context,
          view_of(MORPHOIA_CAPABILITY_ENGINE_IR_MANIFEST),
          &capability_future.info,
          &diagnostic) == MORPHOIA_STATUS_OK,
      "future-sized capability query failed");
  failures += require_true(
      capability_future.info.supported == 1U &&
          capability_future.future_field == UINT64_C(0x1122334455667788),
      "capability query wrote beyond its ABI-v1 prefix");

  capability.struct_size = 1U;
  capability.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  capability.supported = 0xabcdef03U;
  failures += require_true(
      morphoia_context_query_capability(
          context,
          view_of(MORPHOIA_CAPABILITY_ENGINE_IR_MANIFEST),
          &capability,
          &diagnostic) == MORPHOIA_STATUS_STRUCT_TOO_SMALL,
      "undersized capability output was not rejected");
  failures += require_true(
      capability.supported == 0xabcdef03U,
      "undersized capability query changed output storage");
  failures += require_true(
      diagnostic_is_structured(&diagnostic, MORPHOIA_STATUS_STRUCT_TOO_SMALL),
      "undersized capability diagnostic was incomplete");

  capability.struct_size = (uint32_t)sizeof(capability);
  capability.abi_version = MORPHOIA_ENGINE_ABI_VERSION + 1U;
  capability.supported = 0xabcdef04U;
  failures += require_true(
      morphoia_context_query_capability(
          context,
          view_of(MORPHOIA_CAPABILITY_ENGINE_IR_MANIFEST),
          &capability,
          &diagnostic) == MORPHOIA_STATUS_UNSUPPORTED_ABI,
      "unsupported capability ABI was not rejected");
  failures += require_true(
      capability.supported == 0xabcdef04U,
      "unsupported capability ABI changed output storage");
  failures += require_true(
      diagnostic_is_structured(&diagnostic, MORPHOIA_STATUS_UNSUPPORTED_ABI),
      "unsupported capability ABI diagnostic was incomplete");

  capability.struct_size = (uint32_t)sizeof(capability);
  capability.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  failures += require_true(
      morphoia_context_query_capability(
          context, view_of("org.example.unknown"), &capability, &diagnostic) ==
          MORPHOIA_STATUS_OK,
      "unknown capability query failed");
  failures += require_true(capability.supported == 0U, "unknown capability was supported");

  capability.struct_size = (uint32_t)sizeof(capability);
  capability.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  capability.supported = 0xabcdef01U;
  {
    const char malformed_utf8[] = {(char)0xc0, (char)0x80};
    const morphoia_string_view_t malformed_view = {
        malformed_utf8,
        sizeof(malformed_utf8),
    };
    failures += require_true(
        morphoia_context_query_capability(
            context, malformed_view, &capability, &diagnostic) ==
            MORPHOIA_STATUS_INVALID_ARGUMENT,
        "malformed UTF-8 capability was not rejected");
  }
  failures += require_true(
      capability.supported == 0xabcdef01U,
      "malformed capability changed capability output");
  failures += require_true(
      diagnostic_is_structured(&diagnostic, MORPHOIA_STATUS_INVALID_ARGUMENT),
      "malformed capability diagnostic was incomplete");

  capability.struct_size = (uint32_t)sizeof(capability);
  capability.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  capability.supported = 0xabcdef02U;
  {
    const char embedded_nul[] = {'a', '\0', 'b'};
    const morphoia_string_view_t nul_view = {embedded_nul, sizeof(embedded_nul)};
    failures += require_true(
        morphoia_context_query_capability(context, nul_view, &capability, &diagnostic) ==
            MORPHOIA_STATUS_INVALID_ARGUMENT,
        "embedded-NUL capability was not rejected");
  }
  failures += require_true(
      capability.supported == 0xabcdef02U,
      "embedded-NUL capability changed capability output");

  memset(&query_alias, 0x5c, sizeof(query_alias));
  query_alias.info.struct_size = (uint32_t)sizeof(query_alias.info);
  query_alias.info.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  failures += require_true(
      morphoia_context_query_capability(
          context,
          view_of(MORPHOIA_CAPABILITY_ENGINE_IR_MANIFEST),
          &query_alias.info,
          &query_alias.diagnostic) == MORPHOIA_STATUS_INVALID_ARGUMENT,
      "overlapping capability info and diagnostic were not rejected");
  failures += require_true(
      query_alias.info.supported == 0x5c5c5c5cU,
      "info-diagnostic overlap changed caller storage");

  memset(digest, 0xaa, sizeof(digest));
  required_size = 777U;
  failures += require_true(
      morphoia_canonical_json_profile1(
          context,
          view_of(input),
          NULL,
          NULL,
          0U,
          &required_size,
          digest,
          &diagnostic) == MORPHOIA_STATUS_BUFFER_TOO_SMALL,
      "measurement call did not request a buffer");
  failures += require_true(
      required_size == strlen(canonical), "measurement returned wrong size");
  failures += require_true(
      memcmp(digest, expected_digest, sizeof(digest)) == 0,
      "measurement returned wrong digest");
  failures += require_true(
      diagnostic_is_structured(&diagnostic, MORPHOIA_STATUS_BUFFER_TOO_SMALL),
      "measurement diagnostic was incomplete");

  memset(output, 0x5a, sizeof(output));
  failures += require_true(
      morphoia_canonical_json_profile1(
          context,
          view_of(input),
          NULL,
          output,
          required_size - 1U,
          &required_size,
          digest,
          &diagnostic) == MORPHOIA_STATUS_BUFFER_TOO_SMALL,
      "short output did not fail closed");
  failures += require_true(
      (unsigned char)output[0] == 0x5aU,
      "short output was partially written");

  failures += require_true(
      morphoia_canonical_json_profile1(
          context,
          view_of(input),
          NULL,
          output,
          sizeof(output),
          &required_size,
          digest,
          &diagnostic) == MORPHOIA_STATUS_OK,
      "canonicalization failed");
  failures += require_true(
      required_size == strlen(canonical) && memcmp(output, canonical, required_size) == 0,
      "canonical output mismatch");
  failures += require_true(
      memcmp(digest, expected_digest, sizeof(digest)) == 0,
      "canonical output digest mismatch");

  memset(output, 0x31, sizeof(output));
  memset(digest, 0xaa, sizeof(digest));
  required_size = 777U;
  failures += require_true(
      morphoia_canonical_json_profile1(
          context,
          view_of("{\"a\":1,\"a\":2}"),
          NULL,
          output,
          sizeof(output),
          &required_size,
          digest,
          &diagnostic) == MORPHOIA_STATUS_INVALID_JSON,
      "duplicate decoded key was not invalid JSON");
  failures += require_true(required_size == 777U, "invalid JSON changed required size");
  failures += require_true(
      bytes_are(digest, 0xaaU, sizeof(digest)), "invalid JSON changed digest output");
  failures += require_true(
      (unsigned char)output[0] == 0x31U, "invalid JSON changed canonical output");
  failures += require_true(
      diagnostic_is_structured(&diagnostic, MORPHOIA_STATUS_INVALID_JSON),
      "invalid JSON diagnostic was incomplete");

  memset(output, 0x32, sizeof(output));
  memset(digest, 0xaa, sizeof(digest));
  required_size = 777U;
  {
    const char malformed_utf8[] = {'"', (char)0xc0, (char)0x80, '"'};
    const morphoia_string_view_t malformed_view = {
        malformed_utf8,
        sizeof(malformed_utf8),
    };
    failures += require_true(
        morphoia_canonical_json_profile1(
            context,
            malformed_view,
            NULL,
            output,
            sizeof(output),
            &required_size,
            digest,
            &diagnostic) == MORPHOIA_STATUS_INVALID_JSON,
        "malformed UTF-8 JSON was not rejected");
  }
  failures += require_true(
      required_size == 777U && bytes_are(digest, 0xaaU, sizeof(digest)) &&
          (unsigned char)output[0] == 0x32U,
      "malformed UTF-8 changed an output");

  options.struct_size = (uint32_t)sizeof(options);
  options.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  options.flags = MORPHOIA_CANONICAL_JSON_FLAG_NONE;
  options.maximum_input_bytes = 2U;
  options.maximum_string_bytes = 2U;
  options.maximum_values = 2U;
  options.maximum_depth = 2U;
  failures += require_true(
      morphoia_canonical_json_profile1(
          context,
          view_of(input),
          &options,
          output,
          sizeof(output),
          &required_size,
          digest,
          &diagnostic) == MORPHOIA_STATUS_RESOURCE_LIMIT,
      "bounded input did not report a resource limit");
  failures += require_true(
      diagnostic_is_structured(&diagnostic, MORPHOIA_STATUS_RESOURCE_LIMIT),
      "resource limit diagnostic was incomplete");

  options.maximum_input_bytes = MORPHOIA_CANONICAL_JSON_DEFAULT_MAXIMUM_INPUT_BYTES;
  options.maximum_string_bytes = MORPHOIA_CANONICAL_JSON_DEFAULT_MAXIMUM_STRING_BYTES;
  options.maximum_values = MORPHOIA_CANONICAL_JSON_DEFAULT_MAXIMUM_VALUES;
  options.maximum_depth = MORPHOIA_CANONICAL_JSON_DEFAULT_MAXIMUM_DEPTH;
  options.flags = UINT64_C(1);
  memset(output, 0x33, sizeof(output));
  memset(digest, 0xaa, sizeof(digest));
  required_size = 777U;
  failures += require_true(
      morphoia_canonical_json_profile1(
          context,
          view_of(input),
          &options,
          output,
          sizeof(output),
          &required_size,
          digest,
          &diagnostic) == MORPHOIA_STATUS_UNSUPPORTED_OPTION,
      "unsupported canonical flag was not rejected");
  failures += require_true(
      required_size == 777U && bytes_are(digest, 0xaaU, sizeof(digest)) &&
          (unsigned char)output[0] == 0x33U,
      "unsupported flag changed an output");
  failures += require_true(
      diagnostic_is_structured(&diagnostic, MORPHOIA_STATUS_UNSUPPORTED_OPTION),
      "unsupported flag diagnostic was incomplete");

  options.flags = 0U;
  options.struct_size = 1U;
  failures += require_true(
      morphoia_canonical_json_profile1(
          context,
          view_of(input),
          &options,
          output,
          sizeof(output),
          &required_size,
          digest,
          &diagnostic) == MORPHOIA_STATUS_STRUCT_TOO_SMALL,
      "undersized canonical options were not rejected");
  failures += require_true(
      required_size == 777U && bytes_are(digest, 0xaaU, sizeof(digest)) &&
          (unsigned char)output[0] == 0x33U,
      "undersized options changed an output");
  failures += require_true(
      diagnostic_is_structured(&diagnostic, MORPHOIA_STATUS_STRUCT_TOO_SMALL),
      "undersized options diagnostic was incomplete");

  options.struct_size = (uint32_t)sizeof(options);
  options.abi_version = MORPHOIA_ENGINE_ABI_VERSION + 1U;
  failures += require_true(
      morphoia_canonical_json_profile1(
          context,
          view_of(input),
          &options,
          output,
          sizeof(output),
          &required_size,
          digest,
          &diagnostic) == MORPHOIA_STATUS_UNSUPPORTED_ABI,
      "unsupported canonical options ABI was not rejected");
  failures += require_true(
      required_size == 777U && bytes_are(digest, 0xaaU, sizeof(digest)) &&
          (unsigned char)output[0] == 0x33U,
      "unsupported options ABI changed an output");
  failures += require_true(
      diagnostic_is_structured(&diagnostic, MORPHOIA_STATUS_UNSUPPORTED_ABI),
      "unsupported options ABI diagnostic was incomplete");

  options.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  options.maximum_input_bytes = 0U;
  failures += require_true(
      morphoia_canonical_json_profile1(
          context,
          view_of(input),
          &options,
          output,
          sizeof(output),
          &required_size,
          digest,
          &diagnostic) == MORPHOIA_STATUS_RESOURCE_LIMIT,
      "zero canonical limit was not rejected");
  failures += require_true(
      required_size == 777U && bytes_are(digest, 0xaaU, sizeof(digest)) &&
          (unsigned char)output[0] == 0x33U,
      "zero limit changed an output");

  failures += require_true(
      morphoia_canonical_json_profile1(
          NULL,
          view_of(input),
          NULL,
          output,
          sizeof(output),
          &required_size,
          digest,
          &diagnostic) == MORPHOIA_STATUS_INVALID_ARGUMENT,
      "null context was not rejected");
  failures += require_true(
      required_size == 777U && bytes_are(digest, 0xaaU, sizeof(digest)) &&
          (unsigned char)output[0] == 0x33U,
      "null context changed an output");
  failures += require_true(
      diagnostic_is_structured(&diagnostic, MORPHOIA_STATUS_INVALID_ARGUMENT),
      "null context diagnostic was incomplete");

  required_size = 777U;
  memset(digest, 0xaa, sizeof(digest));
  failures += require_true(
      morphoia_canonical_json_profile1(
          context,
          view_of(input),
          NULL,
          (char*)digest,
          sizeof(digest),
          &required_size,
          digest,
          &diagnostic) == MORPHOIA_STATUS_INVALID_ARGUMENT,
      "overlapping output and digest were not rejected");
  failures += require_true(required_size == 777U, "overlap changed required size");
  failures += require_true(
      bytes_are(digest, 0xaaU, sizeof(digest)), "overlap changed digest storage");
  failures += require_true(
      diagnostic_is_structured(&diagnostic, MORPHOIA_STATUS_INVALID_ARGUMENT),
      "output-digest overlap diagnostic was incomplete");

  memset(&canonical_alias, 0x6d, sizeof(canonical_alias));
  canonical_alias.diagnostic.struct_size = (uint32_t)sizeof(canonical_alias.diagnostic);
  canonical_alias.diagnostic.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  memcpy(alias_snapshot, canonical_alias.bytes, sizeof(alias_snapshot));
  failures += require_true(
      morphoia_canonical_json_profile1(
          context,
          view_of(input),
          NULL,
          (char*)canonical_alias.bytes,
          sizeof(canonical_alias.bytes),
          &required_size,
          digest,
          &canonical_alias.diagnostic) == MORPHOIA_STATUS_INVALID_ARGUMENT,
      "overlapping diagnostic and output were not rejected");
  failures += require_true(
      memcmp(alias_snapshot, canonical_alias.bytes, sizeof(alias_snapshot)) == 0,
      "diagnostic-output overlap changed caller storage");

  failures += require_true(
      morphoia_context_destroy(&context, &diagnostic) == MORPHOIA_STATUS_OK,
      "context destruction failed");
  if (failures != 0) {
    return 1;
  }
  (void)printf("canonical_json_c_api_test: PASS (capability, limits, no partial output)\n");
  return 0;
}
