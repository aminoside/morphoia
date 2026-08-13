// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#include "morphoia/engine.h"

#include <array>
#include <atomic>
#include <barrier>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <thread>
#include <vector>

namespace {

morphoia_string_view_t literal(const char* const value, const std::size_t size) {
  return {value, size};
}

} // namespace

int main() {
  morphoia_context_t* context = nullptr;
  morphoia_diagnostic_t diagnostic{};
  diagnostic.struct_size = sizeof(diagnostic);
  diagnostic.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
  if (morphoia_context_create(nullptr, &context, &diagnostic) != MORPHOIA_STATUS_OK) {
    std::cerr << "unit_validation_thread_test: context creation failed\n";
    return 1;
  }

  constexpr std::size_t thread_count = 16U;
  constexpr std::size_t iterations = 2000U;
  std::atomic<std::uint32_t> failures{0U};
  std::atomic<std::uint32_t> shared_active{0U};
  std::atomic<std::uint32_t> shared_max_active{0U};
  std::barrier shared_ready(static_cast<std::ptrdiff_t>(thread_count));
  std::vector<std::thread> threads;
  threads.reserve(thread_count);
  for (std::size_t thread_index = 0U; thread_index < thread_count; ++thread_index) {
    threads.emplace_back([
                             context,
                             thread_index,
                             &failures,
                             &shared_active,
                             &shared_max_active,
                             &shared_ready]() {
      const auto active = shared_active.fetch_add(1U, std::memory_order_acq_rel) + 1U;
      auto observed = shared_max_active.load(std::memory_order_relaxed);
      while (observed < active &&
             !shared_max_active.compare_exchange_weak(
                 observed, active, std::memory_order_relaxed)) {
      }
      shared_ready.arrive_and_wait();
      for (std::size_t iteration = 0U; iteration < iterations; ++iteration) {
        const bool valid = ((iteration + thread_index) & 1U) == 0U;
        morphoia_engine_ir_unit_t unit{};
        unit.struct_size = sizeof(unit);
        unit.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
        unit.code = literal("mm", 2U);
        unit.dimensions[0] = valid ? 1 : 2;
        unit.si_factor_coefficient = 1;
        unit.si_factor_scale = -3;
        morphoia_engine_ir_unit_validation_t validation{};
        validation.struct_size = sizeof(validation);
        validation.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
        morphoia_diagnostic_t local_diagnostic{};
        local_diagnostic.struct_size = sizeof(local_diagnostic);
        local_diagnostic.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
        const auto status = morphoia_context_validate_engine_ir_unit(
            context, &unit, &validation, &local_diagnostic);
        bool correct = status == MORPHOIA_STATUS_OK && validation.recognized == 1U &&
                       validation.dimensions_match == (valid ? 1U : 0U) &&
                       validation.si_factor_match == 1U &&
                       validation.qualified == (valid ? 1U : 0U);
        switch ((iteration + thread_index) % 3U) {
          case 0U: {
            std::uint32_t abi_version = 0U;
            correct = correct &&
                      morphoia_context_get_abi_version(
                          context, &abi_version, &local_diagnostic) == MORPHOIA_STATUS_OK &&
                      abi_version == MORPHOIA_ENGINE_ABI_VERSION;
            break;
          }
          case 1U: {
            morphoia_capability_info_t capability{};
            capability.struct_size = sizeof(capability);
            capability.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
            correct = correct &&
                      morphoia_context_query_capability(
                          context,
                          literal(
                              MORPHOIA_CAPABILITY_ENGINE_IR_CORE_SI,
                              sizeof(MORPHOIA_CAPABILITY_ENGINE_IR_CORE_SI) - 1U),
                          &capability,
                          &local_diagnostic) == MORPHOIA_STATUS_OK &&
                      capability.supported == 1U;
            break;
          }
          default: {
            static constexpr char input[] = "{\"z\":0,\"a\":1}";
            static constexpr char expected[] = "{\"a\":1,\"z\":0}";
            std::array<char, 32> output{};
            std::size_t required_size = 0U;
            std::array<std::uint8_t, MORPHOIA_SHA256_DIGEST_SIZE> digest{};
            correct = correct &&
                      morphoia_canonical_json_profile1(
                          context,
                          literal(input, sizeof(input) - 1U),
                          nullptr,
                          output.data(),
                          output.size(),
                          &required_size,
                          digest.data(),
                          &local_diagnostic) == MORPHOIA_STATUS_OK &&
                      required_size == sizeof(expected) - 1U &&
                      std::memcmp(output.data(), expected, required_size) == 0;
            break;
          }
        }
        if (!correct) {
          failures.fetch_add(1U, std::memory_order_relaxed);
        }
      }
      shared_active.fetch_sub(1U, std::memory_order_acq_rel);
    });
  }
  for (auto& thread : threads) {
    thread.join();
  }

  std::vector<std::thread> independent_threads;
  std::atomic<std::uint32_t> independent_active{0U};
  std::atomic<std::uint32_t> independent_max_active{0U};
  std::barrier independent_ready(4);
  independent_threads.reserve(4U);
  for (std::size_t index = 0U; index < 4U; ++index) {
    independent_threads.emplace_back([
                                         &failures,
                                         &independent_active,
                                         &independent_max_active,
                                         &independent_ready]() {
      morphoia_context_t* independent = nullptr;
      morphoia_diagnostic_t local_diagnostic{};
      local_diagnostic.struct_size = sizeof(local_diagnostic);
      local_diagnostic.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
      if (morphoia_context_create(nullptr, &independent, &local_diagnostic) !=
          MORPHOIA_STATUS_OK) {
        failures.fetch_add(1U, std::memory_order_relaxed);
        return;
      }
      const auto active = independent_active.fetch_add(1U, std::memory_order_acq_rel) + 1U;
      auto observed = independent_max_active.load(std::memory_order_relaxed);
      while (observed < active &&
             !independent_max_active.compare_exchange_weak(
                 observed, active, std::memory_order_relaxed)) {
      }
      independent_ready.arrive_and_wait();
      morphoia_engine_ir_unit_t unit{};
      unit.struct_size = sizeof(unit);
      unit.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
      unit.code = literal("m", 1U);
      unit.dimensions[0] = 1;
      unit.si_factor_coefficient = 1;
      morphoia_engine_ir_unit_validation_t validation{};
      validation.struct_size = sizeof(validation);
      validation.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
      std::uint32_t abi_version = 0U;
      morphoia_capability_info_t capability{};
      capability.struct_size = sizeof(capability);
      capability.abi_version = MORPHOIA_ENGINE_ABI_VERSION;
      static constexpr char input[] = "{\"z\":0,\"a\":1}";
      static constexpr char expected[] = "{\"a\":1,\"z\":0}";
      std::array<char, 32> output{};
      std::size_t required_size = 0U;
      std::array<std::uint8_t, MORPHOIA_SHA256_DIGEST_SIZE> digest{};
      const bool correct =
          morphoia_context_validate_engine_ir_unit(
              independent, &unit, &validation, &local_diagnostic) ==
              MORPHOIA_STATUS_OK &&
          validation.qualified == 1U &&
          morphoia_context_get_abi_version(
              independent, &abi_version, &local_diagnostic) == MORPHOIA_STATUS_OK &&
          abi_version == MORPHOIA_ENGINE_ABI_VERSION &&
          morphoia_context_query_capability(
              independent,
              literal(
                  MORPHOIA_CAPABILITY_ENGINE_IR_CORE_SI,
                  sizeof(MORPHOIA_CAPABILITY_ENGINE_IR_CORE_SI) - 1U),
              &capability,
              &local_diagnostic) == MORPHOIA_STATUS_OK &&
          capability.supported == 1U &&
          morphoia_canonical_json_profile1(
              independent,
              literal(input, sizeof(input) - 1U),
              nullptr,
              output.data(),
              output.size(),
              &required_size,
              digest.data(),
              &local_diagnostic) == MORPHOIA_STATUS_OK &&
          required_size == sizeof(expected) - 1U &&
          std::memcmp(output.data(), expected, required_size) == 0 &&
          morphoia_context_destroy(&independent, &local_diagnostic) ==
              MORPHOIA_STATUS_OK &&
          independent == nullptr;
      independent_active.fetch_sub(1U, std::memory_order_acq_rel);
      if (!correct) {
        failures.fetch_add(1U, std::memory_order_relaxed);
      }
    });
  }
  for (auto& thread : independent_threads) {
    thread.join();
  }

  const auto destroy_status = morphoia_context_destroy(&context, &diagnostic);
  if (failures.load(std::memory_order_relaxed) != 0U ||
      shared_max_active.load(std::memory_order_relaxed) < 2U ||
      independent_max_active.load(std::memory_order_relaxed) < 2U ||
      destroy_status != MORPHOIA_STATUS_OK || context != nullptr) {
    std::cerr << "unit_validation_thread_test: concurrent verdict mismatch\n";
    return 1;
  }
  std::cout << "unit_validation_thread_test: PASS "
               "(16 shared-context threads, 32000 unit + 32000 mixed calls; "
               "4 independent contexts)\n";
  return 0;
}
