// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#include "core/unit_registry.hpp"

#include <array>
#include <cstdint>
#include <iostream>
#include <string_view>

namespace {

using Definition = morphoia::core::EngineIrUnitDefinition;
using Dimensions = std::array<std::int32_t, morphoia::core::engine_ir_dimension_count>;

struct Expected {
  std::string_view code;
  Dimensions dimensions;
  std::int64_t coefficient;
  std::int32_t scale;
};

int require(const bool condition, const char* const message) {
  if (condition) {
    return 0;
  }
  std::cerr << "unit_registry_test: " << message << '\n';
  return 1;
}

} // namespace

int main() {
  constexpr std::array<Expected, 10> expected{{
      {"1", Dimensions{0, 0, 0, 0, 0, 0, 0}, 1, 0},
      {"m", Dimensions{1, 0, 0, 0, 0, 0, 0}, 1, 0},
      {"mm", Dimensions{1, 0, 0, 0, 0, 0, 0}, 1, -3},
      {"s", Dimensions{0, 0, 1, 0, 0, 0, 0}, 1, 0},
      {"kg", Dimensions{0, 1, 0, 0, 0, 0, 0}, 1, 0},
      {"g", Dimensions{0, 1, 0, 0, 0, 0, 0}, 1, -3},
      {"A", Dimensions{0, 0, 0, 1, 0, 0, 0}, 1, 0},
      {"K", Dimensions{0, 0, 0, 0, 1, 0, 0}, 1, 0},
      {"mol", Dimensions{0, 0, 0, 0, 0, 1, 0}, 1, 0},
      {"cd", Dimensions{0, 0, 0, 0, 0, 0, 1}, 1, 0},
  }};

  int failures = 0;
  for (const Expected& value : expected) {
    const auto found = morphoia::core::find_engine_ir_unit(value.code);
    failures += require(found.has_value(), "published literal was not found");
    if (found.has_value()) {
      failures += require(found->code == value.code, "literal lookup changed code");
      failures += require(found->dimensions == value.dimensions, "dimension tuple mismatch");
      failures += require(
          found->si_factor_coefficient == value.coefficient &&
              found->si_factor_scale == value.scale,
          "SI factor mismatch");
    }
  }
  failures += require(!morphoia::core::find_engine_ir_unit("").has_value(), "empty matched");
  failures += require(!morphoia::core::find_engine_ir_unit("MM").has_value(), "case folded");
  failures += require(!morphoia::core::find_engine_ir_unit("cm").has_value(), "extra unit matched");
  failures += require(!morphoia::core::find_engine_ir_unit("m/s").has_value(), "parsed expression");

  if (failures != 0) {
    return 1;
  }
  std::cout << "unit_registry_test: PASS (10 exact literals, no parser)\n";
  return 0;
}
