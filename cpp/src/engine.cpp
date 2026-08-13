// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#include "morphoia/engine.h"

#include "core/canonical_json.hpp"
#include "core/sha256.hpp"
#include "core/unit_registry.hpp"

#include <algorithm>
#include <array>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <limits>
#include <new>
#include <string>
#include <string_view>

#ifndef MORPHOIA_ENGINE_VERSION_MAJOR
#  define MORPHOIA_ENGINE_VERSION_MAJOR 0
#endif
#ifndef MORPHOIA_ENGINE_VERSION_MINOR
#  define MORPHOIA_ENGINE_VERSION_MINOR 0
#endif
#ifndef MORPHOIA_ENGINE_VERSION_PATCH
#  define MORPHOIA_ENGINE_VERSION_PATCH 1
#endif
#ifndef MORPHOIA_ENGINE_VERSION_STRING
#  define MORPHOIA_ENGINE_VERSION_STRING "0.0.1"
#endif

struct morphoia_context {
  uint32_t abi_version;
  morphoia_deallocate_fn deallocate;
  void* allocator_user_data;
};

namespace {

struct DiagnosticDetail {
  const char* message;
  const char* context;
  const char* cause;
  const char* affected_elements;
  const char* recommendation;
};

void* MORPHOIA_ENGINE_CALL default_allocate(void*, const size_t size, const size_t) {
  return std::malloc(size);
}

void MORPHOIA_ENGINE_CALL default_deallocate(void*, void* const allocation) {
  std::free(allocation);
}

void copy_text(
    char* const destination,
    const size_t capacity,
    uint32_t* const length_output,
    const char* const source) noexcept {
  const size_t source_length = source == nullptr ? 0U : std::strlen(source);
  const size_t length = std::min(source_length, capacity - 1U);
  if (length != 0U) {
    std::memcpy(destination, source, length);
  }
  destination[length] = '\0';
  *length_output = static_cast<uint32_t>(length);
}

bool diagnostic_is_compatible(const morphoia_diagnostic_t* const diagnostic) noexcept {
  return diagnostic != nullptr && diagnostic->struct_size >= MORPHOIA_DIAGNOSTIC_V1_SIZE &&
         diagnostic->abi_version == MORPHOIA_ENGINE_ABI_VERSION;
}

void set_diagnostic(
    morphoia_diagnostic_t* const diagnostic,
    const morphoia_status_t status,
    const DiagnosticDetail detail) noexcept {
  if (!diagnostic_is_compatible(diagnostic)) {
    return;
  }

  diagnostic->status = status;
  diagnostic->severity = status == MORPHOIA_STATUS_OK ? MORPHOIA_DIAGNOSTIC_NONE
                                                       : MORPHOIA_DIAGNOSTIC_ERROR;
  copy_text(
      diagnostic->message,
      sizeof(diagnostic->message),
      &diagnostic->message_length,
      detail.message);
  copy_text(
      diagnostic->context,
      sizeof(diagnostic->context),
      &diagnostic->context_length,
      detail.context);
  copy_text(
      diagnostic->cause,
      sizeof(diagnostic->cause),
      &diagnostic->cause_length,
      detail.cause);
  copy_text(
      diagnostic->affected_elements,
      sizeof(diagnostic->affected_elements),
      &diagnostic->affected_elements_length,
      detail.affected_elements);
  copy_text(
      diagnostic->recommendation,
      sizeof(diagnostic->recommendation),
      &diagnostic->recommendation_length,
      detail.recommendation);
}

morphoia_status_t fail(
    morphoia_diagnostic_t* const diagnostic,
    const morphoia_status_t status,
    const DiagnosticDetail detail) noexcept {
  set_diagnostic(diagnostic, status, detail);
  return status;
}

morphoia_status_t internal_exception(
    morphoia_diagnostic_t* const diagnostic,
    const char* const context,
    const char* const affected_elements) noexcept {
  return fail(
      diagnostic,
      MORPHOIA_STATUS_INTERNAL_ERROR,
      {
          "an exception was contained at the C ABI boundary",
          context,
          "a C++ operation or caller-provided callback threw",
          affected_elements,
          "inspect the callback and retry with a non-throwing implementation",
      });
}

constexpr morphoia_string_view_t string_view(const char* const value, const size_t size) noexcept {
  return {value, size};
}

template <std::size_t Size>
constexpr morphoia_string_view_t literal_view(const char (&value)[Size]) noexcept {
  return string_view(value, Size - 1U);
}

bool view_equals(
    const morphoia_string_view_t value,
    const char* const expected,
    const std::size_t expected_size) noexcept {
  return value.size == expected_size &&
         (expected_size == 0U ||
          (value.data != nullptr && std::memcmp(value.data, expected, expected_size) == 0));
}

bool ranges_overlap(
    const void* const first,
    const std::size_t first_size,
    const void* const second,
    const std::size_t second_size) noexcept {
  if (first == nullptr || second == nullptr || first_size == 0U || second_size == 0U) {
    return false;
  }
  const auto first_begin = reinterpret_cast<std::uintptr_t>(first);
  const auto second_begin = reinterpret_cast<std::uintptr_t>(second);
  const auto maximum = std::numeric_limits<std::uintptr_t>::max();
  const auto first_end =
      first_size > maximum - first_begin ? maximum : first_begin + first_size;
  const auto second_end =
      second_size > maximum - second_begin ? maximum : second_begin + second_size;
  return first_begin < second_end && second_begin < first_end;
}

struct StorageRange {
  const void* data;
  std::size_t size;
};

template <std::size_t Count>
bool any_storage_overlap(const std::array<StorageRange, Count>& ranges) noexcept {
  for (std::size_t left = 0U; left < ranges.size(); ++left) {
    for (std::size_t right = left + 1U; right < ranges.size(); ++right) {
      if (ranges_overlap(
              ranges[left].data,
              ranges[left].size,
              ranges[right].data,
              ranges[right].size)) {
        return true;
      }
    }
  }
  return false;
}

bool valid_utf8_identifier(const morphoia_string_view_t value) noexcept {
  if (value.data == nullptr || value.size == 0U || value.size > 255U) {
    return false;
  }
  std::size_t offset = 0U;
  while (offset < value.size) {
    const auto first = static_cast<std::uint8_t>(value.data[offset]);
    if (first == 0U) {
      return false;
    }
    if (first < 0x80U) {
      ++offset;
      continue;
    }
    std::size_t width = 0U;
    std::uint32_t scalar = 0U;
    if (first >= 0xc2U && first <= 0xdfU) {
      width = 2U;
      scalar = first & 0x1fU;
    } else if (first >= 0xe0U && first <= 0xefU) {
      width = 3U;
      scalar = first & 0x0fU;
    } else if (first >= 0xf0U && first <= 0xf4U) {
      width = 4U;
      scalar = first & 0x07U;
    } else {
      return false;
    }
    if (offset + width > value.size) {
      return false;
    }
    for (std::size_t index = 1U; index < width; ++index) {
      const auto continuation = static_cast<std::uint8_t>(value.data[offset + index]);
      if ((continuation & 0xc0U) != 0x80U) {
        return false;
      }
      scalar = (scalar << 6U) | (continuation & 0x3fU);
    }
    const bool overlong = (width == 2U && scalar < 0x80U) ||
                          (width == 3U && scalar < 0x800U) ||
                          (width == 4U && scalar < 0x10000U);
    if (overlong || scalar > 0x10ffffU || (scalar >= 0xd800U && scalar <= 0xdfffU)) {
      return false;
    }
    offset += width;
  }
  return true;
}

bool valid_engine_ir_unit_code(const morphoia_string_view_t value) noexcept {
  if (value.size > 32U) {
    return false;
  }
  return valid_utf8_identifier(value);
}

struct CanonicalLimits {
  morphoia::core::CanonicalJsonLimits parser;
};

morphoia_status_t read_canonical_limits(
    const morphoia_canonical_json_options_t* const options,
    CanonicalLimits& limits,
    morphoia_diagnostic_t* const diagnostic) noexcept {
  std::uint64_t maximum_input_bytes =
      MORPHOIA_CANONICAL_JSON_DEFAULT_MAXIMUM_INPUT_BYTES;
  std::uint64_t maximum_string_bytes =
      MORPHOIA_CANONICAL_JSON_DEFAULT_MAXIMUM_STRING_BYTES;
  std::uint64_t maximum_values = MORPHOIA_CANONICAL_JSON_DEFAULT_MAXIMUM_VALUES;
  std::uint64_t maximum_depth = MORPHOIA_CANONICAL_JSON_DEFAULT_MAXIMUM_DEPTH;
  if (options != nullptr) {
    if (options->struct_size < MORPHOIA_CANONICAL_JSON_OPTIONS_V1_SIZE) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_STRUCT_TOO_SMALL,
          {
              "canonical options structure is too small",
              "canonical JSON Profile 1",
              "struct_size is below the required ABI-v1 prefix",
              "options.struct_size",
              "initialize struct_size with sizeof(morphoia_canonical_json_options_t)",
          });
    }
    if (options->abi_version != MORPHOIA_ENGINE_ABI_VERSION) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_UNSUPPORTED_ABI,
          {
              "canonical options ABI is unsupported",
              "canonical JSON Profile 1",
              "abi_version does not match the engine ABI",
              "options.abi_version",
              "use the negotiated engine ABI version",
          });
    }
    if (options->flags != MORPHOIA_CANONICAL_JSON_FLAG_NONE) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_UNSUPPORTED_OPTION,
          {
              "canonical option flags are unsupported",
              "canonical JSON Profile 1",
              "an unknown flag bit is set",
              "options.flags",
              "clear unsupported flag bits",
          });
    }
    maximum_input_bytes = options->maximum_input_bytes;
    maximum_string_bytes = options->maximum_string_bytes;
    maximum_values = options->maximum_values;
    maximum_depth = options->maximum_depth;
  }

  constexpr auto size_maximum = std::numeric_limits<std::size_t>::max();
  if (maximum_input_bytes == 0U || maximum_string_bytes == 0U || maximum_values == 0U ||
      maximum_depth == 0U || maximum_input_bytes > size_maximum ||
      maximum_string_bytes > size_maximum || maximum_values > size_maximum ||
      maximum_depth > size_maximum) {
    return fail(
        diagnostic,
        MORPHOIA_STATUS_RESOURCE_LIMIT,
        {
            "canonical limits are zero or exceed this platform",
            "canonical JSON Profile 1",
            "every limit must be representable as a positive size_t",
            "options limits",
            "use positive limits within the platform addressable range",
        });
  }
  limits.parser.maximum_input_bytes = static_cast<std::size_t>(maximum_input_bytes);
  limits.parser.maximum_string_bytes = static_cast<std::size_t>(maximum_string_bytes);
  limits.parser.maximum_values = static_cast<std::size_t>(maximum_values);
  limits.parser.maximum_depth = static_cast<std::size_t>(maximum_depth);
  return MORPHOIA_STATUS_OK;
}

