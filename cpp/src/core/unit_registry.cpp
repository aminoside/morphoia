// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#include "core/unit_registry.hpp"

#include <array>

namespace morphoia::core {
namespace {

using Dimensions = std::array<std::int32_t, engine_ir_dimension_count>;

constexpr std::array<EngineIrUnitDefinition, 10> registry{{
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

} // namespace

std::optional<EngineIrUnitDefinition> find_engine_ir_unit(
    const std::string_view code) noexcept {
  for (const EngineIrUnitDefinition& definition : registry) {
    if (definition.code == code) {
      return definition;
    }
  }
  return std::nullopt;
}

} // namespace morphoia::core
