cmake_minimum_required(VERSION 3.14)
project(packwise_packer CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(Threads REQUIRED)

add_library(packer_core STATIC src/packer_core.cpp)
target_include_directories(packer_core PUBLIC src)

add_executable(packer_service src/main.cpp)
target_include_directories(packer_service PRIVATE include src)
target_link_libraries(packer_service PRIVATE packer_core Threads::Threads)
if(WIN32)
  target_compile_definitions(packer_service PRIVATE _WIN32_WINNT=0x0A00)
  target_link_libraries(packer_service PRIVATE ws2_32 crypt32)
endif()

add_executable(test_core tests/test_core.cpp)
target_link_libraries(test_core PRIVATE packer_core)