bool json_error_is_resource_limit(const morphoia::core::JsonErrorCode code) noexcept {
  using morphoia::core::JsonErrorCode;
  return code == JsonErrorCode::input_too_large || code == JsonErrorCode::depth_limit ||
         code == JsonErrorCode::value_limit || code == JsonErrorCode::string_limit;
}

} // namespace

extern "C" morphoia_status_t MORPHOIA_ENGINE_CALL morphoia_engine_get_version(
    morphoia_version_info_t* const version,
    morphoia_diagnostic_t* const diagnostic) noexcept {
  try {
    if (version == nullptr) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_INVALID_ARGUMENT,
          {
              "version output is null",
              "version query",
              "missing output storage",
              "version",
              "provide a version output structure",
          });
    }
    if (version->struct_size < MORPHOIA_VERSION_INFO_V1_SIZE) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_STRUCT_TOO_SMALL,
          {
              "version output structure is too small",
              "version query",
              "struct_size is below the required size",
              "version.struct_size",
              "initialize struct_size with sizeof(morphoia_version_info_t)",
          });
    }
    if (version->abi_version != MORPHOIA_ENGINE_ABI_VERSION) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_UNSUPPORTED_ABI,
          {
              "version output ABI is unsupported",
              "version query",
              "abi_version does not match the engine ABI",
              "version.abi_version",
              "negotiate a supported ABI version",
          });
    }

    version->engine_abi_version = MORPHOIA_ENGINE_ABI_VERSION;
    version->major = MORPHOIA_ENGINE_VERSION_MAJOR;
    version->minor = MORPHOIA_ENGINE_VERSION_MINOR;
    version->patch = MORPHOIA_ENGINE_VERSION_PATCH;
    static constexpr char version_text[] = MORPHOIA_ENGINE_VERSION_STRING;
    version->version_string = string_view(version_text, sizeof(version_text) - 1U);
    set_diagnostic(diagnostic, MORPHOIA_STATUS_OK, {"", "version query", "", "", ""});
    return MORPHOIA_STATUS_OK;
  } catch (...) {
    return internal_exception(diagnostic, "version query", "version");
  }
}

