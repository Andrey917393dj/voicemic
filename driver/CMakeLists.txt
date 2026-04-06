cmake_minimum_required(VERSION 3.16)
project(voicemic_audio LANGUAGES C CXX)

# Find WDK
find_package(WDK REQUIRED)

# Driver target
wdk_add_driver(voicemic_audio
    adapter.cpp
    minwave.cpp
)

target_include_directories(voicemic_audio PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(voicemic_audio portcls.lib)
