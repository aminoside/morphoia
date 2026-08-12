/* SPDX-FileCopyrightText: 2026 Olivier Ami */
/* SPDX-License-Identifier: Apache-2.0 OR MIT */

#ifndef MORPHOIA_ENGINE_H
#define MORPHOIA_ENGINE_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
#  define MORPHOIA_ENGINE_CALL __cdecl
#else
#  define MORPHOIA_ENGINE_CALL
#endif

#if defined(_WIN32) && defined(MORPHOIA_ENGINE_SHARED)
#  if defined(MORPHOIA_ENGINE_EXPORTS)
#    define MORPHOIA_ENGINE_API __declspec(dllexport)
#  else
#    define MORPHOIA_ENGINE_API __declspec(dllimport)
#  endif
#elif defined(__GNUC__) && defined(MORPHOIA_ENGINE_SHARED)
#  define MORPHOIA_ENGINE_API __attribute__((visibility("default")))
#else
#  define MORPHOIA_ENGINE_API
#endif

#if defined(__cplusplus)
#  define MORPHOIA_ENGINE_NOEXCEPT noexcept
#else
#  define MORPHOIA_ENGINE_NOEXCEPT
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define MORPHOIA_ENGINE_ABI_VERSION UINT32_C(1)
#define MORPHOIA_DIAGNOSTIC_MESSAGE_CAPACITY UINT32_C(256)
#define MORPHOIA_DIAGNOSTIC_DETAIL_CAPACITY UINT32_C(128)

typedef int32_t morphoia_status_t;

#define MORPHOIA_STATUS_OK ((morphoia_status_t)0)
#define MORPHOIA_STATUS_INVALID_ARGUMENT ((morphoia_status_t)1)
#define MORPHOIA_STATUS_UNSUPPORTED_ABI ((morphoia_status_t)2)
#define MORPHOIA_STATUS_STRUCT_TOO_SMALL ((morphoia_status_t)3)
#define MORPHOIA_STATUS_ALLOCATION_FAILED ((morphoia_status_t)4)
#define MORPHOIA_STATUS_INTERNAL_ERROR ((morphoia_status_t)5)
#define MORPHOIA_STATUS_UNSUPPORTED_OPTION ((morphoia_status_t)6)

typedef uint32_t morphoia_diagnostic_severity_t;

#define MORPHOIA_DIAGNOSTIC_NONE ((morphoia_diagnostic_severity_t)0)
#define MORPHOIA_DIAGNOSTIC_INFO ((morphoia_diagnostic_severity_t)1)
#define MORPHOIA_DIAGNOSTIC_WARNING ((morphoia_diagnostic_severity_t)2)
#define MORPHOIA_DIAGNOSTIC_ERROR ((morphoia_diagnostic_severity_t)3)

/* Fixed, non-extensible UTF-8 view. The explicit size is authoritative. */
typedef struct morphoia_string_view {
  const char* data;
  size_t size;
} morphoia_string_view_t;

/*
 * Caller-owned diagnostic. Every text field is UTF-8 and has an explicit byte
 * length. Implementations append a NUL only as a debugging convenience;
 * consumers must use the corresponding length.
 */
typedef struct morphoia_diagnostic {
  uint32_t struct_size;
  uint32_t abi_version;
  morphoia_status_t status;
  morphoia_diagnostic_severity_t severity;
  uint32_t message_length;
  char message[MORPHOIA_DIAGNOSTIC_MESSAGE_CAPACITY];
  uint32_t context_length;
  char context[MORPHOIA_DIAGNOSTIC_DETAIL_CAPACITY];
  uint32_t cause_length;
  char cause[MORPHOIA_DIAGNOSTIC_DETAIL_CAPACITY];
  uint32_t affected_elements_length;
  char affected_elements[MORPHOIA_DIAGNOSTIC_DETAIL_CAPACITY];
  uint32_t recommendation_length;
  char recommendation[MORPHOIA_DIAGNOSTIC_DETAIL_CAPACITY];
} morphoia_diagnostic_t;

typedef struct morphoia_version_info {
  uint32_t struct_size;
  uint32_t abi_version;
  uint32_t engine_abi_version;
  uint32_t major;
  uint32_t minor;
  uint32_t patch;
  morphoia_string_view_t version_string;
} morphoia_version_info_t;