extern "C" morphoia_status_t MORPHOIA_ENGINE_CALL morphoia_context_create(
    const morphoia_context_options_t* const options,
    morphoia_context_t** const context,
    morphoia_diagnostic_t* const diagnostic) noexcept {
  if (context == nullptr) {
    return fail(
        diagnostic,
        MORPHOIA_STATUS_INVALID_ARGUMENT,
        {
            "context output is null",
            "context creation",
            "missing output storage",
            "context",
            "provide a context output pointer",
        });
  }
  *context = nullptr;

  try {
    morphoia_allocate_fn allocate = default_allocate;
    morphoia_deallocate_fn deallocate = default_deallocate;
    void* allocator_user_data = nullptr;

    if (options != nullptr) {
      if (options->struct_size < MORPHOIA_CONTEXT_OPTIONS_V1_SIZE) {
        return fail(
            diagnostic,
            MORPHOIA_STATUS_STRUCT_TOO_SMALL,
            {
                "context options structure is too small",
                "context creation",
                "struct_size is below the required size",
                "options.struct_size",
                "initialize struct_size with sizeof(morphoia_context_options_t)",
            });
      }
      if (options->abi_version != MORPHOIA_ENGINE_ABI_VERSION) {
        return fail(
            diagnostic,
            MORPHOIA_STATUS_UNSUPPORTED_ABI,
            {
                "requested ABI version is unsupported",
                "context creation",
                "abi_version does not match the engine ABI",
                "options.abi_version",
                "negotiate a supported ABI version",
            });
      }
      if (options->flags != MORPHOIA_CONTEXT_FLAG_NONE) {
        return fail(
            diagnostic,
            MORPHOIA_STATUS_UNSUPPORTED_OPTION,
            {
                "context option flags are unsupported",
                "context creation",
                "an unknown flag bit is set",
                "options.flags",
                "clear unsupported flag bits",
            });
      }

      const bool has_allocate = options->allocator.allocate != nullptr;
      const bool has_deallocate = options->allocator.deallocate != nullptr;
      if (has_allocate != has_deallocate) {
        return fail(
            diagnostic,
            MORPHOIA_STATUS_INVALID_ARGUMENT,
            {
                "allocator callbacks must be provided as a pair",
                "context creation",
                "only one allocator callback is present",
                "options.allocator",
                "provide both callbacks or neither callback",
            });
      }
      if (has_allocate) {
        if (options->allocator.struct_size < MORPHOIA_ALLOCATOR_V1_SIZE) {
          return fail(
              diagnostic,
              MORPHOIA_STATUS_STRUCT_TOO_SMALL,
              {
                  "allocator structure is too small",
                  "context creation",
                  "allocator.struct_size is below the required size",
                  "options.allocator.struct_size",
                  "initialize allocator.struct_size with sizeof(morphoia_allocator_t)",
              });
        }
        if (options->allocator.abi_version != MORPHOIA_ENGINE_ABI_VERSION) {
          return fail(
              diagnostic,
              MORPHOIA_STATUS_UNSUPPORTED_ABI,
              {
                  "allocator ABI version is unsupported",
                  "context creation",
                  "allocator.abi_version does not match",
                  "options.allocator.abi_version",
                  "use the negotiated engine ABI version",
              });
        }
        allocate = options->allocator.allocate;
        deallocate = options->allocator.deallocate;
        allocator_user_data = options->allocator.user_data;
      }
    }

    void* const storage =
        allocate(allocator_user_data, sizeof(morphoia_context), alignof(morphoia_context));
    if (storage == nullptr) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_ALLOCATION_FAILED,
          {
              "context allocation failed",
              "context creation",
              "allocator returned null",
              "context storage",
              "release memory or provide a working allocator",
          });
    }
    if (reinterpret_cast<std::uintptr_t>(storage) % alignof(morphoia_context) != 0U) {
      try {
        deallocate(allocator_user_data, storage);
      } catch (...) {
        return internal_exception(diagnostic, "context creation", "misaligned context storage");
      }
      return fail(
          diagnostic,
          MORPHOIA_STATUS_INVALID_ARGUMENT,
          {
              "context allocation is misaligned",
              "context creation",
              "allocator violated the requested alignment",
              "context storage",
              "return storage aligned to the callback alignment argument",
          });
    }

    *context = new (storage) morphoia_context{
        MORPHOIA_ENGINE_ABI_VERSION,
        deallocate,
        allocator_user_data,
    };
    set_diagnostic(diagnostic, MORPHOIA_STATUS_OK, {"", "context creation", "", "", ""});
    return MORPHOIA_STATUS_OK;
  } catch (const std::bad_alloc&) {
    return fail(
        diagnostic,
        MORPHOIA_STATUS_ALLOCATION_FAILED,
        {
            "context allocation threw",
            "context creation",
            "allocator raised an allocation exception",
            "context storage",
            "release memory or provide a non-throwing allocator",
        });
  } catch (...) {
    return internal_exception(diagnostic, "context creation", "context storage");
  }
}

