// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#ifndef MORPHOIA_CORE_POSIX_CAS_HPP
#define MORPHOIA_CORE_POSIX_CAS_HPP

#include "core/sha256.hpp"

#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <string_view>

namespace morphoia::core {

enum class CasErrorCode {
  none,
  invalid_argument,
  unsafe_path,
  invalid_media_type,
  invalid_reference,
  not_found,
  size_limit,
  io_error,
  integrity_error,
  consumer_rejected,
};

struct CasError {
  CasErrorCode code{CasErrorCode::none};
  int system_error{0};
  std::string message;
};

struct BlobReference {
  Sha256Digest digest;
  std::uint64_t size{0U};
  std::string media_type;
  std::string uri;

  friend bool operator==(const BlobReference&, const BlobReference&) = default;
};

struct CasPutResult {
  BlobReference reference;
  CasError error;

  [[nodiscard]] explicit operator bool() const noexcept {
    return error.code == CasErrorCode::none;
  }
};

struct CasReadResult {
  std::uint64_t size{0U};
  CasError error;

  [[nodiscard]] explicit operator bool() const noexcept {
    return error.code == CasErrorCode::none;
  }
};

class PosixCas;

struct PosixCasOpenResult {
  std::unique_ptr<PosixCas> store;
  CasError error;

  [[nodiscard]] explicit operator bool() const noexcept {
    return store != nullptr && error.code == CasErrorCode::none;
  }
};

class PosixCas final {
 public:
  using Sink = std::function<bool(std::span<const std::byte>)>;

  static constexpr std::uint64_t maximum_sha256_bytes = UINT64_MAX / 8U;
  static constexpr std::uint64_t maximum_reference_bytes = UINT64_C(9007199254740991);

  [[nodiscard]] static PosixCasOpenResult open(std::string_view absolute_root);

  ~PosixCas();
  PosixCas(const PosixCas&) = delete;
  PosixCas& operator=(const PosixCas&) = delete;
  PosixCas(PosixCas&&) = delete;
  PosixCas& operator=(PosixCas&&) = delete;

  [[nodiscard]] CasPutResult put(
      std::span<const std::byte> bytes,
      std::string_view media_type,
      std::uint64_t maximum_bytes = maximum_reference_bytes);

  [[nodiscard]] CasPutResult put_file(
      std::string_view absolute_input_path,
      std::string_view media_type,
      std::uint64_t maximum_bytes = maximum_reference_bytes);

  [[nodiscard]] CasPutResult put_file_verified(
      std::string_view absolute_input_path,
      std::string_view media_type,
      const Sha256Digest& expected_digest,
      std::uint64_t expected_size,
      std::uint64_t maximum_bytes = maximum_reference_bytes);

  /* The sink is called only after a complete size and digest verification. */
  [[nodiscard]] CasReadResult read_verified(
      const BlobReference& reference,
      const Sink& sink,
      std::uint64_t maximum_bytes = maximum_reference_bytes) const;

  [[nodiscard]] CasReadResult verify(
      const BlobReference& reference,
      std::uint64_t maximum_bytes = maximum_reference_bytes) const;

  [[nodiscard]] static std::string uri_for(const Sha256Digest& digest);
  [[nodiscard]] static std::optional<Sha256Digest> digest_from_uri(
      std::string_view uri) noexcept;
  [[nodiscard]] static bool valid_media_type(std::string_view media_type) noexcept;

 private:
  using Reader = std::function<std::ptrdiff_t(std::span<std::byte>)>;
  struct ExpectedBlob {
    Sha256Digest digest;
    std::uint64_t size;
  };

  explicit PosixCas(int root_fd) noexcept : root_fd_(root_fd) {}

  [[nodiscard]] CasPutResult publish(
      const Reader& reader,
      std::string_view media_type,
      std::uint64_t maximum_bytes,
      const std::optional<ExpectedBlob>& expected = std::nullopt);

  [[nodiscard]] CasPutResult put_file_internal(
      std::string_view absolute_input_path,
      std::string_view media_type,
      std::uint64_t maximum_bytes,
      const std::optional<ExpectedBlob>& expected);

  int root_fd_{-1};
};

[[nodiscard]] std::string_view cas_error_name(CasErrorCode code) noexcept;

} // namespace morphoia::core

#endif // MORPHOIA_CORE_POSIX_CAS_HPP
