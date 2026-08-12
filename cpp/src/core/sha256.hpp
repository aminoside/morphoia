// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#ifndef MORPHOIA_CORE_SHA256_HPP
#define MORPHOIA_CORE_SHA256_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <string_view>

namespace morphoia::core {

struct Sha256Digest {
  std::array<std::uint8_t, 32> bytes{};

  [[nodiscard]] std::string hex() const;
  [[nodiscard]] static std::optional<Sha256Digest> from_hex(std::string_view value) noexcept;

  friend bool operator==(const Sha256Digest&, const Sha256Digest&) = default;
};

class Sha256 final {
 public:
  Sha256() noexcept;

  void update(std::span<const std::byte> bytes);
  void update(std::string_view bytes);

  [[nodiscard]] Sha256Digest finalize();
  [[nodiscard]] static Sha256Digest hash(std::span<const std::byte> bytes);
  [[nodiscard]] static Sha256Digest hash(std::string_view bytes);

 private:
  void transform(const std::byte* block) noexcept;

  std::array<std::uint32_t, 8> state_{};
  std::array<std::byte, 64> pending_{};
  std::uint64_t byte_count_{0};
  std::size_t pending_size_{0};
  bool finalized_{false};
};

} // namespace morphoia::core

#endif // MORPHOIA_CORE_SHA256_HPP
