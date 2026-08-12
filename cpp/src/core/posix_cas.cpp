// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#include "core/posix_cas.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <limits>
#include <string>
#include <string_view>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <unistd.h>
#include <utility>
#include <vector>

namespace morphoia::core {
namespace {

constexpr mode_t directory_mode = S_IRWXU;
constexpr mode_t temporary_mode = S_IRUSR | S_IWUSR;
constexpr mode_t object_mode = S_IRUSR | S_IRGRP | S_IROTH;
constexpr std::size_t transfer_buffer_size = 64U * 1024U;
std::atomic<std::uint64_t> temporary_counter{0U};

#ifndef RENAME_NOREPLACE
#  define RENAME_NOREPLACE (1U << 0U)
#endif

class UniqueFd final {
 public:
  UniqueFd() noexcept = default;
  explicit UniqueFd(const int value) noexcept : value_(value) {}
  ~UniqueFd() {
    if (value_ >= 0) {
      ::close(value_);
    }
  }

  UniqueFd(const UniqueFd&) = delete;
  UniqueFd& operator=(const UniqueFd&) = delete;

  UniqueFd(UniqueFd&& other) noexcept : value_(std::exchange(other.value_, -1)) {}
  UniqueFd& operator=(UniqueFd&& other) noexcept {
    if (this != &other) {
      if (value_ >= 0) {
        ::close(value_);
      }
      value_ = std::exchange(other.value_, -1);
    }
    return *this;
  }

  [[nodiscard]] int get() const noexcept {
    return value_;
  }

  [[nodiscard]] int release() noexcept {
    return std::exchange(value_, -1);
  }

 private:
  int value_{-1};
};

class TemporaryEntry final {
 public:
  TemporaryEntry(const int directory_fd, std::string name)
      : directory_fd_(directory_fd), name_(std::move(name)) {}
  ~TemporaryEntry() {
    if (active_) {
      if (::unlinkat(directory_fd_, name_.c_str(), 0) == 0) {
        static_cast<void>(::fsync(directory_fd_));
      }
    }
  }

  TemporaryEntry(const TemporaryEntry&) = delete;
  TemporaryEntry& operator=(const TemporaryEntry&) = delete;

  [[nodiscard]] bool remove() noexcept {
    if (active_) {
      const int result = ::unlinkat(directory_fd_, name_.c_str(), 0);
      active_ = false;
      return result == 0 || errno == ENOENT;
    }
    return true;
  }

  void disarm() noexcept {
    active_ = false;
  }

