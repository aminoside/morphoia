// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#include "morphoia/engine.h"

#include <cstdlib>
#include <cstring>
#include <iostream>
#include <new>
#include <stdexcept>

namespace {

struct AllocationProbe {
  unsigned allocations{0U};
  unsigned deallocations{0U};
  bool reject_allocation{false};
  bool throw_on_allocation{false};
  bool throw_on_deallocation{false};
  bool misalign_allocation{false};
};

void* MORPHOIA_ENGINE_CALL probe_allocate(
    void* const user_data,
    const size_t size,
    const size_t alignment) {
  auto* const probe = static_cast<AllocationProbe*>(user_data);
  ++probe->allocations;
  if (probe->throw_on_allocation) {
    throw std::runtime_error("allocation probe");
  }
  if (probe->reject_allocation) {
    return nullptr;
  }
  if (alignment == 0U || (alignment & (alignment - 1U)) != 0U) {
    return nullptr;
  }
  void* const allocation = std::malloc(size + (probe->misalign_allocation ? 1U : 0U));
  if (allocation == nullptr || !probe->misalign_allocation) {
    return allocation;
  }
  return static_cast<void*>(static_cast<unsigned char*>(allocation) + 1U);
}

void MORPHOIA_ENGINE_CALL probe_deallocate(void* const user_data, void* const allocation) {
  auto* const probe = static_cast<AllocationProbe*>(user_data);
  ++probe->deallocations;
  void* const base = probe->misalign_allocation
                         ? static_cast<void*>(static_cast<unsigned char*>(allocation) - 1U)
                         : allocation;
  std::free(base);
  if (probe->throw_on_deallocation) {
    throw std::runtime_error("deallocation probe");
  }
}

bool require_true(const bool condition, const char* const message) {
  if (!condition) {
    std::cerr << "core_smoke: " << message << '\n';
  }
  return condition;
}

} // namespace

int main() {
  morphoia_diagnostic_t diagnostic{};
  diagnostic.struct_size = sizeof(diagnostic);
  diagnostic.abi_version = MORPHOIA_ENGINE_ABI_VERSION;

  morphoia_context_options_t options{};
  options.struct_size = sizeof(options);
  options.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  options.flags = MORPHOIA_CONTEXT_FLAG_NONE;

  AllocationProbe probe{};
  options.allocator.struct_size = sizeof(options.allocator);
  options.allocator.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  options.allocator.allocate = probe_allocate;
  options.allocator.deallocate = probe_deallocate;
  options.allocator.user_data = &probe;

  morphoia_context_t* context = nullptr;
  bool passed = true;
  passed &= require_true(
      morphoia_context_create(&options, &context, &diagnostic) == MORPHOIA_STATUS_OK,
      "custom-allocator context creation failed");
  passed &= require_true(context != nullptr, "context is null");
  passed &= require_true(probe.allocations == 1U, "custom allocator was not called once");
  passed &= require_true(
      morphoia_context_destroy(&context, &diagnostic) == MORPHOIA_STATUS_OK,
      "custom-allocator context destruction failed");
  passed &= require_true(context == nullptr, "destroy did not consume the context");
  passed &= require_true(probe.deallocations == 1U, "custom deallocator was not called once");

  options.abi_version = MORPHOIA_ENGINE_ABI_VERSION + 1U;
  context = nullptr;
  passed &= require_true(
      morphoia_context_create(&options, &context, &diagnostic) ==
          MORPHOIA_STATUS_UNSUPPORTED_ABI,
      "unsupported ABI was not rejected");
  passed &= require_true(context == nullptr, "failed creation returned a context");
  passed &= require_true(
      diagnostic.status == MORPHOIA_STATUS_UNSUPPORTED_ABI,
      "diagnostic status does not report unsupported ABI");
  passed &= require_true(
      diagnostic.severity == MORPHOIA_DIAGNOSTIC_ERROR,
      "error diagnostic has an unexpected severity");
  passed &= require_true(
      diagnostic.message_length == std::strlen(diagnostic.message),
      "diagnostic message length is inconsistent");
  passed &= require_true(diagnostic.context_length != 0U, "diagnostic context is missing");
  passed &= require_true(diagnostic.cause_length != 0U, "diagnostic cause is missing");
  passed &= require_true(
      diagnostic.affected_elements_length != 0U,
      "diagnostic affected elements are missing");
  passed &= require_true(
      diagnostic.recommendation_length != 0U,
      "diagnostic recommendation is missing");

  options.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  probe.reject_allocation = true;
  passed &= require_true(
      morphoia_context_create(&options, &context, &diagnostic) ==
          MORPHOIA_STATUS_ALLOCATION_FAILED,
      "allocator failure was not propagated");
  passed &= require_true(context == nullptr, "allocation failure returned a context");
  probe.reject_allocation = false;

  probe.misalign_allocation = true;
  passed &= require_true(
      morphoia_context_create(&options, &context, &diagnostic) ==
          MORPHOIA_STATUS_INVALID_ARGUMENT,
      "misaligned allocator storage was not rejected");
  passed &= require_true(context == nullptr, "misaligned allocator returned a context");
  probe.misalign_allocation = false;

  probe.throw_on_allocation = true;
  passed &= require_true(
      morphoia_context_create(&options, &context, &diagnostic) == MORPHOIA_STATUS_INTERNAL_ERROR,
      "throwing allocator escaped or returned the wrong status");
  passed &= require_true(context == nullptr, "throwing allocator returned a context");
  probe.throw_on_allocation = false;

  passed &= require_true(
      morphoia_context_create(&options, &context, &diagnostic) == MORPHOIA_STATUS_OK,
      "context for throwing deallocator could not be created");
  probe.throw_on_deallocation = true;
  passed &= require_true(
      morphoia_context_destroy(&context, &diagnostic) == MORPHOIA_STATUS_INTERNAL_ERROR,
      "throwing deallocator escaped or returned the wrong status");
  passed &= require_true(
      context == nullptr,
      "throwing deallocator left a reusable context handle");
  probe.throw_on_deallocation = false;

  options.struct_size = 1U;
  context = nullptr;
  passed &= require_true(
      morphoia_context_create(&options, &context, &diagnostic) ==
          MORPHOIA_STATUS_STRUCT_TOO_SMALL,
      "undersized options were not rejected");

  if (!passed) {
    return EXIT_FAILURE;
  }
  std::cout << "core_smoke: PASS (ABI guards, diagnostics, allocator exceptions)\n";
  return EXIT_SUCCESS;
}