extern "C" morphoia_status_t MORPHOIA_ENGINE_CALL morphoia_context_destroy(
    morphoia_context_t** const context,
    morphoia_diagnostic_t* const diagnostic) noexcept {
  if (context == nullptr || *context == nullptr) {
    set_diagnostic(diagnostic, MORPHOIA_STATUS_OK, {"", "context destruction", "", "", ""});
    return MORPHOIA_STATUS_OK;
  }

  morphoia_context_t* const consumed = *context;
  *context = nullptr;
  const morphoia_deallocate_fn deallocate = consumed->deallocate;
  void* const allocator_user_data = consumed->allocator_user_data;
  consumed->~morphoia_context();
  try {
    deallocate(allocator_user_data, consumed);
    set_diagnostic(diagnostic, MORPHOIA_STATUS_OK, {"", "context destruction", "", "", ""});
    return MORPHOIA_STATUS_OK;
  } catch (...) {
    return fail(
        diagnostic,
        MORPHOIA_STATUS_INTERNAL_ERROR,
        {
            "deallocator exception was contained",
            "context destruction",
            "the caller-provided deallocator threw after context destruction",
            "destroyed context storage",
            "do not reuse the context; fix the deallocator before creating another context",
        });
  }
}

extern "C" morphoia_status_t MORPHOIA_ENGINE_CALL morphoia_context_get_abi_version(
    const morphoia_context_t* const context,
    uint32_t* const abi_version,
    morphoia_diagnostic_t* const diagnostic) noexcept {
  try {
    if (context == nullptr || abi_version == nullptr) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_INVALID_ARGUMENT,
          {
              "context and ABI version output are required",
              "context ABI query",
              "a required pointer is null",
              "context or abi_version",
              "provide both required pointers",
          });
    }

    *abi_version = context->abi_version;
    set_diagnostic(diagnostic, MORPHOIA_STATUS_OK, {"", "context ABI query", "", "", ""});
    return MORPHOIA_STATUS_OK;
  } catch (...) {
    return internal_exception(diagnostic, "context ABI query", "context or abi_version");
  }
}

