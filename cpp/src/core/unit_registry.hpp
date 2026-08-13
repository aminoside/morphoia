// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#ifndef MORPHOIA_CORE_UNIT_REGISTRY_HPP
#define MORPHOIA_CORE_UNIT_REGISTRY_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>

namespace morphoia::core {

inline constexpr std::size_t engine_ir_dimension_count = 7U;

struct EngineIrUnitDefinition {
  std::string_view code;
  std::array<std::int32_t, engine_ir_dimension_count> dimensions;
  std::int64_t si_factor_coefficient;
  std::int32_t si_factor_scale;
};

/*
 * Exact, case-sensitive lookup for the closed `engine-ir-core-si-0.1`
 * Morphoia registry. This function deliberately does not parse or normalize
 * unit expressions and does not implement general UCUM equivalence.
 */
std::optional<EngineIrUnitDefinition> find_engine_ir_unit(
    std::string_view code) noexcept;

} // namespace morphoia::core

#endif // MORPHOIA_CORE_UNIT_REGISTRY_HPP
