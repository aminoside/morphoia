/* SPDX-FileCopyrightText: 2026 Olivier Ami */
/* SPDX-License-Identifier: Apache-2.0 OR MIT */

#include "morphoia/engine.h"

#include <limits.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

_Static_assert(
    offsetof(morphoia_engine_ir_unit_t, abi_version) == sizeof(uint32_t),
    "unit ABI prefix changed");
_Static_assert(
    offsetof(morphoia_engine_ir_unit_validation_t, abi_version) == sizeof(uint32_t),
    "unit validation ABI prefix changed");
_Static_assert(
    sizeof(((morphoia_engine_ir_unit_t*)0)->dimensions) / sizeof(int32_t) == 7U,
    "unit dimension count changed");
_Static_assert(
    sizeof(((morphoia_engine_ir_unit_t*)0)->si_factor_coefficient) == sizeof(int64_t),
    "SI coefficient must remain 64-bit");

struct expected_unit {
  const char* code;
  int32_t dimensions[7];
  int64_t coefficient;
  int32_t scale;
};

static const struct expected_unit expected_units[] = {
    {"1", {0, 0, 0, 0, 0, 0, 0}, INT64_C(1), 0},
    {"m", {1, 0, 0, 0, 0, 0, 0}, INT64_C(1), 0},
    {"mm", {1, 0, 0, 0, 0, 0, 0}, INT64_C(1), -3},
    {"s", {0, 0, 1, 0, 0, 0, 0}, INT64_C(1), 0},
    {"kg", {0, 1, 0, 0, 0, 0, 0}, INT64_C(1), 0},
    {"g", {0, 1, 0, 0, 0, 0, 0}, INT64_C(1), -3},
    {"A", {0, 0, 0, 1, 0, 0, 0}, INT64_C(1), 0},
    {"K", {0, 0, 0, 0, 1, 0, 0}, INT64_C(1), 0},
    {"mol", {0, 0, 0, 0, 0, 1, 0}, INT64_C(1), 0},
    {"cd", {0, 0, 0, 0, 0, 0, 1}, INT64_C(1), 0},
};

static int require_true(const int condition, const char* const message) {
  if (condition != 0) {
    return 0;
  }
  (void)fprintf(stderr, "unit_validation_c_api_test: %s\n", message);
  return 1;
}

static morphoia_string_view_t bytes_view(const char* const data, const size_t size) {
  morphoia_string_view_t result;
  result.data = data;
  result.size = size;
  return result;
}

static morphoia_string_view_t text_view(const char* const text) {
  return bytes_view(text, strlen(text));
}

static int view_equals(const morphoia_string_view_t view, const char* const text) {
  const size_t size = strlen(text);
  return view.data != NULL && view.size == size && memcmp(view.data, text, size) == 0;
}

static void init_diagnostic(morphoia_diagnostic_t* const diagnostic) {
  memset(diagnostic, 0, sizeof(*diagnostic));
  diagnostic->struct_size = (uint32_t)sizeof(*diagnostic);
  diagnostic->abi_version = MORPHOIA_ENGINE_ABI_VERSION;
}

static void init_unit(
    morphoia_engine_ir_unit_t* const unit,
    const morphoia_string_view_t code,
    const int32_t dimensions[7],
    const int64_t coefficient,
    const int32_t scale) {
  memset(unit, 0, sizeof(*unit));
  unit->struct_size = (uint32_t)sizeof(*unit);
  unit->abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  unit->code = code;
  memcpy(unit->dimensions, dimensions, sizeof(unit->dimensions));
  unit->si_factor_coefficient = coefficient;
  unit->si_factor_scale = scale;
}

static void init_validation(morphoia_engine_ir_unit_validation_t* const validation) {
  memset(validation, 0, sizeof(*validation));
  validation->struct_size = (uint32_t)sizeof(*validation);
  validation->abi_version = MORPHOIA_ENGINE_ABI_VERSION;
}

