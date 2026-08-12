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

add_library(morphoia_engine SHARED)
add_library(Morphoia::Engine ALIAS morphoia_engine)

target_sources(
  morphoia_engine
  PRIVATE
    cpp/src/engine.cpp
    cpp/include/morphoia/engine.h
)

target_compile_features(morphoia_engine PRIVATE cxx_std_20)
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

  add_executable(morphoia_core_smoke tests/native/core_smoke.cpp)
  target_link_libraries(morphoia_core_smoke PRIVATE Morphoia::Engine)
  target_compile_features(morphoia_core_smoke PRIVATE cxx_std_20)
  set_target_properties(morphoia_core_smoke PROPERTIES CXX_EXTENSIONS OFF)
  morphoia_enable_strict_warnings(morphoia_core_smoke)
  add_test(NAME native.core_smoke COMMAND morphoia_core_smoke)
  set_tests_properties(native.core_smoke PROPERTIES LABELS "native;core;smoke")
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