/*
 * Callbacks MUST NOT throw; any accidental exception is caught and converted
 * to a status. `alignment` is a
 * power of two; successful storage must satisfy it. The engine never retains
 * callback-owned data beyond the context lifetime and does not invoke a
 * context's callbacks concurrently during this bootstrap profile. Callbacks
 * must not recursively destroy or otherwise re-enter the same context.
 */
typedef void* (MORPHOIA_ENGINE_CALL *morphoia_allocate_fn)(
    void* user_data,
    size_t size,
    size_t alignment);
typedef void (MORPHOIA_ENGINE_CALL *morphoia_deallocate_fn)(
    void* user_data,
    void* allocation);

typedef struct morphoia_allocator {
  uint32_t struct_size;
  uint32_t abi_version;
  morphoia_allocate_fn allocate;
  morphoia_deallocate_fn deallocate;
  void* user_data;
} morphoia_allocator_t;

#define MORPHOIA_CONTEXT_FLAG_NONE UINT64_C(0)

typedef struct morphoia_context_options {
  uint32_t struct_size;
  uint32_t abi_version;
  uint64_t flags;
  morphoia_allocator_t allocator;
} morphoia_context_options_t;

/* Stable ABI-v1 prefixes; keep these formulas unchanged if fields are appended. */
#define MORPHOIA_DIAGNOSTIC_V1_SIZE \
  ((uint32_t)(offsetof(morphoia_diagnostic_t, recommendation) + \
              sizeof(((morphoia_diagnostic_t*)0)->recommendation)))
#define MORPHOIA_VERSION_INFO_V1_SIZE \
  ((uint32_t)(offsetof(morphoia_version_info_t, version_string) + \
              sizeof(((morphoia_version_info_t*)0)->version_string)))
#define MORPHOIA_ALLOCATOR_V1_SIZE \
  ((uint32_t)(offsetof(morphoia_allocator_t, user_data) + \
              sizeof(((morphoia_allocator_t*)0)->user_data)))
#define MORPHOIA_CONTEXT_OPTIONS_V1_SIZE \
  ((uint32_t)(offsetof(morphoia_context_options_t, allocator) + \
              MORPHOIA_ALLOCATOR_V1_SIZE))

/* The context layout is private to the implementation. */
typedef struct morphoia_context morphoia_context_t;

/*
 * Every caller-owned extensible structure must set struct_size and abi_version
 * to the values known by the caller. Larger future structures are accepted.
 */
MORPHOIA_ENGINE_API morphoia_status_t MORPHOIA_ENGINE_CALL morphoia_engine_get_version(
    morphoia_version_info_t* version,
    morphoia_diagnostic_t* diagnostic) MORPHOIA_ENGINE_NOEXCEPT;

/* A NULL options pointer requests the default allocator and current ABI. */
MORPHOIA_ENGINE_API morphoia_status_t MORPHOIA_ENGINE_CALL morphoia_context_create(
    const morphoia_context_options_t* options,
    morphoia_context_t** context,
    morphoia_diagnostic_t* diagnostic) MORPHOIA_ENGINE_NOEXCEPT;

/*
 * Atomically consumes `*context`: a non-NULL handle is cleared before any
 * destructor/deallocator runs and must never be reused, even on error.
 */
MORPHOIA_ENGINE_API morphoia_status_t MORPHOIA_ENGINE_CALL morphoia_context_destroy(
    morphoia_context_t** context,
    morphoia_diagnostic_t* diagnostic) MORPHOIA_ENGINE_NOEXCEPT;

MORPHOIA_ENGINE_API morphoia_status_t MORPHOIA_ENGINE_CALL morphoia_context_get_abi_version(
    const morphoia_context_t* context,
    uint32_t* abi_version,
    morphoia_diagnostic_t* diagnostic) MORPHOIA_ENGINE_NOEXCEPT;

/* The returned UTF-8 view has static storage duration. */
MORPHOIA_ENGINE_API morphoia_string_view_t MORPHOIA_ENGINE_CALL morphoia_status_name(
    morphoia_status_t status) MORPHOIA_ENGINE_NOEXCEPT;

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* MORPHOIA_ENGINE_H */
