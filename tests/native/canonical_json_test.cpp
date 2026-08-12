// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#include "core/canonical_json.hpp"
#include "core/sha256.hpp"

#include <array>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <string_view>

#ifndef MORPHOIA_TEST_SOURCE_DIR
#  error "MORPHOIA_TEST_SOURCE_DIR must identify the repository source root"
#endif

namespace {

bool require_true(const bool condition, const std::string_view message) {
  if (!condition) {
    std::cerr << "canonical_json_test: " << message << '\n';
  }
  return condition;
}

std::string read_fixture(const std::string_view name) {
  const std::string path = std::string(MORPHOIA_TEST_SOURCE_DIR) +
                           "/tests/native/fixtures/" + std::string(name);
  std::ifstream input(path, std::ios::binary);
  return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

bool require_error(
    const std::string_view input,
    const morphoia::core::JsonErrorCode expected,
    const morphoia::core::CanonicalJsonLimits& limits = {}) {
  const auto result = morphoia::core::canonicalize_json(input, limits);
  return require_true(
      !result && result.error.code == expected && !result.error.message.empty(),
      std::string("wrong classification for invalid input: expected ") +
          std::string(morphoia::core::json_error_name(expected)) + ", got " +
          std::string(morphoia::core::json_error_name(result.error.code)));
}

} // namespace

int main() {
  using morphoia::core::CanonicalJsonLimits;
  using morphoia::core::JsonErrorCode;
  using morphoia::core::Sha256;
  using morphoia::core::canonicalize_json;

  bool passed = true;
  const std::string input = read_fixture("canonical-input.json");
  const std::string expected =
      "{\"\\r\":\"CR\",\"$\":\"dollar\",\"1\":\"one\",\"escaped\":"
      "\"line\\nslash/quote\\\"\",\"negative_zero\":0,\"nested\":[true,null,false,"
      "9007199254740991,-9007199254740991],\"\xC2\x80\":\"control-plane\","
      "\"\xC3\xB6\":\"o-diaeresis\",\"\xE2\x82\xAC\":\"Euro\","
      "\"\xF0\x9F\x98\x80\":\"grin\"}";
  passed &= require_true(!input.empty(), "golden input fixture could not be read");

  const auto canonical = canonicalize_json(input);
  passed &= require_true(static_cast<bool>(canonical), "golden fixture was rejected");
  passed &= require_true(canonical.canonical == expected, "golden canonical bytes differ");
  passed &= require_true(
      Sha256::hash(canonical.canonical).hex() ==
          "e2c261d3704d5ba038012f15347fbb011fc2416159688e46e19b2852d99c3bb9",
      "golden canonical SHA-256 differs");
  const auto replay = canonicalize_json(canonical.canonical);
  passed &= require_true(
      replay && replay.canonical == canonical.canonical,
      "canonicalization is not idempotent");

  const auto utf16_order = canonicalize_json("{\"\\ue000\":1,\"\\ud800\\udc00\":2}");
  passed &= require_true(
      utf16_order && utf16_order.canonical == "{\"𐀀\":2,\"\":1}",
      "object keys were not ordered by UTF-16 code units");

  const auto decoded_escape = canonicalize_json("{\"solidus\":\"\\/\",\"letter\":\"\\u0061\"}");
  passed &= require_true(
      decoded_escape && decoded_escape.canonical == "{\"letter\":\"a\",\"solidus\":\"/\"}",
      "string escapes were not minimized");

  passed &= require_error("{\"a\":1,\"\\u0061\":2}", JsonErrorCode::duplicate_key);
  passed &= require_error("{\"a\":1,\"a\":2}", JsonErrorCode::duplicate_key);
  passed &= require_error("\"\\ud800\"", JsonErrorCode::invalid_surrogate);
  passed &= require_error("\"\\udc00\"", JsonErrorCode::invalid_surrogate);
  passed &= require_error("\"\\ud800\\u0041\"", JsonErrorCode::invalid_surrogate);
  passed &= require_error("\"\\u00xz\"", JsonErrorCode::invalid_escape);
  passed &= require_error("\"\\q\"", JsonErrorCode::invalid_escape);

  const std::array<char, 4> malformed_utf8{
      static_cast<char>(0xf0), static_cast<char>(0x80), static_cast<char>(0x80),
      static_cast<char>(0x80)};
  std::string malformed_string{"\""};
  malformed_string.append(malformed_utf8.data(), malformed_utf8.size());
  malformed_string.push_back('"');
  passed &= require_error(malformed_string, JsonErrorCode::invalid_utf8);
  const std::string truncated_utf8{"\"\xf0\x9f\x98\"", 5U};
  passed &= require_error(truncated_utf8, JsonErrorCode::invalid_utf8);

  passed &= require_error("9007199254740992", JsonErrorCode::unsupported_number);
  passed &= require_error("-9007199254740992", JsonErrorCode::unsupported_number);
  passed &= require_error("1.0", JsonErrorCode::unsupported_number);
  passed &= require_error("1e2", JsonErrorCode::unsupported_number);
  passed &= require_error("01", JsonErrorCode::invalid_number);
  passed &= require_error("NaN", JsonErrorCode::unexpected_token);
  passed &= require_error("Infinity", JsonErrorCode::unexpected_token);
  passed &= require_error("[1,]", JsonErrorCode::unexpected_token);
  passed &= require_error("{} garbage", JsonErrorCode::trailing_data);
  passed &= require_error("\"unterminated", JsonErrorCode::unexpected_end);

  CanonicalJsonLimits depth_limits;
  depth_limits.maximum_depth = 2U;
  passed &= require_error("[[[]]]", JsonErrorCode::depth_limit, depth_limits);
  CanonicalJsonLimits value_limits;
  value_limits.maximum_values = 2U;
  passed &= require_error("[1,2]", JsonErrorCode::value_limit, value_limits);
  CanonicalJsonLimits string_limits;
  string_limits.maximum_string_bytes = 1U;
  passed &= require_error("\"é\"", JsonErrorCode::string_limit, string_limits);
  CanonicalJsonLimits input_limits;
  input_limits.maximum_input_bytes = 3U;
  passed &= require_error("null", JsonErrorCode::input_too_large, input_limits);

  if (!passed) {
    return EXIT_FAILURE;
  }
  std::cout << "canonical_json_test: PASS (golden, Unicode, limits, hostile input)\n";
  return EXIT_SUCCESS;
}