static int validation_equals_expected(
    const morphoia_engine_ir_unit_validation_t* const validation,
    const struct expected_unit* const expected) {
  return validation->struct_size == MORPHOIA_ENGINE_IR_UNIT_VALIDATION_V1_SIZE &&
         validation->abi_version == MORPHOIA_ENGINE_ABI_VERSION &&
         validation->flags == MORPHOIA_ENGINE_IR_UNIT_VALIDATION_FLAG_NONE &&
         validation->recognized == 1U && validation->dimensions_match == 1U &&
         validation->si_factor_match == 1U && validation->qualified == 1U &&
         memcmp(
             validation->expected_dimensions,
             expected->dimensions,
             sizeof(validation->expected_dimensions)) == 0 &&
         validation->expected_si_factor_coefficient == expected->coefficient &&
         validation->expected_si_factor_scale == expected->scale &&
         validation->reserved == 0U;
}

static int diagnostic_is_error(
    const morphoia_diagnostic_t* const diagnostic,
    const morphoia_status_t status) {
  return diagnostic->status == status &&
         diagnostic->severity == MORPHOIA_DIAGNOSTIC_ERROR &&
         diagnostic->message_length != 0U && diagnostic->context_length != 0U &&
         diagnostic->cause_length != 0U &&
         diagnostic->affected_elements_length != 0U &&
         diagnostic->recommendation_length != 0U;
}

static int bytes_unchanged(
    const void* const value,
    const unsigned char* const snapshot,
    const size_t size) {
  return memcmp(value, snapshot, size) == 0;
}

static int expect_atomic_error(
    const morphoia_status_t actual,
    const morphoia_status_t expected,
    const morphoia_engine_ir_unit_validation_t* const validation,
    const unsigned char snapshot[sizeof(morphoia_engine_ir_unit_validation_t)],
    const morphoia_diagnostic_t* const diagnostic,
    const char* const message) {
  int failures = 0;
  failures += require_true(actual == expected, message);
  failures += require_true(
      bytes_unchanged(validation, snapshot, sizeof(*validation)),
      "technical error changed validation output");
  failures += require_true(
      diagnostic_is_error(diagnostic, expected),
      "technical error diagnostic was incomplete");
  return failures;
}

