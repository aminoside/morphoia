// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#include "core/canonical_json.hpp"
#include "core/posix_cas.hpp"
#include "core/sha256.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <span>
#include <string>
#include <system_error>
#include <vector>

#include <sys/stat.h>

namespace {

using morphoia::core::BlobReference;
using morphoia::core::CanonicalJsonLimits;
using morphoia::core::PosixCas;
using morphoia::core::Sha256;

class Sandbox final {
 public:
  Sandbox() {
    std::array<char, 64> pattern{};
    constexpr char prefix[] = "/tmp/morphoia-ir-replay.XXXXXX";
    std::copy(prefix, prefix + sizeof(prefix), pattern.begin());
    char* const created = ::mkdtemp(pattern.data());
    if (created == nullptr) {
      throw std::runtime_error("cannot create replay sandbox");
    }
    path_ = created;
  }

  ~Sandbox() {
    std::error_code ignored;
    std::filesystem::remove_all(path_, ignored);
  }

  Sandbox(const Sandbox&) = delete;
  Sandbox& operator=(const Sandbox&) = delete;

  [[nodiscard]] const std::filesystem::path& path() const noexcept { return path_; }

 private:
  std::filesystem::path path_;
};

bool require_true(const bool condition, const std::string& message) {
  if (!condition) {
    std::cerr << "ir_replay_test: " << message << '\n';
  }
  return condition;
}

std::string read_bytes(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    throw std::runtime_error("cannot open fixture: " + path.string());
  }
  return {
      std::istreambuf_iterator<char>(stream),
      std::istreambuf_iterator<char>(),
  };
}

std::span<const std::byte> as_bytes(const std::string& value) {
  return {
      reinterpret_cast<const std::byte*>(value.data()),
      value.size(),
  };
}

std::vector<std::filesystem::path> sorted_json_files(const std::filesystem::path& directory) {
  std::vector<std::filesystem::path> paths;
  for (const auto& entry : std::filesystem::directory_iterator(directory)) {
    if (entry.is_regular_file() && entry.path().extension() == ".json") {
      paths.push_back(entry.path());
    }
  }
  std::sort(paths.begin(), paths.end());
  return paths;
}

std::vector<std::filesystem::path> sorted_golden_files(
    const std::filesystem::path& directory) {
  std::vector<std::filesystem::path> paths;
  for (const auto& entry : std::filesystem::directory_iterator(directory)) {
    if (entry.is_regular_file() && entry.path().extension() == ".cjson") {
      paths.push_back(entry.path());
    }
  }
  std::sort(paths.begin(), paths.end());
  return paths;
}

} // namespace

int main() {
  const std::filesystem::path corpus =
      std::filesystem::path(MORPHOIA_TEST_SOURCE_DIR) / "tests" / "fixtures" /
      "engine-ir" / "0.1.0";
  const auto inputs = sorted_json_files(corpus / "inputs");
  const auto goldens = sorted_golden_files(corpus / "goldens");
  bool passed = true;
  passed &= require_true(inputs.size() == 20U, "corpus must contain exactly 20 inputs");
  passed &= require_true(goldens.size() == 20U, "corpus must contain exactly 20 goldens");
  if (!passed) {
    return EXIT_FAILURE;
  }

  Sandbox sandbox;
  const auto first_root = sandbox.path() / "cas-a";
  const auto second_root = sandbox.path() / "cas-b";
  std::filesystem::create_directory(first_root);
  std::filesystem::create_directory(second_root);
  (void)::chmod(first_root.c_str(), 0700);
  (void)::chmod(second_root.c_str(), 0700);
  auto first_open = PosixCas::open(first_root.string());
  auto second_open = PosixCas::open(second_root.string());
  passed &= require_true(static_cast<bool>(first_open), "first POSIX CAS did not open");
  passed &= require_true(static_cast<bool>(second_open), "second POSIX CAS did not open");
  if (!passed) {
    return EXIT_FAILURE;
  }

  CanonicalJsonLimits limits{};
  for (std::size_t index = 0U; index < inputs.size(); ++index) {
    const std::string input = read_bytes(inputs[index]);
    const std::string golden = read_bytes(goldens[index]);
    const auto canonical = morphoia::core::canonicalize_json(golden, limits);
    passed &= require_true(
        static_cast<bool>(canonical) && canonical.canonical == golden,
        "golden is not exact Profile 1 bytes: " + goldens[index].filename().string());
    const auto content_digest = Sha256::hash(golden);
    passed &= require_true(
        input.find(content_digest.hex()) != std::string::npos,
        "input envelope does not carry its golden content identity");

    const auto first_put = first_open.store->put(
        as_bytes(input), "application/vnd.morphoia.ir-manifest.v0+json", 1'048'576U);
    const auto second_put = second_open.store->put(
        as_bytes(input), "application/vnd.morphoia.ir-manifest.v0+json", 1'048'576U);
    passed &= require_true(
        static_cast<bool>(first_put) && static_cast<bool>(second_put),
        "manifest publication failed in one replay CAS root");
    if (!first_put || !second_put) {
      continue;
    }
    passed &= require_true(
        first_put.reference == second_put.reference,
        "independent CAS roots produced different references");

    std::string delivered;
    const auto read = second_open.store->read_verified(
        second_put.reference,
        [&delivered](const std::span<const std::byte> bytes) {
          delivered.append(reinterpret_cast<const char*>(bytes.data()), bytes.size());
          return true;
        },
        1'048'576U);
    passed &= require_true(
        static_cast<bool>(read) && delivered == input,
        "verified cross-root replay did not reproduce input bytes");

    BlobReference corrupt = second_put.reference;
    ++corrupt.size;
    delivered.clear();
    const auto rejected = second_open.store->read_verified(
        corrupt,
        [&delivered](const std::span<const std::byte> bytes) {
          delivered.append(reinterpret_cast<const char*>(bytes.data()), bytes.size());
          return true;
        },
        1'048'576U);
    passed &= require_true(
        !rejected && delivered.empty(),
        "invalid reference exposed bytes before complete verification");
  }

  if (!passed) {
    return EXIT_FAILURE;
  }
  std::cout << "ir_replay_test: PASS (20 Profile 1 goldens, two verified POSIX CAS roots)\n";
  return EXIT_SUCCESS;
}
