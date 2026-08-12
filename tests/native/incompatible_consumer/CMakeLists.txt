# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

cmake_minimum_required(VERSION 3.20)
project(MorphoiaEngineIncompatibleConsumer LANGUAGES C)

# E0 publishes 0.0.1 with SameMinorVersion compatibility. A request for a
# future 0.1 line must therefore be rejected until an explicit compatibility
# decision changes this contract.
find_package(MorphoiaEngine 0.1 CONFIG REQUIRED)
