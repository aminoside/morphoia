// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#include "core/canonical_json.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <cstdint>
#include <limits>
#include <string>
#include <unordered_set>
#include <utility>
#include <variant>
#include <vector>

namespace morphoia::core {
namespace {

constexpr std::uint64_t maximum_interoperable_integer = UINT64_C(9007199254740991);

struct Value;
using Array = std::vector<Value>;
using Object = std::vector<std::pair<std::string, Value>>;

struct Value {
  using Storage = std::variant<std::nullptr_t, bool, std::int64_t, std::string, Array, Object>;
  Storage storage;
};

class Parser final {
 public:
  Parser(const std::string_view input, const CanonicalJsonLimits& limits)
      : input_(input), limits_(limits) {}

  [[nodiscard]] CanonicalJsonResult run() {
    if (input_.size() > limits_.maximum_input_bytes) {
      return failure(JsonErrorCode::input_too_large, 0U, "JSON input exceeds its byte limit");
    }
    if (limits_.maximum_values == 0U || limits_.maximum_depth == 0U) {
      return failure(JsonErrorCode::value_limit, 0U, "JSON parser limits prohibit a root value");
    }

    skip_whitespace();
    Value root{nullptr};
    if (!parse_value(root, 0U)) {
      return {{}, std::move(error_)};
    }
    skip_whitespace();
    if (position_ != input_.size()) {
      return failure(JsonErrorCode::trailing_data, position_, "data follows the root JSON value");
    }

    std::string output;
    output.reserve(input_.size());
    serialize(root, output);
    return {std::move(output), {}};
  }

 private:
  [[nodiscard]] CanonicalJsonResult failure(
      const JsonErrorCode code,
      const std::size_t offset,
      std::string message) const {
    return {{}, {code, offset, std::move(message)}};
  }

  bool set_error(const JsonErrorCode code, const std::size_t offset, std::string message) {
    if (error_.code == JsonErrorCode::none) {
      error_ = {code, offset, std::move(message)};
    }
    return false;
  }

  void skip_whitespace() noexcept {
    while (position_ < input_.size()) {
      const char value = input_[position_];
      if (value != ' ' && value != '\t' && value != '\n' && value != '\r') {
        break;
      }
      ++position_;
    }
  }

  bool parse_value(Value& value, const std::size_t depth) {
    if (++value_count_ > limits_.maximum_values) {
      return set_error(JsonErrorCode::value_limit, position_, "JSON value count exceeds its limit");
    }
    if (position_ == input_.size()) {
      return set_error(JsonErrorCode::unexpected_end, position_, "expected a JSON value");
    }

    switch (input_[position_]) {
      case 'n':
        if (!consume_keyword("null")) {
          return false;
        }
        value.storage = nullptr;
        return true;
      case 't':
        if (!consume_keyword("true")) {
          return false;
        }
        value.storage = true;
        return true;
      case 'f':
        if (!consume_keyword("false")) {
          return false;
        }
        value.storage = false;
        return true;
      case '"': {
        std::string parsed;
        if (!parse_string(parsed)) {
          return false;
        }
        value.storage = std::move(parsed);
        return true;
      }
      case '[':
        return parse_array(value, depth);
      case '{':
        return parse_object(value, depth);
      default:
        if (input_[position_] == '-' ||
            (input_[position_] >= '0' && input_[position_] <= '9')) {
          return parse_integer(value);
        }
        return set_error(JsonErrorCode::unexpected_token, position_, "unexpected JSON token");
    }
  }

  bool consume_keyword(const std::string_view keyword) {
    if (input_.substr(position_, keyword.size()) != keyword) {
      return set_error(JsonErrorCode::unexpected_token, position_, "invalid JSON keyword");
    }
    position_ += keyword.size();
    return true;
  }