 private:
  int directory_fd_;
  std::string name_;
  bool active_{true};
};

CasError error(const CasErrorCode code, std::string message, const int system_error = 0) {
  return {code, system_error, std::move(message)};
}

bool has_embedded_nul(const std::string_view value) noexcept {
  return value.find('\0') != std::string_view::npos;
}

bool safe_absolute_path(const std::string_view value) noexcept {
  if (value.size() < 2U || value.front() != '/' || value.back() == '/' ||
      has_embedded_nul(value)) {
    return false;
  }
  std::size_t component_start = 1U;
  while (component_start < value.size()) {
    const std::size_t separator = value.find('/', component_start);
    const std::size_t component_end =
        separator == std::string_view::npos ? value.size() : separator;
    const std::string_view component =
        value.substr(component_start, component_end - component_start);
    if (component.empty() || component == "." || component == "..") {
      return false;
    }
    if (separator == std::string_view::npos) {
      break;
    }
    component_start = separator + 1U;
  }
  return true;
}

std::vector<std::string> absolute_path_components(const std::string_view value) {
  std::vector<std::string> components;
  std::size_t start = 1U;
  while (start < value.size()) {
    const std::size_t separator = value.find('/', start);
    const std::size_t end = separator == std::string_view::npos ? value.size() : separator;
    components.emplace_back(value.substr(start, end - start));
    if (separator == std::string_view::npos) {
      break;
    }
    start = separator + 1U;
  }
  return components;
}

bool secure_managed_directory(const int fd, CasError& output_error) {
  struct stat metadata {};
  if (::fstat(fd, &metadata) != 0) {
    output_error = error(CasErrorCode::io_error, "cannot inspect managed CAS directory", errno);
    return false;
  }
  if (!S_ISDIR(metadata.st_mode) || metadata.st_uid != ::geteuid() ||
      (metadata.st_mode & 07777) != directory_mode) {
    output_error = error(
        CasErrorCode::unsafe_path,
        "managed CAS directory must be owner-controlled with mode 0700");
    return false;
  }
  return true;
}

UniqueFd open_absolute_parent(
    const std::string_view path,
    std::string& leaf,
    CasError& output_error) {
  const auto components = absolute_path_components(path);
  if (components.empty()) {
    output_error = error(CasErrorCode::unsafe_path, "absolute path has no leaf component");
    return {};
  }
  leaf = components.back();
  UniqueFd current(::open("/", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC));
  if (current.get() < 0) {
    output_error = error(CasErrorCode::io_error, "cannot open filesystem root", errno);
    return {};
  }
  for (std::size_t index = 0U; index + 1U < components.size(); ++index) {
    const int next = ::openat(
        current.get(),
        components[index].c_str(),
        O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (next < 0) {
      output_error = error(
          CasErrorCode::unsafe_path,
          "cannot traverse an absolute path without following symlinks",
          errno);
      return {};
    }
    current = UniqueFd(next);
  }
  return current;
}

UniqueFd open_or_create_absolute_directory(
    const std::string_view path,
    CasError& output_error) {
  std::string leaf;
  auto parent = open_absolute_parent(path, leaf, output_error);
  if (parent.get() < 0) {
    return {};
  }
  if (::mkdirat(parent.get(), leaf.c_str(), directory_mode) == 0) {
    if (::fsync(parent.get()) != 0) {
      output_error =
          error(CasErrorCode::io_error, "cannot synchronize parent of CAS root", errno);
      return {};
    }
  } else if (errno != EEXIST) {
    output_error = error(CasErrorCode::io_error, "cannot create CAS root", errno);
    return {};
  }
  const int root = ::openat(
      parent.get(), leaf.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (root < 0) {
    output_error = error(CasErrorCode::unsafe_path, "cannot open CAS root without symlinks", errno);
    return {};
  }
  UniqueFd result(root);
  if (!secure_managed_directory(result.get(), output_error)) {
    return {};
  }
  return result;
}

UniqueFd open_absolute_regular_file(
    const std::string_view path,
    CasError& output_error) {
  std::string leaf;
  auto parent = open_absolute_parent(path, leaf, output_error);
  if (parent.get() < 0) {
    return {};
  }
  const int input = ::openat(
      parent.get(), leaf.c_str(), O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
  if (input < 0) {
    output_error = error(
        CasErrorCode::unsafe_path,
        "cannot open source without following symlinks",
        errno);
  }
  return UniqueFd(input);
}

UniqueFd open_directory_at(const int parent_fd, const char* const name, CasError& output_error) {
  const int value = ::openat(parent_fd, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (value < 0) {
    const int saved = errno;
    output_error = error(
        saved == ENOENT ? CasErrorCode::not_found : CasErrorCode::unsafe_path,
        std::string("cannot open CAS directory '") + name + "'",
        saved);
    return {};
  }
  UniqueFd result(value);
  if (!secure_managed_directory(result.get(), output_error)) {
    return {};
  }
  return result;
}

UniqueFd ensure_directory_at(
    const int parent_fd,
    const char* const name,
    CasError& output_error) {
  if (::mkdirat(parent_fd, name, directory_mode) == 0) {
    if (::fsync(parent_fd) != 0) {
      output_error = error(
          CasErrorCode::io_error,
          std::string("cannot synchronize parent of CAS directory '") + name + "'",
          errno);
      return {};
    }
  } else if (errno != EEXIST) {
    const int saved = errno;
    output_error = error(
        CasErrorCode::io_error,
        std::string("cannot create CAS directory '") + name + "'",
        saved);
    return {};
  }
  auto result = open_directory_at(parent_fd, name, output_error);
  return result;
}

bool write_all(const int fd, const std::span<const std::byte> bytes, CasError& output_error) {
  std::size_t written = 0U;
  while (written < bytes.size()) {
    const ssize_t result = ::write(fd, bytes.data() + written, bytes.size() - written);
    if (result < 0 && errno == EINTR) {
      continue;
    }
    if (result <= 0) {
      const int saved = result < 0 ? errno : EIO;
      output_error = error(CasErrorCode::io_error, "cannot write CAS temporary object", saved);
      return false;
    }
    written += static_cast<std::size_t>(result);
  }
  return true;
}

int rename_no_replace(
    const int old_directory,
    const char* const old_name,
    const int new_directory,
    const char* const new_name) noexcept {
#if defined(SYS_renameat2)
  return static_cast<int>(::syscall(
      SYS_renameat2,
      old_directory,
      old_name,
      new_directory,
      new_name,
      static_cast<unsigned int>(RENAME_NOREPLACE)));
#else
  static_cast<void>(old_directory);
  static_cast<void>(old_name);
  static_cast<void>(new_directory);
  static_cast<void>(new_name);
  errno = ENOSYS;
  return -1;
#endif
}

UniqueFd create_unlinked_snapshot(const int root_fd, CasError& output_error) {
  auto temporary_directory = open_directory_at(root_fd, "tmp", output_error);
  if (temporary_directory.get() < 0) {
    return {};
  }
  for (std::size_t attempt = 0U; attempt < 128U; ++attempt) {
    const std::uint64_t sequence =
        temporary_counter.fetch_add(1U, std::memory_order_relaxed);
    const std::string name =
        "read-" + std::to_string(static_cast<long long>(::getpid())) + "-" +
        std::to_string(sequence) + ".private";
    UniqueFd snapshot(::openat(
        temporary_directory.get(),
        name.c_str(),
        O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC,
        temporary_mode));
    if (snapshot.get() < 0) {
      if (errno == EEXIST) {
        continue;
      }
      output_error =
          error(CasErrorCode::io_error, "cannot create verified-read snapshot", errno);
      return {};
    }
    if (::unlinkat(temporary_directory.get(), name.c_str(), 0) != 0) {
      output_error =
          error(CasErrorCode::io_error, "cannot unlink verified-read snapshot", errno);
      return {};
    }
    return snapshot;
  }
  output_error =
      error(CasErrorCode::io_error, "cannot allocate verified-read snapshot", EEXIST);
  return {};
}

bool seek_to_start(const int fd, CasError& output_error) {
  if (::lseek(fd, 0, SEEK_SET) < 0) {
    output_error = error(CasErrorCode::io_error, "cannot rewind CAS object", errno);
    return false;
  }
  return true;
}

bool hash_fd(
    const int fd,
    const std::uint64_t maximum_bytes,
    Sha256Digest& digest,
    std::uint64_t& size,
    CasError& output_error) {
  if (!seek_to_start(fd, output_error)) {
    return false;
  }
  std::array<std::byte, transfer_buffer_size> buffer{};
  Sha256 hash;
  size = 0U;
  while (true) {
    const ssize_t result = ::read(fd, buffer.data(), buffer.size());
    if (result < 0 && errno == EINTR) {
      continue;
    }
    if (result < 0) {
      output_error = error(CasErrorCode::io_error, "cannot read CAS object", errno);
      return false;
    }
    if (result == 0) {
      break;
    }
    const auto count = static_cast<std::uint64_t>(result);
    if (count > maximum_bytes - size) {
      output_error = error(CasErrorCode::size_limit, "CAS object exceeds its byte limit");
      return false;
    }
    size += count;
    hash.update(std::span(buffer.data(), static_cast<std::size_t>(result)));
  }
  digest = hash.finalize();
  return true;
}

bool regular_file(
    const int fd,
    std::uint64_t& size,
    CasError& output_error,
    const bool published_object = false) {
  struct stat metadata {};
  if (::fstat(fd, &metadata) != 0) {
    output_error = error(CasErrorCode::io_error, "cannot inspect CAS object", errno);
    return false;
  }
  if (!S_ISREG(metadata.st_mode) || metadata.st_size < 0) {
    output_error = error(
        CasErrorCode::unsafe_path,
        "CAS file must be regular and nonnegative in size");
    return false;
  }
  if (published_object &&
      (metadata.st_nlink != 1 || metadata.st_uid != ::geteuid() ||
       (metadata.st_mode & 07777) != object_mode)) {
    output_error = error(
        CasErrorCode::unsafe_path,
        "published CAS object must be owner-controlled, read-only, and singly linked");
    return false;
  }
  size = static_cast<std::uint64_t>(metadata.st_size);
  return true;
}

UniqueFd open_object(
    const int root_fd,
    const Sha256Digest& digest,
    CasError& output_error) {
  const std::string hexadecimal = digest.hex();
  auto objects = open_directory_at(root_fd, "objects", output_error);
  if (objects.get() < 0) {
    return {};
  }
  auto algorithm = open_directory_at(objects.get(), "sha256", output_error);
  if (algorithm.get() < 0) {
    return {};
  }
  const std::string prefix = hexadecimal.substr(0U, 2U);
  auto bucket = open_directory_at(algorithm.get(), prefix.c_str(), output_error);
  if (bucket.get() < 0) {
    return {};
  }
  const std::string name = hexadecimal.substr(2U);
  const int object = ::openat(
      bucket.get(),
      name.c_str(),
      O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
  if (object < 0) {
    const int saved = errno;
    output_error = error(
        saved == ENOENT ? CasErrorCode::not_found : CasErrorCode::unsafe_path,
        "cannot open CAS object",
        saved);
    return {};
  }
  UniqueFd result(object);
  std::uint64_t ignored_size = 0U;
  if (!regular_file(result.get(), ignored_size, output_error, true)) {
    return {};
  }
  return result;
}

bool validate_reference(
    const BlobReference& reference,
    const std::uint64_t maximum_bytes,
    CasError& output_error) {
  if (!PosixCas::valid_media_type(reference.media_type)) {
    output_error = error(CasErrorCode::invalid_media_type, "CAS reference has an invalid media type");
    return false;
  }
  if (reference.uri != PosixCas::uri_for(reference.digest)) {
    output_error = error(CasErrorCode::invalid_reference, "CAS URI does not match its SHA-256 digest");
    return false;
  }
  if (maximum_bytes > PosixCas::maximum_reference_bytes ||
      reference.size > PosixCas::maximum_reference_bytes ||
      reference.size > maximum_bytes) {
    output_error = error(CasErrorCode::size_limit, "declared CAS object size exceeds its byte limit");
    return false;
  }
  return true;
}

bool verify_open_object(
    const int fd,
    const BlobReference& reference,
    const std::uint64_t maximum_bytes,
    CasError& output_error) {
  std::uint64_t stat_size = 0U;
  if (!regular_file(fd, stat_size, output_error, true)) {
    return false;
  }
  if (stat_size != reference.size) {
    output_error = error(CasErrorCode::integrity_error, "CAS object size differs from its reference");
    return false;
  }
  Sha256Digest actual_digest;
  std::uint64_t actual_size = 0U;
  if (!hash_fd(fd, maximum_bytes, actual_digest, actual_size, output_error)) {
    return false;
  }
  if (actual_size != reference.size || actual_digest != reference.digest) {
    output_error = error(CasErrorCode::integrity_error, "CAS object digest differs from its reference");
    return false;
  }
  return true;
}

} // namespace

PosixCasOpenResult PosixCas::open(const std::string_view absolute_root) {
  if (!safe_absolute_path(absolute_root)) {
    return {
        nullptr,
        error(
            CasErrorCode::unsafe_path,
            "CAS root must be an absolute normalized NUL-free path")};
  }
  CasError directory_error;
  auto root = open_or_create_absolute_directory(absolute_root, directory_error);
  if (root.get() < 0) {
    return {nullptr, std::move(directory_error)};
  }

  auto objects = ensure_directory_at(root.get(), "objects", directory_error);
  if (objects.get() < 0) {
    return {nullptr, std::move(directory_error)};
  }
  auto algorithm = ensure_directory_at(objects.get(), "sha256", directory_error);
  if (algorithm.get() < 0) {
    return {nullptr, std::move(directory_error)};
  }
  auto temporary = ensure_directory_at(root.get(), "tmp", directory_error);
  if (temporary.get() < 0) {
    return {nullptr, std::move(directory_error)};
  }
  if (::fsync(root.get()) != 0) {
    return {nullptr, error(CasErrorCode::io_error, "cannot synchronize CAS root", errno)};
  }
  return {std::unique_ptr<PosixCas>(new PosixCas(root.release())), {}};
}

PosixCas::~PosixCas() {
  if (root_fd_ >= 0) {
    ::close(root_fd_);
  }
}

CasPutResult PosixCas::put(
    const std::span<const std::byte> bytes,
    const std::string_view media_type,
    const std::uint64_t maximum_bytes) {
  std::size_t offset = 0U;
  const Reader reader = [&bytes, &offset](const std::span<std::byte> output) -> std::ptrdiff_t {
    const std::size_t count = std::min(output.size(), bytes.size() - offset);
    if (count != 0U) {
      std::memcpy(output.data(), bytes.data() + offset, count);
      offset += count;
    }
    return static_cast<std::ptrdiff_t>(count);
  };
  return publish(reader, media_type, maximum_bytes);
}

CasPutResult PosixCas::put_file(
    const std::string_view absolute_input_path,
    const std::string_view media_type,
    const std::uint64_t maximum_bytes) {
  return put_file_internal(absolute_input_path, media_type, maximum_bytes, std::nullopt);
}

CasPutResult PosixCas::put_file_verified(
    const std::string_view absolute_input_path,
    const std::string_view media_type,
    const Sha256Digest& expected_digest,
    const std::uint64_t expected_size,
    const std::uint64_t maximum_bytes) {
  return put_file_internal(
      absolute_input_path,
      media_type,
      maximum_bytes,
      ExpectedBlob{expected_digest, expected_size});
}

CasPutResult PosixCas::put_file_internal(
    const std::string_view absolute_input_path,
    const std::string_view media_type,
    const std::uint64_t maximum_bytes,
    const std::optional<ExpectedBlob>& expected) {
  if (!safe_absolute_path(absolute_input_path)) {
    return {
        {},
        error(
            CasErrorCode::unsafe_path,
            "CAS input must be an absolute normalized NUL-free path")};
  }
  CasError input_error;
  auto input = open_absolute_regular_file(absolute_input_path, input_error);
  if (input.get() < 0) {
    return {{}, std::move(input_error)};
  }
  std::uint64_t input_size = 0U;
  if (!regular_file(input.get(), input_size, input_error)) {
    return {{}, std::move(input_error)};
  }
  if (input_size > maximum_bytes) {
    return {{}, error(CasErrorCode::size_limit, "CAS input exceeds its byte limit")};
  }
  if (expected.has_value() && expected->size != input_size) {
    return {
        {},
        error(CasErrorCode::integrity_error, "CAS input size differs from the expected transfer size")};
  }

  int reader_error = 0;
  const Reader reader = [&input, &reader_error](const std::span<std::byte> output) -> std::ptrdiff_t {
    while (true) {
      const ssize_t result = ::read(input.get(), output.data(), output.size());
      if (result < 0 && errno == EINTR) {
        continue;
      }
      if (result < 0) {
        reader_error = errno;
      }
      return static_cast<std::ptrdiff_t>(result);
    }
  };
  auto result = publish(reader, media_type, maximum_bytes, expected);
  if (!result && result.error.code == CasErrorCode::io_error && reader_error != 0) {
    result.error.system_error = reader_error;
  }
  return result;
}

CasPutResult PosixCas::publish(
    const Reader& reader,
    const std::string_view media_type,
    const std::uint64_t maximum_bytes,
    const std::optional<ExpectedBlob>& expected) {
  if (!valid_media_type(media_type)) {
    return {{}, error(CasErrorCode::invalid_media_type, "invalid canonical media type")};
  }
  if (maximum_bytes > maximum_reference_bytes) {
    return {
        {},
        error(
            CasErrorCode::invalid_argument,
            "byte limit exceeds the exact integer domain of canonical JSON references")};
  }

  CasError directory_error;
  auto temporary_directory = open_directory_at(root_fd_, "tmp", directory_error);
  if (temporary_directory.get() < 0) {
    return {{}, std::move(directory_error)};
  }

  std::string temporary_name;
  UniqueFd temporary;
  for (std::size_t attempt = 0U; attempt < 128U; ++attempt) {
    const std::uint64_t sequence = temporary_counter.fetch_add(1U, std::memory_order_relaxed);
    temporary_name = "morphoia-" + std::to_string(static_cast<long long>(::getpid())) + "-" +
                     std::to_string(sequence) + ".partial";
    temporary = UniqueFd(::openat(
        temporary_directory.get(),
        temporary_name.c_str(),
        O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC,
        temporary_mode));
    if (temporary.get() >= 0) {
      break;
    }
    if (errno != EEXIST) {
      return {{}, error(CasErrorCode::io_error, "cannot create CAS temporary object", errno)};
    }
  }
  if (temporary.get() < 0) {
    return {{}, error(CasErrorCode::io_error, "cannot allocate a unique CAS temporary object", EEXIST)};
  }
  TemporaryEntry cleanup(temporary_directory.get(), temporary_name);

  std::array<std::byte, transfer_buffer_size> buffer{};
  Sha256 hash;
  std::uint64_t size = 0U;
  while (true) {
    std::ptrdiff_t read_count = 0;
    try {
      read_count = reader(buffer);
    } catch (...) {
      return {{}, error(CasErrorCode::io_error, "CAS reader threw an exception")};
    }
    if (read_count < 0) {
      return {{}, error(CasErrorCode::io_error, "cannot read CAS source")};
    }
    if (read_count == 0) {
      break;
    }
    const auto count = static_cast<std::uint64_t>(read_count);
    if (count > buffer.size()) {
      return {{}, error(CasErrorCode::io_error, "CAS reader returned an impossible byte count")};
    }
    if (count > maximum_bytes - size) {
      return {{}, error(CasErrorCode::size_limit, "CAS source exceeds its byte limit")};
    }
    const auto chunk = std::span(buffer.data(), static_cast<std::size_t>(count));
    hash.update(chunk);
    CasError write_error;
    if (!write_all(temporary.get(), chunk, write_error)) {
      return {{}, std::move(write_error)};
    }
    size += count;
  }
  const Sha256Digest digest = hash.finalize();
  if (expected.has_value() &&
      (expected->size != size || expected->digest != digest)) {
    return {
        {},
        error(
            CasErrorCode::integrity_error,
            "CAS transfer bytes differ from the expected size or SHA-256 digest")};
  }

  if (::fsync(temporary.get()) != 0) {
    return {{}, error(CasErrorCode::io_error, "cannot synchronize CAS temporary object", errno)};
  }
  if (::fchmod(temporary.get(), object_mode) != 0) {
    return {{}, error(CasErrorCode::io_error, "cannot make CAS object immutable", errno)};
  }
  if (::fsync(temporary.get()) != 0) {
    return {{}, error(CasErrorCode::io_error, "cannot synchronize CAS object metadata", errno)};
  }

  auto objects = open_directory_at(root_fd_, "objects", directory_error);
  if (objects.get() < 0) {
    return {{}, std::move(directory_error)};
  }
  auto algorithm = open_directory_at(objects.get(), "sha256", directory_error);
  if (algorithm.get() < 0) {
    return {{}, std::move(directory_error)};
  }
  const std::string hexadecimal = digest.hex();
  const std::string prefix = hexadecimal.substr(0U, 2U);
  auto bucket = ensure_directory_at(algorithm.get(), prefix.c_str(), directory_error);
  if (bucket.get() < 0) {
    return {{}, std::move(directory_error)};
  }
  const std::string object_name = hexadecimal.substr(2U);
  if (rename_no_replace(
          temporary_directory.get(),
          temporary_name.c_str(),
          bucket.get(),
          object_name.c_str()) != 0) {
    const int saved = errno;
    if (saved != EEXIST) {
      return {
          {},
          error(
              CasErrorCode::io_error,
              saved == ENOSYS
                  ? "atomic no-clobber rename is unavailable for this POSIX CAS backend"
                  : "cannot atomically publish CAS object",
              saved)};
    }
    CasError existing_error;
    auto existing = open_object(root_fd_, digest, existing_error);
    if (existing.get() < 0) {
      return {{}, std::move(existing_error)};
    }
    const BlobReference existing_reference{
        digest, size, std::string(media_type), uri_for(digest)};
    if (!verify_open_object(
            existing.get(), existing_reference, maximum_bytes, existing_error)) {
      return {{}, error(CasErrorCode::integrity_error, "existing CAS identity contains different bytes", existing_error.system_error)};
    }
    if (!cleanup.remove()) {
      return {{}, error(CasErrorCode::io_error, "cannot remove redundant CAS temporary object", errno)};
    }
  } else {
    cleanup.disarm();
  }
  if (::fsync(bucket.get()) != 0) {
    return {{}, error(CasErrorCode::io_error, "cannot synchronize published CAS directory", errno)};
  }
  if (::fsync(temporary_directory.get()) != 0) {
    return {{}, error(CasErrorCode::io_error, "cannot synchronize CAS temporary directory", errno)};
  }

  return {{digest, size, std::string(media_type), uri_for(digest)}, {}};
}

CasReadResult PosixCas::verify(
    const BlobReference& reference,
    const std::uint64_t maximum_bytes) const {
  CasError reference_error;
  if (!validate_reference(reference, maximum_bytes, reference_error)) {
    return {0U, std::move(reference_error)};
  }
  auto object = open_object(root_fd_, reference.digest, reference_error);
  if (object.get() < 0) {
    return {0U, std::move(reference_error)};
  }
  if (!verify_open_object(object.get(), reference, maximum_bytes, reference_error)) {
    return {0U, std::move(reference_error)};
  }
  return {reference.size, {}};
}

CasReadResult PosixCas::read_verified(
    const BlobReference& reference,
    const Sink& sink,
    const std::uint64_t maximum_bytes) const {
  if (!sink) {
    return {0U, error(CasErrorCode::invalid_argument, "CAS read sink is empty")};
  }
  CasError reference_error;
  if (!validate_reference(reference, maximum_bytes, reference_error)) {
    return {0U, std::move(reference_error)};
  }
  auto object = open_object(root_fd_, reference.digest, reference_error);
  if (object.get() < 0) {
    return {0U, std::move(reference_error)};
  }
  std::uint64_t object_size = 0U;
  if (!regular_file(object.get(), object_size, reference_error, true)) {
    return {0U, std::move(reference_error)};
  }
  if (object_size != reference.size) {
    return {
        0U,
        error(CasErrorCode::integrity_error, "CAS object size differs from its reference")};
  }

  auto snapshot = create_unlinked_snapshot(root_fd_, reference_error);
  if (snapshot.get() < 0) {
    return {0U, std::move(reference_error)};
  }

  std::array<std::byte, transfer_buffer_size> buffer{};
  Sha256 snapshot_hash;
  std::uint64_t snapshot_size = 0U;
  while (true) {
    const ssize_t result = ::read(object.get(), buffer.data(), buffer.size());
    if (result < 0 && errno == EINTR) {
      continue;
    }
    if (result < 0) {
      return {0U, error(CasErrorCode::io_error, "cannot stage CAS object for verified read", errno)};
    }
    if (result == 0) {
      break;
    }
    const auto count = static_cast<std::size_t>(result);
    const auto chunk = std::span(buffer.data(), count);
    if (static_cast<std::uint64_t>(count) > maximum_bytes - snapshot_size) {
      return {0U, error(CasErrorCode::size_limit, "CAS object exceeds its byte limit")};
    }
    snapshot_hash.update(chunk);
    if (!write_all(snapshot.get(), chunk, reference_error)) {
      return {0U, std::move(reference_error)};
    }
    snapshot_size += static_cast<std::uint64_t>(count);
  }
  if (snapshot_size != reference.size || snapshot_hash.finalize() != reference.digest) {
    return {
        0U,
        error(CasErrorCode::integrity_error, "CAS object digest differs from its reference")};
  }
  if (!seek_to_start(snapshot.get(), reference_error)) {
    return {0U, std::move(reference_error)};
  }

  std::uint64_t delivered = 0U;
  while (true) {
    const ssize_t result = ::read(snapshot.get(), buffer.data(), buffer.size());
    if (result < 0 && errno == EINTR) {
      continue;
    }
    if (result < 0) {
      return {
          delivered,
          error(CasErrorCode::io_error, "cannot stream private verified CAS snapshot", errno)};
    }
    if (result == 0) {
      break;
    }
    const auto count = static_cast<std::size_t>(result);
    const auto chunk = std::span(buffer.data(), count);
    try {
      if (!sink(chunk)) {
        return {delivered, error(CasErrorCode::consumer_rejected, "CAS consumer rejected a chunk")};
      }
    } catch (...) {
      return {delivered, error(CasErrorCode::consumer_rejected, "CAS consumer threw an exception")};
    }
    delivered += static_cast<std::uint64_t>(count);
  }
  if (delivered != reference.size) {
    return {
        delivered,
        error(CasErrorCode::integrity_error, "verified CAS snapshot size changed unexpectedly")};
  }
  return {delivered, {}};
}

std::string PosixCas::uri_for(const Sha256Digest& digest) {
  return "morphoia-cas://sha256/" + digest.hex();
}

std::optional<Sha256Digest> PosixCas::digest_from_uri(const std::string_view uri) noexcept {
  static constexpr std::string_view prefix = "morphoia-cas://sha256/";
  if (!uri.starts_with(prefix)) {
    return std::nullopt;
  }
  return Sha256Digest::from_hex(uri.substr(prefix.size()));
}

bool PosixCas::valid_media_type(const std::string_view media_type) noexcept {
  if (media_type.empty() || media_type.size() > 127U) {
    return false;
  }
  std::size_t slash_count = 0U;
  std::size_t slash_position = 0U;
  for (std::size_t index = 0U; index < media_type.size(); ++index) {
    const char value = media_type[index];
    if (value == '/') {
      ++slash_count;
      slash_position = index;
      continue;
    }
    const bool alpha = value >= 'a' && value <= 'z';
    const bool digit = value >= '0' && value <= '9';
    const bool punctuation = value == '!' || value == '#' || value == '$' || value == '&' ||
                             value == '^' || value == '_' || value == '.' || value == '+' ||
                             value == '-';
    if (!alpha && !digit && !punctuation) {
      return false;
    }
  }
  return slash_count == 1U && slash_position != 0U && slash_position + 1U < media_type.size();
}

std::string_view cas_error_name(const CasErrorCode code) noexcept {
  switch (code) {
    case CasErrorCode::none:
      return "none";
    case CasErrorCode::invalid_argument:
      return "invalid_argument";
    case CasErrorCode::unsafe_path:
      return "unsafe_path";
    case CasErrorCode::invalid_media_type:
      return "invalid_media_type";
    case CasErrorCode::invalid_reference:
      return "invalid_reference";
    case CasErrorCode::not_found:
      return "not_found";
    case CasErrorCode::size_limit:
      return "size_limit";
    case CasErrorCode::io_error:
      return "io_error";
    case CasErrorCode::integrity_error:
      return "integrity_error";
    case CasErrorCode::consumer_rejected:
      return "consumer_rejected";
  }
  return "unknown";
}

} // namespace morphoia::core
