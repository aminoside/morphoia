# SPDX-License-Identifier: Apache-2.0 OR MIT

cmake_minimum_required(VERSION 3.20)

project(
  MorphoiaEngine
  VERSION 0.0.1
  DESCRIPTION "Federated interoperability and provenance engine"
  LANGUAGES C CXX
)

include(CTest)
include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
include(cmake/MorphoiaWarnings.cmake)

option(MORPHOIA_WARNINGS_AS_ERRORS "Treat warnings in Morphoia-owned code as errors" ON)

add_library(morphoia_core_internal STATIC)
target_sources(
  morphoia_core_internal
  PRIVATE
    cpp/src/core/canonical_json.cpp
    cpp/src/core/canonical_json.hpp
    cpp/src/core/sha256.cpp
    cpp/src/core/sha256.hpp
)
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  target_sources(
    morphoia_core_internal
    PRIVATE
      cpp/src/core/posix_cas.cpp
      cpp/src/core/posix_cas.hpp
  )
endif()
target_compile_features(morphoia_core_internal PUBLIC cxx_std_20)
target_include_directories(
  morphoia_core_internal
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/cpp/src>
)
set_target_properties(
  morphoia_core_internal
  PROPERTIES
    CXX_EXTENSIONS OFF
    POSITION_INDEPENDENT_CODE ON
)
morphoia_enable_strict_warnings(morphoia_core_internal)

add_library(morphoia_engine SHARED)
add_library(Morphoia::Engine ALIAS morphoia_engine)

target_sources(
  morphoia_engine
  PRIVATE
    cpp/src/engine.cpp
    cpp/include/morphoia/engine.h
)

target_compile_features(morphoia_engine PRIVATE cxx_std_20)
target_link_libraries(morphoia_engine PRIVATE morphoia_core_internal)
target_include_directories(
  morphoia_engine
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/cpp/include>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)
target_compile_definitions(
  morphoia_engine
  PUBLIC
    MORPHOIA_ENGINE_SHARED
  PRIVATE
    MORPHOIA_ENGINE_EXPORTS
    MORPHOIA_ENGINE_VERSION_MAJOR=${PROJECT_VERSION_MAJOR}
    MORPHOIA_ENGINE_VERSION_MINOR=${PROJECT_VERSION_MINOR}
    MORPHOIA_ENGINE_VERSION_PATCH=${PROJECT_VERSION_PATCH}
    MORPHOIA_ENGINE_VERSION_STRING="${PROJECT_VERSION}"
)
set_target_properties(
  morphoia_engine
  PROPERTIES
    CXX_EXTENSIONS OFF
    POSITION_INDEPENDENT_CODE ON
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN ON
    EXPORT_NAME Engine
    VERSION ${PROJECT_VERSION}
    SOVERSION 0
)
morphoia_enable_strict_warnings(morphoia_engine)
if(UNIX AND NOT APPLE)
  target_link_options(
    morphoia_engine
    PRIVATE
      "LINKER:--version-script=${CMAKE_CURRENT_SOURCE_DIR}/cmake/morphoia_engine.map"
  )
  set_property(
    TARGET morphoia_engine
    APPEND
    PROPERTY LINK_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/cmake/morphoia_engine.map
  )
endif()