  bool parse_array(Value& value, const std::size_t depth) {
    if (depth + 1U > limits_.maximum_depth) {
      return set_error(JsonErrorCode::depth_limit, position_, "JSON nesting exceeds its limit");
    }
    ++position_;
    skip_whitespace();
    Array elements;
    if (position_ < input_.size() && input_[position_] == ']') {
      ++position_;
      value.storage = std::move(elements);
      return true;
    }

    while (true) {
      Value element{nullptr};
      if (!parse_value(element, depth + 1U)) {
        return false;
      }
      elements.push_back(std::move(element));
      skip_whitespace();
      if (position_ == input_.size()) {
        return set_error(JsonErrorCode::unexpected_end, position_, "unterminated JSON array");
      }
      if (input_[position_] == ']') {
        ++position_;
        value.storage = std::move(elements);
        return true;
      }
      if (input_[position_] != ',') {
        return set_error(JsonErrorCode::unexpected_token, position_, "expected ',' or ']' in array");
      }
      ++position_;
      skip_whitespace();
    }
  }

  bool parse_object(Value& value, const std::size_t depth) {
    if (depth + 1U > limits_.maximum_depth) {
      return set_error(JsonErrorCode::depth_limit, position_, "JSON nesting exceeds its limit");
    }
    ++position_;
    skip_whitespace();
    Object members;
    std::unordered_set<std::string> keys;
    if (position_ < input_.size() && input_[position_] == '}') {
      ++position_;
      value.storage = std::move(members);
      return true;
    }

    while (true) {
      if (position_ == input_.size() || input_[position_] != '"') {
        return set_error(JsonErrorCode::unexpected_token, position_, "expected an object key string");
      }
      const std::size_t key_offset = position_;
      std::string key;
      if (!parse_string(key)) {
        return false;
      }
      if (!keys.emplace(key).second) {
        return set_error(JsonErrorCode::duplicate_key, key_offset, "duplicate decoded object key");
      }
      skip_whitespace();
      if (position_ == input_.size() || input_[position_] != ':') {
        return set_error(JsonErrorCode::unexpected_token, position_, "expected ':' after object key");
      }
      ++position_;
      skip_whitespace();
      Value member{nullptr};
      if (!parse_value(member, depth + 1U)) {
        return false;
      }
      members.emplace_back(std::move(key), std::move(member));
      skip_whitespace();
      if (position_ == input_.size()) {
        return set_error(JsonErrorCode::unexpected_end, position_, "unterminated JSON object");
      }
      if (input_[position_] == '}') {
        ++position_;
        std::sort(
            members.begin(),
            members.end(),
            [](const auto& left, const auto& right) { return utf16_less(left.first, right.first); });
        value.storage = std::move(members);
        return true;
      }
      if (input_[position_] != ',') {
        return set_error(JsonErrorCode::unexpected_token, position_, "expected ',' or '}' in object");
      }
      ++position_;
      skip_whitespace();
    }
  }

  bool parse_integer(Value& value) {
    const std::size_t start = position_;
    bool negative = false;
    if (input_[position_] == '-') {
      negative = true;
      ++position_;
      if (position_ == input_.size()) {
        return set_error(JsonErrorCode::invalid_number, start, "minus sign has no integer digits");
      }
    }

    if (input_[position_] == '0') {
      ++position_;
      if (position_ < input_.size() && input_[position_] >= '0' && input_[position_] <= '9') {
        return set_error(JsonErrorCode::invalid_number, start, "leading zero in JSON number");
      }
    } else if (input_[position_] >= '1' && input_[position_] <= '9') {
      while (position_ < input_.size() && input_[position_] >= '0' && input_[position_] <= '9') {
        ++position_;
      }
    } else {
      return set_error(JsonErrorCode::invalid_number, start, "invalid JSON integer");
    }

    if (position_ < input_.size() &&
        (input_[position_] == '.' || input_[position_] == 'e' || input_[position_] == 'E')) {
      return set_error(
          JsonErrorCode::unsupported_number,
          start,
          "Profile 1 rejects fractions and exponents; encode an exact decimal as schema data");
    }

    std::string_view digits = input_.substr(start + (negative ? 1U : 0U), position_ - start - (negative ? 1U : 0U));
    std::uint64_t magnitude = 0U;
    const auto conversion = std::from_chars(digits.data(), digits.data() + digits.size(), magnitude);
    if (conversion.ec != std::errc{} || conversion.ptr != digits.data() + digits.size() ||
        magnitude > maximum_interoperable_integer) {
      return set_error(
          JsonErrorCode::unsupported_number,
          start,
          "integer is outside the interoperable IEEE-754 range");
    }
    if (magnitude == 0U) {
      value.storage = INT64_C(0);
    } else if (negative) {
      value.storage = -static_cast<std::int64_t>(magnitude);
    } else {
      value.storage = static_cast<std::int64_t>(magnitude);
    }
    return true;
  }

