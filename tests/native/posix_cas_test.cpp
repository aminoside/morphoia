// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#include "core/posix_cas.hpp"
#include "core/sha256.hpp"

#include <cerrno>
#include <atomic>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <span>
#include <string>
#include <string_view>
#include <system_error>
#include <thread>
#include <vector>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {

class TemporaryDirectory final {
 public:
  TemporaryDirectory() {
    std::string pattern = "/tmp/morphoia-posix-cas-test.XXXXXX";
    std::vector<char> storage(pattern.begin(), pattern.end());
    storage.push_back('\0');
    char* const created = ::mkdtemp(storage.data());
    if (created != nullptr) {
      path_ = created;
    }
  }

  ~TemporaryDirectory() {
    if (!path_.empty()) {
      std::error_code ignored;
      std::filesystem::remove_all(path_, ignored);
    }
  }

  TemporaryDirectory(const TemporaryDirectory&) = delete;
  TemporaryDirectory& operator=(const TemporaryDirectory&) = delete;

  [[nodiscard]] const std::filesystem::path& path() const noexcept {
    return path_;
  }

 private:
  std::filesystem::path path_;
};

bool require_true(const bool condition, const std::string_view message) {
  if (!condition) {
    std::cerr << "posix_cas_test: " << message << '\n';
  }
  return condition;
}

std::filesystem::path object_path(
    const std::filesystem::path& root,
    const morphoia::core::Sha256Digest& digest) {
  const std::string hexadecimal = digest.hex();
  return root / "objects" / "sha256" / hexadecimal.substr(0U, 2U) /
         hexadecimal.substr(2U);
}

bool write_file(const std::filesystem::path& path, const std::string_view bytes) {
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  output.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  output.close();
  return output.good();
}

std::string read_file(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

} // namespace

