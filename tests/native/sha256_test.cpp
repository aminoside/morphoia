// SPDX-FileCopyrightText: 2026 Olivier Ami
// SPDX-License-Identifier: Apache-2.0 OR MIT

#include "core/sha256.hpp"

#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>

namespace {

bool require_true(const bool condition, const std::string_view message) {
  if (!condition) {
    std::cerr << "sha256_test: " << message << '\n';
  }
  return condition;
}

bool require_digest(const std::string_view input, const std::string_view expected) {
  return require_true(
      morphoia::core::Sha256::hash(input).hex() == expected,
      std::string("digest mismatch for vector length ") + std::to_string(input.size()));
}

} // namespace

int main() {
  using morphoia::core::Sha256;
  using morphoia::core::Sha256Digest;

  bool passed = true;
  passed &= require_digest(
      "",
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  passed &= require_digest(
      "abc",
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  passed &= require_digest(
      "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
      "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1");

  const std::string million_a(1'000'000U, 'a');
  passed &= require_digest(
      million_a,
      "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");

  for (const std::size_t chunk_size : {1U, 3U, 55U, 56U, 63U, 64U, 65U, 4096U}) {
    Sha256 incremental;
    incremental.update(std::string_view{});
    for (std::size_t offset = 0U; offset < million_a.size(); offset += chunk_size) {
      incremental.update(std::string_view(
          million_a.data() + offset,
          std::min(chunk_size, million_a.size() - offset)));
    }
    passed &= require_true(
        incremental.finalize().hex() ==
            "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0",
        "incremental chunking changed the digest");
  }

  const auto parsed = Sha256Digest::from_hex(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  passed &= require_true(parsed.has_value(), "lowercase digest did not parse");
  passed &= require_true(parsed.has_value() && parsed->hex() ==
                                                   "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                         "digest hex round-trip failed");
  passed &= require_true(!Sha256Digest::from_hex("00").has_value(), "short digest was accepted");
  passed &= require_true(
      !Sha256Digest::from_hex(
           "BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD")
           .has_value(),
      "non-canonical uppercase digest was accepted");

  Sha256 finalized;
  finalized.update("one-shot");
  static_cast<void>(finalized.finalize());
  bool rejected_second_finalize = false;
  try {
    static_cast<void>(finalized.finalize());
  } catch (const std::logic_error&) {
    rejected_second_finalize = true;
  }
  passed &= require_true(rejected_second_finalize, "second finalize was not rejected");
  bool rejected_late_update = false;
  try {
    finalized.update("late");
  } catch (const std::logic_error&) {
    rejected_late_update = true;
  }
  passed &= require_true(rejected_late_update, "update after finalize was not rejected");

  if (!passed) {
    return EXIT_FAILURE;
  }
  std::cout << "sha256_test: PASS (NIST vectors and incremental boundaries)\n";
  return EXIT_SUCCESS;
}