  bool parse_string(std::string& output) {
    ++position_;
    while (position_ < input_.size()) {
      const auto byte = static_cast<std::uint8_t>(input_[position_]);
      if (byte == static_cast<std::uint8_t>('"')) {
        ++position_;
        return true;
      }
      if (byte == static_cast<std::uint8_t>('\\')) {
        if (!parse_escape(output)) {
          return false;
        }
      } else if (byte < 0x20U) {
        return set_error(JsonErrorCode::unexpected_token, position_, "unescaped control byte in string");
      } else if (byte < 0x80U) {
        output.push_back(input_[position_++]);
      } else {
        std::uint32_t scalar = 0U;
        std::size_t width = 0U;
        if (!decode_utf8(position_, scalar, width)) {
          return false;
        }
        output.append(input_.substr(position_, width));
        position_ += width;
      }
      if (output.size() > limits_.maximum_string_bytes) {
        return set_error(JsonErrorCode::string_limit, position_, "decoded JSON string exceeds its byte limit");
      }
    }
    return set_error(JsonErrorCode::unexpected_end, position_, "unterminated JSON string");
  }

  bool parse_escape(std::string& output) {
    const std::size_t escape_offset = position_++;
    if (position_ == input_.size()) {
      return set_error(JsonErrorCode::unexpected_end, position_, "unterminated JSON escape");
    }
    const char escaped = input_[position_++];
    switch (escaped) {
      case '"':
      case '\\':
      case '/':
        output.push_back(escaped);
        return true;
      case 'b':
        output.push_back('\b');
        return true;
      case 'f':
        output.push_back('\f');
        return true;
      case 'n':
        output.push_back('\n');
        return true;
      case 'r':
        output.push_back('\r');
        return true;
      case 't':
        output.push_back('\t');
        return true;
      case 'u':
        break;
      default:
        return set_error(JsonErrorCode::invalid_escape, escape_offset, "invalid JSON escape");
    }

    std::uint16_t first = 0U;
    if (!parse_hex_quad(first)) {
      return false;
    }
    std::uint32_t scalar = first;
    if (first >= 0xd800U && first <= 0xdbffU) {
      if (position_ + 6U > input_.size() || input_[position_] != '\\' ||
          input_[position_ + 1U] != 'u') {
        return set_error(JsonErrorCode::invalid_surrogate, escape_offset, "high surrogate lacks a low surrogate");
      }
      position_ += 2U;
      std::uint16_t second = 0U;
      if (!parse_hex_quad(second)) {
        return false;
      }
      if (second < 0xdc00U || second > 0xdfffU) {
        return set_error(JsonErrorCode::invalid_surrogate, escape_offset, "invalid low surrogate");
      }
      scalar = 0x10000U + ((static_cast<std::uint32_t>(first) - 0xd800U) << 10U) +
               (static_cast<std::uint32_t>(second) - 0xdc00U);
    } else if (first >= 0xdc00U && first <= 0xdfffU) {
      return set_error(JsonErrorCode::invalid_surrogate, escape_offset, "lone low surrogate");
    }
    append_utf8(scalar, output);
    return true;
  }

  bool parse_hex_quad(std::uint16_t& result) {
    if (position_ + 4U > input_.size()) {
      return set_error(JsonErrorCode::unexpected_end, position_, "truncated Unicode escape");
    }
    result = 0U;
    for (std::size_t index = 0; index < 4U; ++index) {
      const char value = input_[position_++];
      std::uint16_t digit = 0U;
      if (value >= '0' && value <= '9') {
        digit = static_cast<std::uint16_t>(value - '0');
      } else if (value >= 'a' && value <= 'f') {
        digit = static_cast<std::uint16_t>(value - 'a' + 10);
      } else if (value >= 'A' && value <= 'F') {
        digit = static_cast<std::uint16_t>(value - 'A' + 10);
      } else {
        return set_error(JsonErrorCode::invalid_escape, position_ - 1U, "non-hexadecimal Unicode escape");
      }
      result = static_cast<std::uint16_t>((result << 4U) | digit);
    }
    return true;
  }

