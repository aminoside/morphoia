// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#include "morphoia/engine.h"

#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <new>

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
    default: {
      static constexpr char value[] = "MORPHOIA_STATUS_UNKNOWN";
      return string_view(value, sizeof(value) - 1U);
    }
  }
}