int main() {
  using morphoia::core::BlobReference;
  using morphoia::core::CasErrorCode;
  using morphoia::core::PosixCas;
  using morphoia::core::Sha256;

  bool passed = true;
  TemporaryDirectory sandbox;
  passed &= require_true(!sandbox.path().empty(), "temporary sandbox creation failed");
  if (sandbox.path().empty()) {
    return EXIT_FAILURE;
  }

  passed &= require_true(!PosixCas::open("relative-cas"), "relative CAS root was accepted");
  const std::string traversal = (sandbox.path() / "root" / ".." / "escape").string();
  passed &= require_true(!PosixCas::open(traversal), "CAS root traversal was accepted");

  const auto real_root = sandbox.path() / "real-root";
  const auto root_alias = sandbox.path() / "root-alias";
  std::filesystem::create_directory(real_root);
  passed &= require_true(
      ::symlink(real_root.c_str(), root_alias.c_str()) == 0,
      "root symlink fixture creation failed");
  passed &= require_true(!PosixCas::open(root_alias.string()), "symlink CAS root was accepted");
  const auto real_parent = sandbox.path() / "real-parent";
  const auto parent_alias = sandbox.path() / "parent-alias";
  std::filesystem::create_directory(real_parent);
  passed &= require_true(
      ::symlink(real_parent.c_str(), parent_alias.c_str()) == 0,
      "intermediate root symlink fixture creation failed");
  passed &= require_true(
      !PosixCas::open((parent_alias / "cas").string()),
      "intermediate symlink in CAS root was accepted");

  const auto attacked_root = sandbox.path() / "attacked-root";
  const auto outside_objects = sandbox.path() / "outside-objects";
  std::filesystem::create_directory(attacked_root);
  std::filesystem::create_directory(outside_objects);
  passed &= require_true(
      ::symlink(outside_objects.c_str(), (attacked_root / "objects").c_str()) == 0,
      "objects symlink fixture creation failed");
  passed &= require_true(
      !PosixCas::open(attacked_root.string()),
      "symlinked CAS structural directory was accepted");

  const auto root = sandbox.path() / "cas";
  auto opened = PosixCas::open(root.string());
  passed &= require_true(static_cast<bool>(opened), "CAS could not be opened");
  if (!opened) {
    return EXIT_FAILURE;
  }
  auto& store = *opened.store;

  std::string payload(200'000U, '\0');
  for (std::size_t index = 0U; index < payload.size(); ++index) {
    payload[index] = static_cast<char>((index * 31U + 17U) & 0xffU);
  }
  const auto payload_bytes = std::as_bytes(std::span(payload.data(), payload.size()));
  const auto first = store.put(payload_bytes, "application/octet-stream");
  passed &= require_true(static_cast<bool>(first), "streaming CAS put failed");
  passed &= require_true(first.reference.size == payload.size(), "published CAS size differs");
  passed &= require_true(
      first.reference.digest == Sha256::hash(payload),
      "published CAS digest differs");
  passed &= require_true(
      first.reference.uri == PosixCas::uri_for(first.reference.digest),
      "published CAS URI differs");
  passed &= require_true(
      PosixCas::digest_from_uri(first.reference.uri) == first.reference.digest,
      "CAS URI did not resolve back to its digest");
  passed &= require_true(
      !PosixCas::digest_from_uri("file:///tmp/not-a-cas-object").has_value(),
      "external URI was interpreted as a CAS identity");
  passed &= require_true(
      !PosixCas::digest_from_uri(first.reference.uri + "x").has_value(),
      "CAS URI with a suffix was accepted");
  std::string uppercase_uri = first.reference.uri;
  const std::size_t digest_start = uppercase_uri.rfind('/') + 1U;
  for (std::size_t index = digest_start; index < uppercase_uri.size(); ++index) {
    if (uppercase_uri[index] >= 'a' && uppercase_uri[index] <= 'f') {
      uppercase_uri[index] = static_cast<char>(uppercase_uri[index] - 'a' + 'A');
    }
  }
  passed &= require_true(
      !PosixCas::digest_from_uri(uppercase_uri).has_value(),
      "non-canonical uppercase CAS URI was accepted");

  const auto stored_path = object_path(root, first.reference.digest);
  passed &= require_true(
      ::chmod(stored_path.parent_path().parent_path().c_str(), 0777) == 0,
      "managed-directory mode attack fixture failed");
  const auto unsafe_directory_read = store.verify(first.reference);
  passed &= require_true(
      !unsafe_directory_read && unsafe_directory_read.error.code == CasErrorCode::unsafe_path,
      "group/world-writable managed directory was accepted");
  passed &= require_true(
      ::chmod(stored_path.parent_path().parent_path().c_str(), 0700) == 0,
      "managed-directory mode restore failed");
  struct stat stored_metadata {};
  passed &= require_true(::lstat(stored_path.c_str(), &stored_metadata) == 0, "CAS object is absent");
  passed &= require_true(S_ISREG(stored_metadata.st_mode), "CAS object is not regular");
  passed &= require_true(
      (stored_metadata.st_mode & 0777) == 0444,
      "CAS object permissions are not read-only");
  passed &= require_true(stored_metadata.st_nlink == 1, "CAS object retained a temporary hard link");
  passed &= require_true(
      std::filesystem::is_empty(root / "tmp"),
      "CAS temporary directory was not cleaned");

  const auto repeated = store.put(payload_bytes, "application/octet-stream");
  passed &= require_true(repeated && repeated.reference == first.reference, "idempotent put changed reference");
  passed &= require_true(
      static_cast<bool>(store.verify(first.reference)),
      "published object did not verify");
  passed &= require_true(::chmod(stored_path.c_str(), 0644) == 0, "writable-object fixture failed");
  const auto writable_object = store.verify(first.reference);
  passed &= require_true(
      !writable_object && writable_object.error.code == CasErrorCode::unsafe_path,
      "writable published object was accepted");
  passed &= require_true(::chmod(stored_path.c_str(), 0444) == 0, "writable-object restore failed");

  std::string replayed;
  std::size_t sink_calls = 0U;
  const auto read = store.read_verified(
      first.reference,
      [&replayed, &sink_calls](const std::span<const std::byte> chunk) {
        ++sink_calls;
        replayed.append(reinterpret_cast<const char*>(chunk.data()), chunk.size());
        return true;
      });
  passed &= require_true(read && read.size == payload.size(), "verified streaming read failed");
  passed &= require_true(sink_calls > 1U && replayed == payload, "streaming read bytes differ");

  std::string snapshot_replay;
  std::size_t mutation_calls = 0U;
  const auto mutation_read = store.read_verified(
      first.reference,
      [&snapshot_replay, &mutation_calls, &stored_path, &payload](
          const std::span<const std::byte> chunk) {
        if (mutation_calls++ == 0U) {
          if (::chmod(stored_path.c_str(), 0644) != 0 ||
              !write_file(stored_path, std::string(payload.size(), 'm')) ||
              ::chmod(stored_path.c_str(), 0444) != 0) {
            return false;
          }
        }
        snapshot_replay.append(reinterpret_cast<const char*>(chunk.data()), chunk.size());
        return true;
      });
  passed &= require_true(
      mutation_read && snapshot_replay == payload,
      "mutation during delivery exposed bytes outside the verified snapshot");
  passed &= require_true(::chmod(stored_path.c_str(), 0644) == 0, "snapshot test restore chmod failed");
  passed &= require_true(write_file(stored_path, payload), "snapshot test restore write failed");
  passed &= require_true(::chmod(stored_path.c_str(), 0444) == 0, "snapshot test restore mode failed");

  std::size_t limited_sink_calls = 0U;
  const auto limited_read = store.read_verified(
      first.reference,
      [&limited_sink_calls](const std::span<const std::byte>) {
        ++limited_sink_calls;
        return true;
      },
      static_cast<std::uint64_t>(payload.size() - 1U));
  passed &= require_true(
      !limited_read && limited_read.error.code == CasErrorCode::size_limit &&
          limited_sink_calls == 0U,
      "size limit did not fail before consumer exposure");

  const auto rejected = store.read_verified(
      first.reference,
      [](const std::span<const std::byte>) { return false; });
  passed &= require_true(
      !rejected && rejected.error.code == CasErrorCode::consumer_rejected,
      "consumer rejection was not propagated");

  BlobReference wrong_uri = first.reference;
  wrong_uri.uri.push_back('x');
  passed &= require_true(
      !store.verify(wrong_uri) && store.verify(wrong_uri).error.code == CasErrorCode::invalid_reference,
      "digest/URI mismatch was accepted");
  BlobReference wrong_size = first.reference;
  ++wrong_size.size;
  passed &= require_true(
      !store.verify(wrong_size) && store.verify(wrong_size).error.code == CasErrorCode::integrity_error,
      "declared size mismatch was accepted");

  const auto input_file = sandbox.path() / "input.bin";
  passed &= require_true(write_file(input_file, "file-backed fixture"), "input fixture write failed");
  const auto from_file = store.put_file(input_file.string(), "application/octet-stream");
  passed &= require_true(static_cast<bool>(from_file), "file-backed streaming put failed");
  const auto input_alias = sandbox.path() / "input-alias.bin";
  passed &= require_true(
      ::symlink(input_file.c_str(), input_alias.c_str()) == 0,
      "input symlink fixture creation failed");
  passed &= require_true(
      !store.put_file(input_alias.string(), "application/octet-stream"),
      "symlink CAS input was accepted");
  const auto source_directory = sandbox.path() / "source-directory";
  const auto source_directory_alias = sandbox.path() / "source-directory-alias";
  std::filesystem::create_directory(source_directory);
  passed &= require_true(
      write_file(source_directory / "input.bin", "intermediate source symlink"),
      "intermediate source fixture write failed");
  passed &= require_true(
      ::symlink(source_directory.c_str(), source_directory_alias.c_str()) == 0,
      "intermediate source symlink fixture creation failed");
  passed &= require_true(
      !store.put_file(
          (source_directory_alias / "input.bin").string(),
          "application/octet-stream"),
      "intermediate symlink in CAS input was accepted");
  const std::string input_traversal = (sandbox.path() / "unused" / ".." / "input.bin").string();
  passed &= require_true(
      !store.put_file(input_traversal, "application/octet-stream"),
      "input traversal was accepted");
  passed &= require_true(
      !store.put(payload_bytes, "Application/Octet-Stream"),
      "non-canonical media type was accepted");
  passed &= require_true(
      !store.put(payload_bytes, "application/octet-stream; charset=binary"),
      "parameterized media type was accepted");
  const auto oversized = store.put(
      payload_bytes,
      "application/octet-stream",
      static_cast<std::uint64_t>(payload.size() - 1U));
  passed &= require_true(
      !oversized && oversized.error.code == CasErrorCode::size_limit &&
          std::filesystem::is_empty(root / "tmp"),
      "oversized put exposed an object or retained temporary data");
  const auto unsafe_limit = store.put(
      payload_bytes,
      "application/octet-stream",
      PosixCas::maximum_reference_bytes + 1U);
  passed &= require_true(
      !unsafe_limit && unsafe_limit.error.code == CasErrorCode::invalid_argument,
      "CAS accepted a byte limit outside canonical JSON's exact integer domain");

  const auto transfer_file = sandbox.path() / "transfer.bin";
  const std::string transfer_payload = "expected transfer identity";
  passed &= require_true(
      write_file(transfer_file, transfer_payload),
      "verified transfer fixture write failed");
  const auto transfer_digest = Sha256::hash(transfer_payload);
  morphoia::core::Sha256Digest wrong_digest{};
  const auto rejected_digest = store.put_file_verified(
      transfer_file.string(),
      "application/octet-stream",
      wrong_digest,
      static_cast<std::uint64_t>(transfer_payload.size()));
  passed &= require_true(
      !rejected_digest && rejected_digest.error.code == CasErrorCode::integrity_error &&
          !std::filesystem::exists(object_path(root, transfer_digest)) &&
          std::filesystem::is_empty(root / "tmp"),
      "digest-mismatched transfer was published or left temporary data");
  const auto rejected_size = store.put_file_verified(
      transfer_file.string(),
      "application/octet-stream",
      transfer_digest,
      static_cast<std::uint64_t>(transfer_payload.size() + 1U));
  passed &= require_true(
      !rejected_size && rejected_size.error.code == CasErrorCode::integrity_error &&
          !std::filesystem::exists(object_path(root, transfer_digest)),
      "size-mismatched transfer was published");
  const auto accepted_transfer = store.put_file_verified(
      transfer_file.string(),
      "application/octet-stream",
      transfer_digest,
      static_cast<std::uint64_t>(transfer_payload.size()));
  passed &= require_true(
      static_cast<bool>(accepted_transfer),
      "expected size/digest transfer was rejected");

  for (std::size_t cycle = 0U; cycle < 32U; ++cycle) {
    const std::string concurrent_payload = "concurrent-publication-" + std::to_string(cycle);
    const auto concurrent_digest = Sha256::hash(concurrent_payload);
    const BlobReference expected_reference{
        concurrent_digest,
        static_cast<std::uint64_t>(concurrent_payload.size()),
        "application/octet-stream",
        PosixCas::uri_for(concurrent_digest),
    };
    std::atomic<bool> reader_started{false};
    std::atomic<bool> writer_done{false};
    std::atomic<bool> transient_invalid{false};
    std::thread reader([&store,
                        &expected_reference,
                        &reader_started,
                        &writer_done,
                        &transient_invalid]() {
      reader_started.store(true, std::memory_order_release);
      while (!writer_done.load(std::memory_order_acquire)) {
        const auto result = store.verify(expected_reference);
        if (!result && result.error.code != CasErrorCode::not_found) {
          transient_invalid.store(true, std::memory_order_release);
          return;
        }
      }
    });
    while (!reader_started.load(std::memory_order_acquire)) {
      std::this_thread::yield();
    }
    const auto concurrent_put = store.put(
        std::as_bytes(std::span(concurrent_payload.data(), concurrent_payload.size())),
        "application/octet-stream");
    writer_done.store(true, std::memory_order_release);
    reader.join();
    passed &= require_true(
        static_cast<bool>(concurrent_put),
        "concurrent publication failed");
    passed &= require_true(
        !transient_invalid.load(std::memory_order_acquire),
        "reader observed a partially published identity");
    passed &= require_true(
        static_cast<bool>(store.verify(expected_reference)),
        "concurrently published identity did not verify");
  }

  const auto hardlink = sandbox.path() / "external-hardlink";
  passed &= require_true(
      ::link(stored_path.c_str(), hardlink.c_str()) == 0,
      "hard-link attack fixture creation failed");
  std::size_t hardlink_sink_calls = 0U;
  const auto hardlink_read = store.read_verified(
      first.reference,
      [&hardlink_sink_calls](const std::span<const std::byte>) {
        ++hardlink_sink_calls;
        return true;
      });
  passed &= require_true(
      !hardlink_read && hardlink_read.error.code == CasErrorCode::unsafe_path &&
          hardlink_sink_calls == 0U,
      "hard-linked object reached the consumer");
  passed &= require_true(::unlink(hardlink.c_str()) == 0, "hard-link fixture cleanup failed");

  passed &= require_true(::chmod(stored_path.c_str(), 0644) == 0, "corruption chmod failed");
  passed &= require_true(write_file(stored_path, std::string(payload.size(), 'x')), "corruption write failed");
  passed &= require_true(::chmod(stored_path.c_str(), 0444) == 0, "corruption mode restore failed");
  std::size_t corrupt_sink_calls = 0U;
  const auto corrupt_read = store.read_verified(
      first.reference,
      [&corrupt_sink_calls](const std::span<const std::byte>) {
        ++corrupt_sink_calls;
        return true;
      });
  passed &= require_true(
      !corrupt_read && corrupt_read.error.code == CasErrorCode::integrity_error &&
          corrupt_sink_calls == 0U,
      "corrupt object reached the consumer");
  const auto collision = store.put(payload_bytes, "application/octet-stream");
  passed &= require_true(
      !collision && collision.error.code == CasErrorCode::integrity_error,
      "poisoned existing identity was overwritten or accepted");

  const auto symlink_root = sandbox.path() / "symlink-object-cas";
  auto symlink_store = PosixCas::open(symlink_root.string());
  passed &= require_true(
      static_cast<bool>(symlink_store),
      "symlink-object store creation failed");
  const std::string symlink_payload = "symlink collision fixture";
  const auto symlink_digest = Sha256::hash(symlink_payload);
  const auto symlink_path = object_path(symlink_root, symlink_digest);
  std::filesystem::create_directory(symlink_path.parent_path());
  const auto outside_target = sandbox.path() / "outside-target";
  passed &= require_true(write_file(outside_target, "outside remains unchanged"), "outside target write failed");
  passed &= require_true(
      ::symlink(outside_target.c_str(), symlink_path.c_str()) == 0,
      "object symlink fixture creation failed");
  const auto symlink_collision = symlink_store.store->put(
      std::as_bytes(std::span(symlink_payload.data(), symlink_payload.size())),
      "application/octet-stream");
  passed &= require_true(!symlink_collision, "symlinked object identity was accepted");
  passed &= require_true(
      read_file(outside_target) == "outside remains unchanged",
      "symlink collision modified its target");

  if (!passed) {
    return EXIT_FAILURE;
  }
  std::cout << "posix_cas_test: PASS (atomic streaming, integrity, hostile paths)\n";
  return EXIT_SUCCESS;
}
