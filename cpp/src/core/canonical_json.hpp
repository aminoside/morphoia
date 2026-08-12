// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#ifndef MORPHOIA_CORE_CANONICAL_JSON_HPP
#define MORPHOIA_CORE_CANONICAL_JSON_HPP

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

namespace morphoia::core {

enum class JsonErrorCode {
  none,
  input_too_large,
  depth_limit,
  value_limit,
  string_limit,
  unexpected_end,
  unexpected_token,
  trailing_data,
  invalid_utf8,
  invalid_escape,
  invalid_surrogate,
  invalid_number,
  unsupported_number,
  duplicate_key,
};

struct JsonError {
  JsonErrorCode code{JsonErrorCode::none};
  std::size_t offset{0};
  std::string message;
};

struct CanonicalJsonLimits {
  std::size_t maximum_input_bytes{1024U * 1024U};
  std::size_t maximum_string_bytes{256U * 1024U};
  std::size_t maximum_values{100'000U};
  std::size_t maximum_depth{64U};
};

struct CanonicalJsonResult {
  std::string canonical;
  JsonError error;

  [[nodiscard]] explicit operator bool() const noexcept {
    return error.code == JsonErrorCode::none;
  }
};

/*
 * Morphoia Canonical JSON Profile 1 is the RFC 8785 serialization form over a
 * deliberately constrained input domain. It accepts null, booleans, Unicode
 * strings, arrays, objects, and only integers in the interoperable IEEE-754
 * range [-9007199254740991, 9007199254740991]. Fractions, exponents, duplicate
 * object keys, invalid UTF-8, and lone surrogates are rejected rather than
 * normalized ambiguously.
 */
[[nodiscard]] CanonicalJsonResult canonicalize_json(
    std::string_view input,
    const CanonicalJsonLimits& limits = {});

[[nodiscard]] std::string_view json_error_name(JsonErrorCode code) noexcept;

} // namespace morphoia::core

#endif // MORPHOIA_CORE_CANONICAL_JSON_HPP