extern "C" morphoia_status_t MORPHOIA_ENGINE_CALL morphoia_context_query_capability(
    const morphoia_context_t* const context,
    const morphoia_string_view_t capability,
    morphoia_capability_info_t* const info,
    morphoia_diagnostic_t* const diagnostic) noexcept {
  try {
    const StorageRange capability_storage{capability.data, capability.size};
    const StorageRange info_storage{info, MORPHOIA_CAPABILITY_INFO_V1_SIZE};
    const StorageRange diagnostic_storage{diagnostic, MORPHOIA_DIAGNOSTIC_V1_SIZE};
    if (ranges_overlap(
            diagnostic_storage.data,
            diagnostic_storage.size,
            capability_storage.data,
            capability_storage.size) ||
        ranges_overlap(
            diagnostic_storage.data,
            diagnostic_storage.size,
            info_storage.data,
            info_storage.size)) {
      return MORPHOIA_STATUS_INVALID_ARGUMENT;
    }
    if (ranges_overlap(
            capability_storage.data,
            capability_storage.size,
            info_storage.data,
            info_storage.size)) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_INVALID_ARGUMENT,
          {
              "capability query storage overlaps",
              "capability query",
              "capability and info ABI-v1 storage must be disjoint",
              "capability or info",
              "provide non-overlapping caller-owned storage",
          });
    }
    if (context == nullptr || info == nullptr) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_INVALID_ARGUMENT,
          {
              "context and capability output are required",
              "capability query",
              "a required pointer is null",
              "context or info",
              "provide both required pointers",
          });
    }
    if (!valid_utf8_identifier(capability)) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_INVALID_ARGUMENT,
          {
              "capability name is not a valid UTF-8 identifier",
              "capability query",
              "the name is empty, too long, malformed UTF-8, or contains NUL",
              "capability",
              "provide a nonempty shortest-form UTF-8 name without embedded NUL",
          });
    }
    if (info->struct_size < MORPHOIA_CAPABILITY_INFO_V1_SIZE) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_STRUCT_TOO_SMALL,
          {
              "capability output structure is too small",
              "capability query",
              "struct_size is below the required ABI-v1 prefix",
              "info.struct_size",
              "initialize struct_size with sizeof(morphoia_capability_info_t)",
          });
    }
    if (info->abi_version != MORPHOIA_ENGINE_ABI_VERSION) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_UNSUPPORTED_ABI,
          {
              "capability output ABI is unsupported",
              "capability query",
              "abi_version does not match the engine ABI",
              "info.abi_version",
              "use the negotiated engine ABI version",
          });
    }

    static constexpr char manifest_capability_name[] =
        MORPHOIA_CAPABILITY_ENGINE_IR_MANIFEST;
    static constexpr char manifest_format_identifier[] = "morphoia.engine.ir-manifest";
    static constexpr char manifest_format_version[] = MORPHOIA_ENGINE_IR_FORMAT_VERSION;
    static constexpr char manifest_media_type[] = MORPHOIA_ENGINE_IR_MEDIA_TYPE;
    static constexpr char manifest_canonical_profile[] = MORPHOIA_CANONICAL_JSON_PROFILE1;
    static constexpr char unit_capability_name[] = MORPHOIA_CAPABILITY_ENGINE_IR_CORE_SI;
    static constexpr char inspection_format_identifier[] =
        "morphoia.engine.ir-inspection";
    static constexpr char inspection_format_version[] = "0.1.0";
    static constexpr char inspection_media_type[] =
        "application/vnd.morphoia.ir-inspection.v0+json";
    static constexpr char extension_keys[] = "";

    morphoia_capability_info_t result{};
    result.struct_size = MORPHOIA_CAPABILITY_INFO_V1_SIZE;
    result.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
    const bool manifest_supported = view_equals(
        capability,
        manifest_capability_name,
        sizeof(manifest_capability_name) - 1U);
    const bool unit_supported = view_equals(
        capability, unit_capability_name, sizeof(unit_capability_name) - 1U);
    result.supported = manifest_supported || unit_supported ? 1U : 0U;
    if (manifest_supported) {
      result.capability_name = literal_view(manifest_capability_name);
      result.format_identifier = literal_view(manifest_format_identifier);
      result.format_version = literal_view(manifest_format_version);
      result.media_type = literal_view(manifest_media_type);
      result.canonical_profile = literal_view(manifest_canonical_profile);
      result.extension_keys = literal_view(extension_keys);
      result.maximum_input_bytes = MORPHOIA_CANONICAL_JSON_DEFAULT_MAXIMUM_INPUT_BYTES;
      result.maximum_string_bytes = MORPHOIA_CANONICAL_JSON_DEFAULT_MAXIMUM_STRING_BYTES;
      result.maximum_values = MORPHOIA_CANONICAL_JSON_DEFAULT_MAXIMUM_VALUES;
      result.maximum_depth = MORPHOIA_CANONICAL_JSON_DEFAULT_MAXIMUM_DEPTH;
    } else if (unit_supported) {
      result.capability_name = literal_view(unit_capability_name);
      result.format_identifier = literal_view(inspection_format_identifier);
      result.format_version = literal_view(inspection_format_version);
      result.media_type = literal_view(inspection_media_type);
      result.canonical_profile = literal_view(manifest_canonical_profile);
      result.extension_keys = literal_view(extension_keys);
    }
    std::memcpy(info, &result, MORPHOIA_CAPABILITY_INFO_V1_SIZE);
    set_diagnostic(diagnostic, MORPHOIA_STATUS_OK, {"", "capability query", "", "", ""});
    return MORPHOIA_STATUS_OK;
  } catch (...) {
    return internal_exception(diagnostic, "capability query", "capability or info");
  }
}

