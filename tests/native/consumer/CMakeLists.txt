# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

cmake_minimum_required(VERSION 3.20)
project(MorphoiaEngineConsumer LANGUAGES C)

include(CTest)
find_package(MorphoiaEngine 0.0.1 CONFIG REQUIRED)

add_executable(morphoia_engine_consumer main.c)
target_compile_features(morphoia_engine_consumer PRIVATE c_std_11)
target_link_libraries(morphoia_engine_consumer PRIVATE Morphoia::Engine)

add_test(NAME installed.c_consumer COMMAND morphoia_engine_consumer)