  bool decode_utf8(
      const std::size_t offset,
      std::uint32_t& scalar,
      std::size_t& width) {
    const auto first = static_cast<std::uint8_t>(input_[offset]);
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
      return set_error(JsonErrorCode::invalid_utf8, offset, "invalid UTF-8 leading byte");
    }
    if (offset + width > input_.size()) {
      return set_error(JsonErrorCode::invalid_utf8, offset, "truncated UTF-8 sequence");
    }
    for (std::size_t index = 1U; index < width; ++index) {
      const auto continuation = static_cast<std::uint8_t>(input_[offset + index]);
      if ((continuation & 0xc0U) != 0x80U) {
        return set_error(JsonErrorCode::invalid_utf8, offset + index, "invalid UTF-8 continuation byte");
      }
      scalar = (scalar << 6U) | (continuation & 0x3fU);
    }
    const bool overlong = (width == 2U && scalar < 0x80U) ||
                          (width == 3U && scalar < 0x800U) ||
                          (width == 4U && scalar < 0x10000U);
    if (overlong || scalar > 0x10ffffU || (scalar >= 0xd800U && scalar <= 0xdfffU)) {
      return set_error(JsonErrorCode::invalid_utf8, offset, "non-scalar or non-shortest UTF-8 sequence");
    }
    return true;
  }

  static void append_utf8(const std::uint32_t scalar, std::string& output) {
    if (scalar <= 0x7fU) {
      output.push_back(static_cast<char>(scalar));
    } else if (scalar <= 0x7ffU) {
      output.push_back(static_cast<char>(0xc0U | (scalar >> 6U)));
      output.push_back(static_cast<char>(0x80U | (scalar & 0x3fU)));
    } else if (scalar <= 0xffffU) {
      output.push_back(static_cast<char>(0xe0U | (scalar >> 12U)));
      output.push_back(static_cast<char>(0x80U | ((scalar >> 6U) & 0x3fU)));
      output.push_back(static_cast<char>(0x80U | (scalar & 0x3fU)));
    } else {
      output.push_back(static_cast<char>(0xf0U | (scalar >> 18U)));
      output.push_back(static_cast<char>(0x80U | ((scalar >> 12U) & 0x3fU)));
      output.push_back(static_cast<char>(0x80U | ((scalar >> 6U) & 0x3fU)));
      output.push_back(static_cast<char>(0x80U | (scalar & 0x3fU)));
    }
  }

  static std::vector<std::uint16_t> utf16_units(const std::string_view value) {
    std::vector<std::uint16_t> units;
    units.reserve(value.size());
    std::size_t offset = 0U;
    while (offset < value.size()) {
      const auto first = static_cast<std::uint8_t>(value[offset]);
      std::uint32_t scalar = 0U;
      std::size_t width = 1U;
      if (first < 0x80U) {
        scalar = first;
      } else if (first < 0xe0U) {
        width = 2U;
        scalar = first & 0x1fU;
      } else if (first < 0xf0U) {
        width = 3U;
        scalar = first & 0x0fU;
      } else {
        width = 4U;
        scalar = first & 0x07U;
      }
      for (std::size_t index = 1U; index < width; ++index) {
        scalar = (scalar << 6U) |
                 (static_cast<std::uint8_t>(value[offset + index]) & 0x3fU);
      }
      offset += width;
      if (scalar <= 0xffffU) {
        units.push_back(static_cast<std::uint16_t>(scalar));
      } else {
        scalar -= 0x10000U;
        units.push_back(static_cast<std::uint16_t>(0xd800U + (scalar >> 10U)));
        units.push_back(static_cast<std::uint16_t>(0xdc00U + (scalar & 0x3ffU)));
      }
    }
    return units;
  }