extern "C" morphoia_status_t MORPHOIA_ENGINE_CALL morphoia_canonical_json_profile1(
    const morphoia_context_t* const context,
    const morphoia_string_view_t input,
    const morphoia_canonical_json_options_t* const options,
    char* const output,
    const size_t output_capacity,
    size_t* const required_size,
    uint8_t sha256[MORPHOIA_SHA256_DIGEST_SIZE],
    morphoia_diagnostic_t* const diagnostic) noexcept {
  try {
    const std::array<StorageRange, 5> result_storage{{
        {input.data, input.size},
        {output, output_capacity},
        {required_size, sizeof(*required_size)},
        {sha256, MORPHOIA_SHA256_DIGEST_SIZE},
        {options, MORPHOIA_CANONICAL_JSON_OPTIONS_V1_SIZE},
    }};
    const StorageRange diagnostic_storage{diagnostic, MORPHOIA_DIAGNOSTIC_V1_SIZE};
    for (const StorageRange storage : result_storage) {
      if (ranges_overlap(
              diagnostic_storage.data,
              diagnostic_storage.size,
              storage.data,
              storage.size)) {
        return MORPHOIA_STATUS_INVALID_ARGUMENT;
      }
    }
    if (any_storage_overlap(result_storage)) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_INVALID_ARGUMENT,
          {
              "canonicalization storage overlaps",
              "canonical JSON Profile 1",
              "input, output, result, digest, and options storage must be disjoint",
              "input, output, required_size, sha256, or options",
              "provide non-overlapping caller-owned storage",
          });
    }
    if (context == nullptr || required_size == nullptr || sha256 == nullptr) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_INVALID_ARGUMENT,
          {
              "context, required size, and SHA-256 output are required",
              "canonical JSON Profile 1",
              "a required pointer is null",
              "context, required_size, or sha256",
              "provide every required pointer",
          });
    }
    if ((input.data == nullptr && input.size != 0U) ||
        (output == nullptr && output_capacity != 0U)) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_INVALID_ARGUMENT,
          {
              "an explicit-length buffer has a null pointer with nonzero size",
              "canonical JSON Profile 1",
              "the input or output view is invalid",
              "input or output",
              "provide readable/writable bytes or a zero-length null buffer",
          });
    }
    CanonicalLimits limits{};
    const morphoia_status_t limit_status = read_canonical_limits(options, limits, diagnostic);
    if (limit_status != MORPHOIA_STATUS_OK) {
      return limit_status;
    }

    const char* const input_data = input.data == nullptr ? "" : input.data;
    const auto result = morphoia::core::canonicalize_json(
        std::string_view(input_data, input.size), limits.parser);
    if (!result) {
      const morphoia_status_t status = json_error_is_resource_limit(result.error.code)
                                           ? MORPHOIA_STATUS_RESOURCE_LIMIT
                                           : MORPHOIA_STATUS_INVALID_JSON;
      const std::string context_text =
          "canonical JSON Profile 1 byte " + std::to_string(result.error.offset) + " (" +
          std::string(morphoia::core::json_error_name(result.error.code)) + ")";
      return fail(
          diagnostic,
          status,
          {
              status == MORPHOIA_STATUS_RESOURCE_LIMIT
                  ? "JSON input exceeded a configured resource limit"
                  : "JSON input is invalid for Morphoia Canonical JSON Profile 1",
              context_text.c_str(),
              result.error.message.c_str(),
              "input",
              "correct the input or explicitly select suitable bounded limits",
          });
    }

    const auto digest = morphoia::core::Sha256::hash(result.canonical);
    if (output_capacity < result.canonical.size()) {
      *required_size = result.canonical.size();
      std::memcpy(sha256, digest.bytes.data(), digest.bytes.size());
      set_diagnostic(
          diagnostic,
          MORPHOIA_STATUS_BUFFER_TOO_SMALL,
          {
              "canonical output buffer is too small",
              "canonical JSON Profile 1",
              "measurement or insufficient caller-owned storage",
              "output",
              "allocate required_size bytes and retry with the same input and options",
          });
      return MORPHOIA_STATUS_BUFFER_TOO_SMALL;
    }
    if (!result.canonical.empty()) {
      std::memcpy(output, result.canonical.data(), result.canonical.size());
    }
    *required_size = result.canonical.size();
    std::memcpy(sha256, digest.bytes.data(), digest.bytes.size());
    set_diagnostic(
        diagnostic, MORPHOIA_STATUS_OK, {"", "canonical JSON Profile 1", "", "", ""});
    return MORPHOIA_STATUS_OK;
  } catch (const std::bad_alloc&) {
    return fail(
        diagnostic,
        MORPHOIA_STATUS_ALLOCATION_FAILED,
        {
            "canonicalization allocation failed",
            "canonical JSON Profile 1",
            "bounded parser storage could not be allocated",
            "parser or canonical output",
            "release memory or lower the configured resource limits",
        });
  } catch (...) {
    return internal_exception(diagnostic, "canonical JSON Profile 1", "input or output");
  }
}