if(BUILD_TESTING)
  add_executable(morphoia_abi_c_smoke tests/native/abi_c_smoke.c)
  target_link_libraries(morphoia_abi_c_smoke PRIVATE Morphoia::Engine)
  target_compile_features(morphoia_abi_c_smoke PRIVATE c_std_11)
  set_target_properties(
    morphoia_abi_c_smoke
    PROPERTIES
      C_EXTENSIONS OFF
      LINKER_LANGUAGE CXX
  )
  morphoia_enable_strict_warnings(morphoia_abi_c_smoke)
  add_test(NAME native.abi_c_smoke COMMAND morphoia_abi_c_smoke)
  set_tests_properties(native.abi_c_smoke PROPERTIES LABELS "native;abi;smoke")

  add_executable(
    morphoia_canonical_json_c_api_test
    tests/native/canonical_json_c_api_test.c
  )
  target_link_libraries(morphoia_canonical_json_c_api_test PRIVATE Morphoia::Engine)
  target_compile_features(morphoia_canonical_json_c_api_test PRIVATE c_std_11)
  set_target_properties(
    morphoia_canonical_json_c_api_test
    PROPERTIES
      C_EXTENSIONS OFF
      LINKER_LANGUAGE CXX
  )
  morphoia_enable_strict_warnings(morphoia_canonical_json_c_api_test)
  add_test(
    NAME native.canonical_json_c_api
    COMMAND morphoia_canonical_json_c_api_test
  )
  set_tests_properties(
    native.canonical_json_c_api
    PROPERTIES LABELS "native;abi;json;ir"
  )

  add_executable(morphoia_core_smoke tests/native/core_smoke.cpp)
  target_link_libraries(morphoia_core_smoke PRIVATE Morphoia::Engine)
  target_compile_features(morphoia_core_smoke PRIVATE cxx_std_20)
  set_target_properties(morphoia_core_smoke PROPERTIES CXX_EXTENSIONS OFF)
  morphoia_enable_strict_warnings(morphoia_core_smoke)
  add_test(NAME native.core_smoke COMMAND morphoia_core_smoke)
  set_tests_properties(native.core_smoke PROPERTIES LABELS "native;core;smoke")

  add_executable(morphoia_sha256_test tests/native/sha256_test.cpp)
  target_link_libraries(morphoia_sha256_test PRIVATE morphoia_core_internal)
  target_compile_features(morphoia_sha256_test PRIVATE cxx_std_20)
  set_target_properties(morphoia_sha256_test PROPERTIES CXX_EXTENSIONS OFF)
  morphoia_enable_strict_warnings(morphoia_sha256_test)
  add_test(NAME native.sha256 COMMAND morphoia_sha256_test)
  set_tests_properties(native.sha256 PROPERTIES LABELS "native;core;sha256")

  add_executable(morphoia_canonical_json_test tests/native/canonical_json_test.cpp)
  target_link_libraries(morphoia_canonical_json_test PRIVATE morphoia_core_internal)
  target_compile_features(morphoia_canonical_json_test PRIVATE cxx_std_20)
  target_compile_definitions(
    morphoia_canonical_json_test
    PRIVATE MORPHOIA_TEST_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
  )
  set_target_properties(morphoia_canonical_json_test PROPERTIES CXX_EXTENSIONS OFF)
  morphoia_enable_strict_warnings(morphoia_canonical_json_test)
  add_test(NAME native.canonical_json COMMAND morphoia_canonical_json_test)
  set_tests_properties(native.canonical_json PROPERTIES LABELS "native;core;json;ir")

  if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    find_package(Threads REQUIRED)
    add_executable(morphoia_posix_cas_test tests/native/posix_cas_test.cpp)
    target_link_libraries(
      morphoia_posix_cas_test
      PRIVATE morphoia_core_internal Threads::Threads
    )
    target_compile_features(morphoia_posix_cas_test PRIVATE cxx_std_20)
    set_target_properties(morphoia_posix_cas_test PROPERTIES CXX_EXTENSIONS OFF)
    morphoia_enable_strict_warnings(morphoia_posix_cas_test)
    add_test(NAME native.posix_cas COMMAND morphoia_posix_cas_test)
    set_tests_properties(native.posix_cas PROPERTIES LABELS "native;core;cas;posix")

    add_executable(morphoia_ir_replay_test tests/native/ir_replay_test.cpp)
    target_link_libraries(morphoia_ir_replay_test PRIVATE morphoia_core_internal)
    target_compile_features(morphoia_ir_replay_test PRIVATE cxx_std_20)
    target_compile_definitions(
      morphoia_ir_replay_test
      PRIVATE MORPHOIA_TEST_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_target_properties(morphoia_ir_replay_test PROPERTIES CXX_EXTENSIONS OFF)
    morphoia_enable_strict_warnings(morphoia_ir_replay_test)
    add_test(NAME native.ir_replay COMMAND morphoia_ir_replay_test)
    set_tests_properties(native.ir_replay PROPERTIES LABELS "native;core;cas;ir;replay")
  endif()
endif()

install(
  TARGETS morphoia_engine
  EXPORT MorphoiaEngineTargets
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)
install(FILES cpp/include/morphoia/engine.h DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/morphoia)
install(
  FILES LICENSE-APACHE LICENSE-MIT NOTICE
  DESTINATION ${CMAKE_INSTALL_DATADIR}/licenses/MorphoiaEngine
)

configure_package_config_file(
  cmake/MorphoiaEngineConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/MorphoiaEngineConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/MorphoiaEngine
)
write_basic_package_version_file(
  ${CMAKE_CURRENT_BINARY_DIR}/MorphoiaEngineConfigVersion.cmake
  VERSION ${PROJECT_VERSION}
  COMPATIBILITY SameMinorVersion
)
install(
  EXPORT MorphoiaEngineTargets
  FILE MorphoiaEngineTargets.cmake
  NAMESPACE Morphoia::
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/MorphoiaEngine
)
install(
  FILES
    ${CMAKE_CURRENT_BINARY_DIR}/MorphoiaEngineConfig.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/MorphoiaEngineConfigVersion.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/MorphoiaEngine
)
