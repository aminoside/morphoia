// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#include "core/sha256.hpp"

#include <algorithm>
#include <bit>
#include <cstring>
#include <limits>
#include <stdexcept>

namespace morphoia::core {
namespace {

constexpr std::array<std::uint32_t, 64> round_constants{
    0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U, 0x3956c25bU, 0x59f111f1U,
    0x923f82a4U, 0xab1c5ed5U, 0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U,
    0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U, 0xe49b69c1U, 0xefbe4786U,
    0x0fc19dc6U, 0x240ca1ccU, 0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
    0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U, 0xc6e00bf3U, 0xd5a79147U,
    0x06ca6351U, 0x14292967U, 0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U,
    0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U, 0xa2bfe8a1U, 0xa81a664bU,
    0xc24b8b70U, 0xc76c51a3U, 0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
    0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U, 0x391c0cb3U, 0x4ed8aa4aU,
    0x5b9cca4fU, 0x682e6ff3U, 0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
    0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U,
};

constexpr std::uint32_t choose(
    const std::uint32_t x,
    const std::uint32_t y,
    const std::uint32_t z) noexcept {
  return (x & y) ^ (~x & z);
}

constexpr std::uint32_t majority(
    const std::uint32_t x,
    const std::uint32_t y,
    const std::uint32_t z) noexcept {
  return (x & y) ^ (x & z) ^ (y & z);
}

constexpr std::uint8_t hex_value(const char value) noexcept {
  if (value >= '0' && value <= '9') {
    return static_cast<std::uint8_t>(value - '0');
  }
  if (value >= 'a' && value <= 'f') {
    return static_cast<std::uint8_t>(value - 'a' + 10);
  }
  return 0xffU;
}

} // namespace

std::string Sha256Digest::hex() const {
  static constexpr char alphabet[] = "0123456789abcdef";
  std::string result;
  result.resize(bytes.size() * 2U);
  for (std::size_t index = 0; index < bytes.size(); ++index) {
    result[index * 2U] = alphabet[bytes[index] >> 4U];
    result[index * 2U + 1U] = alphabet[bytes[index] & 0x0fU];
  }
  return result;
}

std::optional<Sha256Digest> Sha256Digest::from_hex(const std::string_view value) noexcept {
  if (value.size() != 64U) {
    return std::nullopt;
  }

  Sha256Digest digest;
  for (std::size_t index = 0; index < digest.bytes.size(); ++index) {
    const std::uint8_t high = hex_value(value[index * 2U]);
    const std::uint8_t low = hex_value(value[index * 2U + 1U]);
    if (high == 0xffU || low == 0xffU) {
      return std::nullopt;
    }
    digest.bytes[index] = static_cast<std::uint8_t>((high << 4U) | low);
  }
  return digest;
}

Sha256::Sha256() noexcept
    : state_{
          0x6a09e667U,
          0xbb67ae85U,
          0x3c6ef372U,
          0xa54ff53aU,
          0x510e527fU,
          0x9b05688cU,
          0x1f83d9abU,
          0x5be0cd19U,
      } {}

void Sha256::update(const std::span<const std::byte> bytes) {
  if (finalized_) {
    throw std::logic_error("SHA-256 update after finalize");
  }
  constexpr std::uint64_t maximum_bytes = std::numeric_limits<std::uint64_t>::max() / 8U;
  if (bytes.size() > maximum_bytes - byte_count_) {
    throw std::length_error("SHA-256 input exceeds the 64-bit length domain");
  }
  byte_count_ += static_cast<std::uint64_t>(bytes.size());

  std::size_t consumed = 0U;
  if (pending_size_ != 0U) {
    const std::size_t copied = std::min(bytes.size(), pending_.size() - pending_size_);
    if (copied != 0U) {
      std::memcpy(pending_.data() + pending_size_, bytes.data(), copied);
    }
    pending_size_ += copied;
    consumed += copied;
    if (pending_size_ == pending_.size()) {
      transform(pending_.data());
      pending_size_ = 0U;
    }
  }

  while (bytes.size() - consumed >= pending_.size()) {
    transform(bytes.data() + consumed);
    consumed += pending_.size();
  }

  const std::size_t remaining = bytes.size() - consumed;
  if (remaining != 0U) {
    std::memcpy(pending_.data(), bytes.data() + consumed, remaining);
    pending_size_ = remaining;
  }
}

void Sha256::update(const std::string_view bytes) {
  update(std::as_bytes(std::span(bytes.data(), bytes.size())));
}

Sha256Digest Sha256::finalize() {
  if (finalized_) {
    throw std::logic_error("SHA-256 finalize called more than once");
  }
  finalized_ = true;

  const std::uint64_t bit_count = byte_count_ * 8U;
  pending_[pending_size_++] = std::byte{0x80U};
  if (pending_size_ > 56U) {
    std::fill(pending_.begin() + static_cast<std::ptrdiff_t>(pending_size_), pending_.end(), std::byte{});
    transform(pending_.data());
    pending_size_ = 0U;
  }
  std::fill(
      pending_.begin() + static_cast<std::ptrdiff_t>(pending_size_),
      pending_.begin() + 56,
      std::byte{});
  for (std::size_t index = 0; index < 8U; ++index) {
    pending_[56U + index] =
        static_cast<std::byte>((bit_count >> ((7U - index) * 8U)) & 0xffU);
  }
  transform(pending_.data());

  Sha256Digest digest;
  for (std::size_t word = 0; word < state_.size(); ++word) {
    for (std::size_t byte = 0; byte < 4U; ++byte) {
      digest.bytes[word * 4U + byte] =
          static_cast<std::uint8_t>(state_[word] >> ((3U - byte) * 8U));
    }
  }
  return digest;
}

Sha256Digest Sha256::hash(const std::span<const std::byte> bytes) {
  Sha256 hash;
  hash.update(bytes);
  return hash.finalize();
}

Sha256Digest Sha256::hash(const std::string_view bytes) {
  Sha256 hash;
  hash.update(bytes);
  return hash.finalize();
}

void Sha256::transform(const std::byte* const block) noexcept {
  std::array<std::uint32_t, 64> schedule{};
  for (std::size_t index = 0; index < 16U; ++index) {
    schedule[index] =
        (std::to_integer<std::uint32_t>(block[index * 4U]) << 24U) |
        (std::to_integer<std::uint32_t>(block[index * 4U + 1U]) << 16U) |
        (std::to_integer<std::uint32_t>(block[index * 4U + 2U]) << 8U) |
        std::to_integer<std::uint32_t>(block[index * 4U + 3U]);
  }
  for (std::size_t index = 16U; index < schedule.size(); ++index) {
    const std::uint32_t s0 = std::rotr(schedule[index - 15U], 7) ^
                             std::rotr(schedule[index - 15U], 18) ^
                             (schedule[index - 15U] >> 3U);
    const std::uint32_t s1 = std::rotr(schedule[index - 2U], 17) ^
                             std::rotr(schedule[index - 2U], 19) ^
                             (schedule[index - 2U] >> 10U);
    schedule[index] = schedule[index - 16U] + s0 + schedule[index - 7U] + s1;
  }

  std::uint32_t a = state_[0];
  std::uint32_t b = state_[1];
  std::uint32_t c = state_[2];
  std::uint32_t d = state_[3];
  std::uint32_t e = state_[4];
  std::uint32_t f = state_[5];
  std::uint32_t g = state_[6];
  std::uint32_t h = state_[7];

  for (std::size_t index = 0; index < schedule.size(); ++index) {
    const std::uint32_t sigma1 = std::rotr(e, 6) ^ std::rotr(e, 11) ^ std::rotr(e, 25);
    const std::uint32_t temporary1 =
        h + sigma1 + choose(e, f, g) + round_constants[index] + schedule[index];
    const std::uint32_t sigma0 = std::rotr(a, 2) ^ std::rotr(a, 13) ^ std::rotr(a, 22);
    const std::uint32_t temporary2 = sigma0 + majority(a, b, c);
    h = g;
    g = f;
    f = e;
    e = d + temporary1;
    d = c;
    c = b;
    b = a;
    a = temporary1 + temporary2;
  }

  state_[0] += a;
  state_[1] += b;
  state_[2] += c;
  state_[3] += d;
  state_[4] += e;
  state_[5] += f;
  state_[6] += g;
  state_[7] += h;
}

} // namespace morphoia::core