extern "C" morphoia_status_t MORPHOIA_ENGINE_CALL
morphoia_context_validate_engine_ir_unit(
    const morphoia_context_t* const context,
    const morphoia_engine_ir_unit_t* const unit,
    morphoia_engine_ir_unit_validation_t* const validation,
    morphoia_diagnostic_t* const diagnostic) noexcept {
  try {
    const std::array<StorageRange, 3> fixed_storage{{
        {context, sizeof(morphoia_context)},
        {unit, MORPHOIA_ENGINE_IR_UNIT_V1_SIZE},
        {validation, MORPHOIA_ENGINE_IR_UNIT_VALIDATION_V1_SIZE},
    }};
    const StorageRange diagnostic_storage{diagnostic, MORPHOIA_DIAGNOSTIC_V1_SIZE};
    for (const StorageRange storage : fixed_storage) {
      if (ranges_overlap(
              diagnostic_storage.data,
              diagnostic_storage.size,
              storage.data,
              storage.size)) {
        return MORPHOIA_STATUS_INVALID_ARGUMENT;
      }
    }
    if (any_storage_overlap(fixed_storage)) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_INVALID_ARGUMENT,
          {
              "unit qualification storage overlaps",
              "engine-ir-core-si-0.1 unit qualification",
              "context, unit, and validation ABI-v1 storage must be disjoint",
              "context, unit, or validation",
              "provide non-overlapping caller-owned storage",
          });
    }
    if (context == nullptr || unit == nullptr || validation == nullptr) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_INVALID_ARGUMENT,
          {
              "context, unit, and validation output are required",
              "engine-ir-core-si-0.1 unit qualification",
              "a required pointer is null",
              "context, unit, or validation",
              "provide every required pointer",
          });
    }
    if (unit->struct_size < MORPHOIA_ENGINE_IR_UNIT_V1_SIZE) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_STRUCT_TOO_SMALL,
          {
              "unit structure is too small",
              "engine-ir-core-si-0.1 unit qualification",
              "struct_size is below the required ABI-v1 prefix",
              "unit.struct_size",
              "initialize struct_size with sizeof(morphoia_engine_ir_unit_t)",
          });
    }
    if (unit->abi_version != MORPHOIA_ENGINE_ABI_VERSION) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_UNSUPPORTED_ABI,
          {
              "unit ABI is unsupported",
              "engine-ir-core-si-0.1 unit qualification",
              "abi_version does not match the engine ABI",
              "unit.abi_version",
              "use the negotiated engine ABI version",
          });
    }
    const StorageRange code_storage{unit->code.data, unit->code.size};
    const std::array<StorageRange, 4> all_storage{{
        fixed_storage[0],
        fixed_storage[1],
        code_storage,
        fixed_storage[2],
    }};
    if (ranges_overlap(
            diagnostic_storage.data,
            diagnostic_storage.size,
            code_storage.data,
            code_storage.size)) {
      return MORPHOIA_STATUS_INVALID_ARGUMENT;
    }
    if (any_storage_overlap(all_storage)) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_INVALID_ARGUMENT,
          {
              "unit qualification storage overlaps",
              "engine-ir-core-si-0.1 unit qualification",
              "context, unit, code, and validation storage must be disjoint",
              "context, unit, code, or validation",
              "provide non-overlapping caller-owned storage",
          });
    }
    if (validation->struct_size < MORPHOIA_ENGINE_IR_UNIT_VALIDATION_V1_SIZE) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_STRUCT_TOO_SMALL,
          {
              "unit validation output structure is too small",
              "engine-ir-core-si-0.1 unit qualification",
              "struct_size is below the required ABI-v1 prefix",
              "validation.struct_size",
              "initialize struct_size with sizeof(morphoia_engine_ir_unit_validation_t)",
          });
    }
    if (validation->abi_version != MORPHOIA_ENGINE_ABI_VERSION) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_UNSUPPORTED_ABI,
          {
              "unit validation output ABI is unsupported",
              "engine-ir-core-si-0.1 unit qualification",
              "abi_version does not match the engine ABI",
              "validation.abi_version",
              "use the negotiated engine ABI version",
          });
    }
    if (unit->flags != MORPHOIA_ENGINE_IR_UNIT_FLAG_NONE ||
        validation->flags != MORPHOIA_ENGINE_IR_UNIT_VALIDATION_FLAG_NONE) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_UNSUPPORTED_OPTION,
          {
              "unit qualification flags are unsupported",
              "engine-ir-core-si-0.1 unit qualification",
              "an unknown input or output flag bit is set",
              "unit.flags or validation.flags",
              "clear unsupported flag bits",
          });
    }
    if (unit->reserved != 0U || validation->reserved != 0U) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_INVALID_ARGUMENT,
          {
              "unit qualification reserved fields must be zero",
              "engine-ir-core-si-0.1 unit qualification",
              "a reserved ABI-v1 field is nonzero",
              "unit.reserved or validation.reserved",
              "zero every reserved field before calling",
          });
    }

    if (!valid_engine_ir_unit_code(unit->code)) {
      return fail(
          diagnostic,
          MORPHOIA_STATUS_INVALID_ARGUMENT,
          {
              "unit code is not a valid UTF-8 identifier",
              "engine-ir-core-si-0.1 unit qualification",
              "the code is empty, exceeds 32 bytes, is malformed UTF-8, or contains NUL",
              "unit.code",
              "provide 1 to 32 bytes of shortest-form UTF-8 without embedded NUL",
          });
    }

    morphoia_engine_ir_unit_validation_t result{};
    result.struct_size = MORPHOIA_ENGINE_IR_UNIT_VALIDATION_V1_SIZE;
    result.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
    const auto definition = morphoia::core::find_engine_ir_unit(
        std::string_view(unit->code.data, unit->code.size));
    if (definition.has_value()) {
      result.recognized = 1U;
      bool dimensions_match = true;
      for (std::size_t index = 0U; index < definition->dimensions.size(); ++index) {
        result.expected_dimensions[index] = definition->dimensions[index];
        dimensions_match = dimensions_match &&
                           unit->dimensions[index] == definition->dimensions[index];
      }
      result.dimensions_match = dimensions_match ? 1U : 0U;
      result.expected_si_factor_coefficient = definition->si_factor_coefficient;
      result.expected_si_factor_scale = definition->si_factor_scale;
      result.si_factor_match =
          unit->si_factor_coefficient == definition->si_factor_coefficient &&
                  unit->si_factor_scale == definition->si_factor_scale
              ? 1U
              : 0U;
      result.qualified = result.dimensions_match != 0U && result.si_factor_match != 0U
                             ? 1U
                             : 0U;
    }
    std::memcpy(validation, &result, MORPHOIA_ENGINE_IR_UNIT_VALIDATION_V1_SIZE);
    set_diagnostic(
        diagnostic,
        MORPHOIA_STATUS_OK,
        {"", "engine-ir-core-si-0.1 unit qualification", "", "", ""});
    return MORPHOIA_STATUS_OK;
  } catch (...) {
    return internal_exception(
        diagnostic,
        "engine-ir-core-si-0.1 unit qualification",
        "unit or validation");
  }
}