int main(void) {
  static const int32_t zero_dimensions[7] = {0, 0, 0, 0, 0, 0, 0};
  morphoia_context_t* context = NULL;
  morphoia_diagnostic_t diagnostic;
  morphoia_engine_ir_unit_t unit;
  morphoia_engine_ir_unit_validation_t validation;
  unsigned char snapshot[sizeof(validation)];
  int failures = 0;
  size_t index = 0U;

  init_diagnostic(&diagnostic);
  failures += require_true(
      morphoia_context_create(NULL, &context, &diagnostic) == MORPHOIA_STATUS_OK,
      "context creation failed");

  {
    morphoia_capability_info_t capability;
    memset(&capability, 0, sizeof(capability));
    capability.struct_size = (uint32_t)sizeof(capability);
    capability.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
    failures += require_true(
        morphoia_context_query_capability(
            context,
            text_view(MORPHOIA_CAPABILITY_ENGINE_IR_CORE_SI),
            &capability,
            &diagnostic) == MORPHOIA_STATUS_OK,
        "unit capability query failed");
    failures += require_true(
        capability.supported == 1U &&
            view_equals(capability.capability_name, MORPHOIA_ENGINE_IR_CORE_SI_PROFILE) &&
            view_equals(capability.format_identifier, "morphoia.engine.ir-inspection") &&
            view_equals(capability.format_version, "0.1.0") &&
            view_equals(
                capability.media_type,
                "application/vnd.morphoia.ir-inspection.v0+json") &&
            view_equals(capability.canonical_profile, MORPHOIA_CANONICAL_JSON_PROFILE1) &&
            capability.extension_keys.size == 0U &&
            capability.maximum_input_bytes == 0U &&
            capability.maximum_string_bytes == 0U && capability.maximum_values == 0U &&
            capability.maximum_depth == 0U,
        "unit capability metadata mismatch");
  }

  for (index = 0U; index < sizeof(expected_units) / sizeof(expected_units[0]); ++index) {
    const struct expected_unit* const expected = &expected_units[index];
    init_unit(
        &unit,
        text_view(expected->code),
        expected->dimensions,
        expected->coefficient,
        expected->scale);
    init_validation(&validation);
    init_diagnostic(&diagnostic);
    failures += require_true(
        morphoia_context_validate_engine_ir_unit(
            context, &unit, &validation, &diagnostic) == MORPHOIA_STATUS_OK,
        "published literal call failed");
    failures += require_true(
        validation_equals_expected(&validation, expected),
        "published literal did not return the exact registry tuple");
    failures += require_true(
        diagnostic.status == MORPHOIA_STATUS_OK &&
            diagnostic.severity == MORPHOIA_DIAGNOSTIC_NONE,
        "qualified literal returned an error diagnostic");
  }

  init_unit(
      &unit,
      text_view("mm"),
      expected_units[2].dimensions,
      expected_units[2].coefficient,
      expected_units[2].scale);
  unit.dimensions[0] = 2;
  init_validation(&validation);
  failures += require_true(
      morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic) ==
              MORPHOIA_STATUS_OK &&
          validation.recognized == 1U && validation.dimensions_match == 0U &&
          validation.si_factor_match == 1U && validation.qualified == 0U &&
          validation.expected_dimensions[0] == 1,
      "dimension mismatch verdict is wrong");

  unit.dimensions[0] = 1;
  unit.si_factor_coefficient = 2;
  init_validation(&validation);
  failures += require_true(
      morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic) ==
              MORPHOIA_STATUS_OK &&
          validation.recognized == 1U && validation.dimensions_match == 1U &&
          validation.si_factor_match == 0U && validation.qualified == 0U &&
          validation.expected_si_factor_coefficient == 1 &&
          validation.expected_si_factor_scale == -3,
      "coefficient-only mismatch was not rejected exactly");

  unit.si_factor_coefficient = 1;
  unit.si_factor_scale = -2;
  init_validation(&validation);
  failures += require_true(
      morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic) ==
              MORPHOIA_STATUS_OK &&
          validation.recognized == 1U && validation.dimensions_match == 1U &&
          validation.si_factor_match == 0U && validation.qualified == 0U &&
          validation.expected_si_factor_coefficient == 1 &&
          validation.expected_si_factor_scale == -3,
      "scale-only mismatch was not rejected exactly");

  unit.si_factor_coefficient = INT64_MIN;
  unit.si_factor_scale = INT32_MAX;
  unit.dimensions[0] = INT32_MIN;
  init_validation(&validation);
  failures += require_true(
      morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic) ==
              MORPHOIA_STATUS_OK &&
          validation.recognized == 1U && validation.dimensions_match == 0U &&
          validation.si_factor_match == 0U && validation.qualified == 0U,
      "integer boundary tuple did not produce a bounded mismatch verdict");

  {
    static const char* const unknown_codes[] = {"cm", "MM", "m/s", "\xc2\xb5m"};
    for (index = 0U; index < sizeof(unknown_codes) / sizeof(unknown_codes[0]); ++index) {
      init_unit(&unit, text_view(unknown_codes[index]), zero_dimensions, 99, 99);
      init_validation(&validation);
      init_diagnostic(&diagnostic);
      failures += require_true(
          morphoia_context_validate_engine_ir_unit(
              context, &unit, &validation, &diagnostic) == MORPHOIA_STATUS_OK,
          "well-formed unknown code call failed");
      failures += require_true(
          validation.recognized == 0U && validation.dimensions_match == 0U &&
              validation.si_factor_match == 0U && validation.qualified == 0U &&
              memcmp(
                  validation.expected_dimensions,
                  zero_dimensions,
                  sizeof(zero_dimensions)) == 0 &&
              validation.expected_si_factor_coefficient == 0 &&
              validation.expected_si_factor_scale == 0 && validation.reserved == 0U,
          "unknown code did not return an all-zero semantic verdict");
      failures += require_true(
          diagnostic.status == MORPHOIA_STATUS_OK &&
              diagnostic.severity == MORPHOIA_DIAGNOSTIC_NONE,
          "unknown code returned an error diagnostic");
    }
  }

  {
    char boundary[33];
    memset(boundary, 'x', sizeof(boundary));
    init_unit(&unit, bytes_view(boundary, 32U), zero_dimensions, 1, 0);
    init_validation(&validation);
    failures += require_true(
        morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic) ==
                MORPHOIA_STATUS_OK &&
            validation.recognized == 0U,
        "exactly 32-byte code was not accepted lexically");

    unit.code = bytes_view(boundary, 33U);
    init_validation(&validation);
    memcpy(snapshot, &validation, sizeof(validation));
    init_diagnostic(&diagnostic);
    failures += expect_atomic_error(
        morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic),
        MORPHOIA_STATUS_INVALID_ARGUMENT,
        &validation,
        snapshot,
        &diagnostic,
        "33-byte code was not rejected");
  }

  {
    static const char malformed[] = {(char)0xc0, (char)0x80};
    static const char embedded_nul[] = {'m', '\0', 'm'};
    const morphoia_string_view_t invalid_codes[] = {
        {"", 0U},
        {NULL, 1U},
        {malformed, sizeof(malformed)},
        {embedded_nul, sizeof(embedded_nul)},
    };
    for (index = 0U; index < sizeof(invalid_codes) / sizeof(invalid_codes[0]); ++index) {
      init_unit(&unit, invalid_codes[index], zero_dimensions, 1, 0);
      init_validation(&validation);
      memcpy(snapshot, &validation, sizeof(validation));
      init_diagnostic(&diagnostic);
      failures += expect_atomic_error(
          morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic),
          MORPHOIA_STATUS_INVALID_ARGUMENT,
          &validation,
          snapshot,
          &diagnostic,
          "invalid code was not rejected");
    }
  }

  init_unit(&unit, text_view("m"), expected_units[1].dimensions, 1, 0);
  init_validation(&validation);
  unit.struct_size = MORPHOIA_ENGINE_IR_UNIT_V1_SIZE - 1U;
  memcpy(snapshot, &validation, sizeof(validation));
  init_diagnostic(&diagnostic);
  failures += expect_atomic_error(
      morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic),
      MORPHOIA_STATUS_STRUCT_TOO_SMALL,
      &validation,
      snapshot,
      &diagnostic,
      "small input structure was not rejected");

  unit.struct_size = (uint32_t)sizeof(unit);
  unit.abi_version += 1U;
  memcpy(snapshot, &validation, sizeof(validation));
  init_diagnostic(&diagnostic);
  failures += expect_atomic_error(
      morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic),
      MORPHOIA_STATUS_UNSUPPORTED_ABI,
      &validation,
      snapshot,
      &diagnostic,
      "future input ABI was not rejected");

  unit.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  unit.flags = UINT64_C(1);
  memcpy(snapshot, &validation, sizeof(validation));
  init_diagnostic(&diagnostic);
  failures += expect_atomic_error(
      morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic),
      MORPHOIA_STATUS_UNSUPPORTED_OPTION,
      &validation,
      snapshot,
      &diagnostic,
      "input flag was not rejected");

  unit.flags = 0U;
  unit.reserved = 1U;
  memcpy(snapshot, &validation, sizeof(validation));
  init_diagnostic(&diagnostic);
  failures += expect_atomic_error(
      morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic),
      MORPHOIA_STATUS_INVALID_ARGUMENT,
      &validation,
      snapshot,
      &diagnostic,
      "input reserved field was not rejected");

  unit.reserved = 0U;
  validation.struct_size = MORPHOIA_ENGINE_IR_UNIT_VALIDATION_V1_SIZE - 1U;
  memcpy(snapshot, &validation, sizeof(validation));
  init_diagnostic(&diagnostic);
  failures += expect_atomic_error(
      morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic),
      MORPHOIA_STATUS_STRUCT_TOO_SMALL,
      &validation,
      snapshot,
      &diagnostic,
      "small validation structure was not rejected");

  init_validation(&validation);
  validation.abi_version += 1U;
  memcpy(snapshot, &validation, sizeof(validation));
  init_diagnostic(&diagnostic);
  failures += expect_atomic_error(
      morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic),
      MORPHOIA_STATUS_UNSUPPORTED_ABI,
      &validation,
      snapshot,
      &diagnostic,
      "future validation ABI was not rejected");

  validation.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  validation.flags = UINT64_C(1);
  memcpy(snapshot, &validation, sizeof(validation));
  init_diagnostic(&diagnostic);
  failures += expect_atomic_error(
      morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic),
      MORPHOIA_STATUS_UNSUPPORTED_OPTION,
      &validation,
      snapshot,
      &diagnostic,
      "validation flag was not rejected");

  validation.flags = 0U;
  validation.reserved = 1U;
  memcpy(snapshot, &validation, sizeof(validation));
  init_diagnostic(&diagnostic);
  failures += expect_atomic_error(
      morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic),
      MORPHOIA_STATUS_INVALID_ARGUMENT,
      &validation,
      snapshot,
      &diagnostic,
      "validation reserved field was not rejected");

  {
    struct unit_future {
      morphoia_engine_ir_unit_t unit;
      uint64_t canary;
    } future_unit;
    struct validation_future {
      morphoia_engine_ir_unit_validation_t validation;
      uint64_t canary;
    } future_validation;
    init_unit(
        &future_unit.unit,
        text_view("kg"),
        expected_units[4].dimensions,
        expected_units[4].coefficient,
        expected_units[4].scale);
    future_unit.unit.struct_size = (uint32_t)sizeof(future_unit);
    future_unit.canary = UINT64_C(0x1122334455667788);
    init_validation(&future_validation.validation);
    future_validation.validation.struct_size = (uint32_t)sizeof(future_validation);
    future_validation.canary = UINT64_C(0x8877665544332211);
    failures += require_true(
        morphoia_context_validate_engine_ir_unit(
            context,
            &future_unit.unit,
            &future_validation.validation,
            &diagnostic) == MORPHOIA_STATUS_OK &&
            future_unit.canary == UINT64_C(0x1122334455667788) &&
            future_validation.canary == UINT64_C(0x8877665544332211) &&
            validation_equals_expected(&future_validation.validation, &expected_units[4]),
        "future-sized structures changed canaries or failed");
  }

  init_unit(&unit, text_view("m"), expected_units[1].dimensions, 1, 0);
  init_validation(&validation);
  memcpy(snapshot, &validation, sizeof(validation));
  init_diagnostic(&diagnostic);
  failures += expect_atomic_error(
      morphoia_context_validate_engine_ir_unit(NULL, &unit, &validation, &diagnostic),
      MORPHOIA_STATUS_INVALID_ARGUMENT,
      &validation,
      snapshot,
      &diagnostic,
      "null context was not rejected");

  init_validation(&validation);
  memcpy(snapshot, &validation, sizeof(validation));
  init_diagnostic(&diagnostic);
  failures += expect_atomic_error(
      morphoia_context_validate_engine_ir_unit(context, NULL, &validation, &diagnostic),
      MORPHOIA_STATUS_INVALID_ARGUMENT,
      &validation,
      snapshot,
      &diagnostic,
      "null unit was not rejected");

  failures += require_true(
      morphoia_context_validate_engine_ir_unit(context, &unit, NULL, &diagnostic) ==
          MORPHOIA_STATUS_INVALID_ARGUMENT,
      "null validation was not rejected");

  {
    union unit_validation_alias {
      morphoia_engine_ir_unit_t unit;
      morphoia_engine_ir_unit_validation_t validation;
      unsigned char bytes[sizeof(morphoia_engine_ir_unit_t)];
    } alias;
    unsigned char alias_snapshot[sizeof(alias)];
    memset(&alias, 0x5a, sizeof(alias));
    memcpy(alias_snapshot, &alias, sizeof(alias));
    init_diagnostic(&diagnostic);
    failures += require_true(
        morphoia_context_validate_engine_ir_unit(
            context, &alias.unit, &alias.validation, &diagnostic) ==
            MORPHOIA_STATUS_INVALID_ARGUMENT,
        "unit-validation alias was not rejected");
    failures += require_true(
        bytes_unchanged(&alias, alias_snapshot, sizeof(alias)),
        "unit-validation alias changed caller storage");
  }

  {
    _Alignas(max_align_t) unsigned char partial_storage[
        sizeof(morphoia_engine_ir_unit_t) +
        sizeof(morphoia_engine_ir_unit_validation_t)];
    unsigned char partial_snapshot[sizeof(partial_storage)];
    const size_t validation_offset =
        sizeof(morphoia_engine_ir_unit_t) -
        _Alignof(morphoia_engine_ir_unit_validation_t);
    morphoia_engine_ir_unit_t* const partial_unit =
        (morphoia_engine_ir_unit_t*)(void*)partial_storage;
    morphoia_engine_ir_unit_validation_t* const partial_validation =
        (morphoia_engine_ir_unit_validation_t*)(void*)(
            partial_storage + validation_offset);
    memset(partial_storage, 0x4c, sizeof(partial_storage));
    memcpy(partial_snapshot, partial_storage, sizeof(partial_storage));
    init_diagnostic(&diagnostic);
    failures += require_true(
        morphoia_context_validate_engine_ir_unit(
            context, partial_unit, partial_validation, &diagnostic) ==
            MORPHOIA_STATUS_INVALID_ARGUMENT,
        "partially overlapping unit-validation storage was not rejected");
    failures += require_true(
        bytes_unchanged(
            partial_storage, partial_snapshot, sizeof(partial_storage)),
        "partial unit-validation alias changed caller storage");
  }

  init_unit(&unit, text_view("m"), expected_units[1].dimensions, 1, 0);
  unit.code = bytes_view(
      (const char*)&unit + offsetof(morphoia_engine_ir_unit_t, dimensions) + 1U,
      1U);
  init_validation(&validation);
  memcpy(snapshot, &validation, sizeof(validation));
  init_diagnostic(&diagnostic);
  failures += expect_atomic_error(
      morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic),
      MORPHOIA_STATUS_INVALID_ARGUMENT,
      &validation,
      snapshot,
      &diagnostic,
      "partial code-unit alias was not rejected");

  init_unit(&unit, bytes_view((const char*)&validation, 1U), zero_dimensions, 1, 0);
  init_validation(&validation);
  memcpy(snapshot, &validation, sizeof(validation));
  init_diagnostic(&diagnostic);
  failures += expect_atomic_error(
      morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic),
      MORPHOIA_STATUS_INVALID_ARGUMENT,
      &validation,
      snapshot,
      &diagnostic,
      "code-validation alias was not rejected");

  init_unit(&unit, bytes_view((const char*)context, 1U), zero_dimensions, 1, 0);
  init_validation(&validation);
  memcpy(snapshot, &validation, sizeof(validation));
  init_diagnostic(&diagnostic);
  failures += expect_atomic_error(
      morphoia_context_validate_engine_ir_unit(context, &unit, &validation, &diagnostic),
      MORPHOIA_STATUS_INVALID_ARGUMENT,
      &validation,
      snapshot,
      &diagnostic,
      "code-context alias was not rejected");

  init_diagnostic(&diagnostic);
  diagnostic.message[0] = 'm';
  init_unit(&unit, bytes_view(diagnostic.message, 1U), zero_dimensions, 1, 0);
  init_validation(&validation);
  memcpy(snapshot, &validation, sizeof(validation));
  {
    unsigned char diagnostic_snapshot[sizeof(diagnostic)];
    memcpy(diagnostic_snapshot, &diagnostic, sizeof(diagnostic));
    failures += require_true(
        morphoia_context_validate_engine_ir_unit(
            context, &unit, &validation, &diagnostic) ==
            MORPHOIA_STATUS_INVALID_ARGUMENT,
        "code-diagnostic alias was not rejected");
    failures += require_true(
        bytes_unchanged(&validation, snapshot, sizeof(validation)) &&
            bytes_unchanged(&diagnostic, diagnostic_snapshot, sizeof(diagnostic)),
        "code-diagnostic alias changed caller storage");
  }

  init_unit(&unit, text_view("m"), expected_units[1].dimensions, 1, 0);
  init_validation(&validation);
  memcpy(snapshot, &validation, sizeof(validation));
  init_diagnostic(&diagnostic);
  failures += expect_atomic_error(
      morphoia_context_validate_engine_ir_unit(
          (const morphoia_context_t*)&unit, &unit, &validation, &diagnostic),
      MORPHOIA_STATUS_INVALID_ARGUMENT,
      &validation,
      snapshot,
      &diagnostic,
      "context-unit alias was not rejected");

  init_validation(&validation);
  memcpy(snapshot, &validation, sizeof(validation));
  init_diagnostic(&diagnostic);
  failures += require_true(
      morphoia_context_validate_engine_ir_unit(
          (const morphoia_context_t*)&validation, &unit, &validation, &diagnostic) ==
          MORPHOIA_STATUS_INVALID_ARGUMENT,
      "context-validation alias was not rejected");
  failures += require_true(
      bytes_unchanged(&validation, snapshot, sizeof(validation)),
      "context-validation alias changed validation output");

  {
    union diagnostic_validation_alias {
      morphoia_diagnostic_t diagnostic;
      morphoia_engine_ir_unit_validation_t validation;
      unsigned char bytes[sizeof(morphoia_diagnostic_t)];
    } alias;
    unsigned char alias_snapshot[sizeof(alias)];
    memset(&alias, 0x6b, sizeof(alias));
    memcpy(alias_snapshot, &alias, sizeof(alias));
    failures += require_true(
        morphoia_context_validate_engine_ir_unit(
            context, &unit, &alias.validation, &alias.diagnostic) ==
            MORPHOIA_STATUS_INVALID_ARGUMENT,
        "validation-diagnostic alias was not rejected");
    failures += require_true(
        bytes_unchanged(&alias, alias_snapshot, sizeof(alias)),
        "validation-diagnostic alias changed caller storage");
  }

  {
    union diagnostic_unit_alias {
      morphoia_diagnostic_t diagnostic;
      morphoia_engine_ir_unit_t unit;
      unsigned char bytes[sizeof(morphoia_diagnostic_t)];
    } alias;
    unsigned char alias_snapshot[sizeof(alias)];
    memset(&alias, 0x6d, sizeof(alias));
    memcpy(alias_snapshot, &alias, sizeof(alias));
    init_validation(&validation);
    memcpy(snapshot, &validation, sizeof(validation));
    failures += require_true(
        morphoia_context_validate_engine_ir_unit(
            context, &alias.unit, &validation, &alias.diagnostic) ==
            MORPHOIA_STATUS_INVALID_ARGUMENT,
        "unit-diagnostic alias was not rejected");
    failures += require_true(
        bytes_unchanged(&alias, alias_snapshot, sizeof(alias)) &&
            bytes_unchanged(&validation, snapshot, sizeof(validation)),
        "unit-diagnostic alias changed caller storage");
  }

  {
    union diagnostic_context_alias {
      morphoia_diagnostic_t diagnostic;
      unsigned char context_storage[sizeof(morphoia_diagnostic_t)];
    } alias;
    unsigned char alias_snapshot[sizeof(alias)];
    memset(&alias, 0x6e, sizeof(alias));
    memcpy(alias_snapshot, &alias, sizeof(alias));
    init_validation(&validation);
    memcpy(snapshot, &validation, sizeof(validation));
    failures += require_true(
        morphoia_context_validate_engine_ir_unit(
            (const morphoia_context_t*)&alias,
            &unit,
            &validation,
            &alias.diagnostic) == MORPHOIA_STATUS_INVALID_ARGUMENT,
        "context-diagnostic alias was not rejected");
    failures += require_true(
        bytes_unchanged(&alias, alias_snapshot, sizeof(alias)) &&
            bytes_unchanged(&validation, snapshot, sizeof(validation)),
        "context-diagnostic alias changed caller storage");
  }

  {
    union all_alias {
      morphoia_diagnostic_t diagnostic;
      morphoia_engine_ir_unit_t unit;
      morphoia_engine_ir_unit_validation_t validation;
      unsigned char bytes[sizeof(morphoia_diagnostic_t)];
    } alias;
    unsigned char alias_snapshot[sizeof(alias)];
    memset(&alias, 0x7c, sizeof(alias));
    memcpy(alias_snapshot, &alias, sizeof(alias));
    failures += require_true(
        morphoia_context_validate_engine_ir_unit(
            (const morphoia_context_t*)&alias,
            &alias.unit,
            &alias.validation,
            &alias.diagnostic) == MORPHOIA_STATUS_INVALID_ARGUMENT,
        "all-storage alias was not rejected");
    failures += require_true(
        bytes_unchanged(&alias, alias_snapshot, sizeof(alias)),
        "all-storage alias changed caller storage");
  }

  init_diagnostic(&diagnostic);
  failures += require_true(
      morphoia_context_destroy(&context, &diagnostic) == MORPHOIA_STATUS_OK &&
          context == NULL,
      "context destruction failed");

  if (failures != 0) {
    return 1;
  }
  (void)printf(
      "unit_validation_c_api_test: PASS (10 literals, verdicts, ABI, aliases, UTF-8)\n");
  return 0;
}