  static bool utf16_less(const std::string& left, const std::string& right) {
    const auto left_units = utf16_units(left);
    const auto right_units = utf16_units(right);
    return std::lexicographical_compare(
        left_units.begin(), left_units.end(), right_units.begin(), right_units.end());
  }

  static void serialize_string(const std::string_view value, std::string& output) {
    static constexpr char hexadecimal[] = "0123456789abcdef";
    output.push_back('"');
    for (const char raw_byte : value) {
      const auto byte = static_cast<unsigned char>(raw_byte);
      switch (byte) {
        case '"':
          output.append("\\\"");
          break;
        case '\\':
          output.append("\\\\");
          break;
        case '\b':
          output.append("\\b");
          break;
        case '\t':
          output.append("\\t");
          break;
        case '\n':
          output.append("\\n");
          break;
        case '\f':
          output.append("\\f");
          break;
        case '\r':
          output.append("\\r");
          break;
        default:
          if (byte < 0x20U) {
            output.append("\\u00");
            output.push_back(hexadecimal[byte >> 4U]);
            output.push_back(hexadecimal[byte & 0x0fU]);
          } else {
            output.push_back(static_cast<char>(byte));
          }
          break;
      }
    }
    output.push_back('"');
  }

  static void serialize(const Value& value, std::string& output) {
    if (std::holds_alternative<std::nullptr_t>(value.storage)) {
      output.append("null");
    } else if (const auto* boolean = std::get_if<bool>(&value.storage)) {
      output.append(*boolean ? "true" : "false");
    } else if (const auto* integer = std::get_if<std::int64_t>(&value.storage)) {
      std::array<char, 32> buffer{};
      const auto conversion = std::to_chars(buffer.data(), buffer.data() + buffer.size(), *integer);
      output.append(buffer.data(), conversion.ptr);
    } else if (const auto* string = std::get_if<std::string>(&value.storage)) {
      serialize_string(*string, output);
    } else if (const auto* array = std::get_if<Array>(&value.storage)) {
      output.push_back('[');
      for (std::size_t index = 0U; index < array->size(); ++index) {
        if (index != 0U) {
          output.push_back(',');
        }
        serialize((*array)[index], output);
      }
      output.push_back(']');
    } else {
      const auto& object = std::get<Object>(value.storage);
      output.push_back('{');
      for (std::size_t index = 0U; index < object.size(); ++index) {
        if (index != 0U) {
          output.push_back(',');
        }
        serialize_string(object[index].first, output);
        output.push_back(':');
        serialize(object[index].second, output);
      }
      output.push_back('}');
    }
  }

  std::string_view input_;
  const CanonicalJsonLimits& limits_;
  std::size_t position_{0U};
  std::size_t value_count_{0U};
  JsonError error_{};
};

} // namespace

CanonicalJsonResult canonicalize_json(
    const std::string_view input,
    const CanonicalJsonLimits& limits) {
  return Parser(input, limits).run();
}

std::string_view json_error_name(const JsonErrorCode code) noexcept {
  switch (code) {
    case JsonErrorCode::none:
      return "none";
    case JsonErrorCode::input_too_large:
      return "input_too_large";
    case JsonErrorCode::depth_limit:
      return "depth_limit";
    case JsonErrorCode::value_limit:
      return "value_limit";
    case JsonErrorCode::string_limit:
      return "string_limit";
    case JsonErrorCode::unexpected_end:
      return "unexpected_end";
    case JsonErrorCode::unexpected_token:
      return "unexpected_token";
    case JsonErrorCode::trailing_data:
      return "trailing_data";
    case JsonErrorCode::invalid_utf8:
      return "invalid_utf8";
    case JsonErrorCode::invalid_escape:
      return "invalid_escape";
    case JsonErrorCode::invalid_surrogate:
      return "invalid_surrogate";
    case JsonErrorCode::invalid_number:
      return "invalid_number";
    case JsonErrorCode::unsupported_number:
      return "unsupported_number";
    case JsonErrorCode::duplicate_key:
      return "duplicate_key";
  }
  return "unknown";
}

} // namespace morphoia::core