extern "C" morphoia_string_view_t MORPHOIA_ENGINE_CALL morphoia_status_name(
    const morphoia_status_t status) noexcept {
  switch (status) {
    case MORPHOIA_STATUS_OK: {
      static constexpr char value[] = "MORPHOIA_STATUS_OK";
      return string_view(value, sizeof(value) - 1U);
    }
    case MORPHOIA_STATUS_INVALID_ARGUMENT: {
      static constexpr char value[] = "MORPHOIA_STATUS_INVALID_ARGUMENT";
      return string_view(value, sizeof(value) - 1U);
    }
    case MORPHOIA_STATUS_UNSUPPORTED_ABI: {
      static constexpr char value[] = "MORPHOIA_STATUS_UNSUPPORTED_ABI";
      return string_view(value, sizeof(value) - 1U);
    }
    case MORPHOIA_STATUS_STRUCT_TOO_SMALL: {
      static constexpr char value[] = "MORPHOIA_STATUS_STRUCT_TOO_SMALL";
      return string_view(value, sizeof(value) - 1U);
    }
    case MORPHOIA_STATUS_ALLOCATION_FAILED: {
      static constexpr char value[] = "MORPHOIA_STATUS_ALLOCATION_FAILED";
      return string_view(value, sizeof(value) - 1U);
    }
    case MORPHOIA_STATUS_INTERNAL_ERROR: {
      static constexpr char value[] = "MORPHOIA_STATUS_INTERNAL_ERROR";
      return string_view(value, sizeof(value) - 1U);
    }
    case MORPHOIA_STATUS_UNSUPPORTED_OPTION: {
      static constexpr char value[] = "MORPHOIA_STATUS_UNSUPPORTED_OPTION";
      return string_view(value, sizeof(value) - 1U);
    }
    case MORPHOIA_STATUS_BUFFER_TOO_SMALL: {
      static constexpr char value[] = "MORPHOIA_STATUS_BUFFER_TOO_SMALL";
      return string_view(value, sizeof(value) - 1U);
    }
    case MORPHOIA_STATUS_INVALID_JSON: {
      static constexpr char value[] = "MORPHOIA_STATUS_INVALID_JSON";
      return string_view(value, sizeof(value) - 1U);
    }
    case MORPHOIA_STATUS_RESOURCE_LIMIT: {
      static constexpr char value[] = "MORPHOIA_STATUS_RESOURCE_LIMIT";
      return string_view(value, sizeof(value) - 1U);
    }
    default: {
      static constexpr char value[] = "MORPHOIA_STATUS_UNKNOWN";
      return string_view(value, sizeof(value) - 1U);
    }
  }
}
