# Standalone Windows build of volume-cartographer's vc.track_crossings nanobind module
# (villa 0fb38c45 volume-cartographer/python/vc/track_crossings.cpp), for the spiral fitter.
# Mirrors the upstream target: nanobind_add_module(... NOMINSIZE), C++23, OpenMP.
cmake_minimum_required(VERSION 3.26)
project(vc_track_crossings CXX)

find_package(Python 3.14 COMPONENTS Interpreter Development.Module REQUIRED)
execute_process(COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
                OUTPUT_STRIP_TRAILING_WHITESPACE OUTPUT_VARIABLE nanobind_ROOT)
find_package(nanobind CONFIG REQUIRED)

nanobind_add_module(track_crossings NOMINSIZE src/track_crossings.cpp)
target_compile_features(track_crossings PRIVATE cxx_std_23)

option(VC_OPENMP "Build with OpenMP (MSVC: /openmp:llvm for OpenMP 3.x atomics)" ON)
if(MSVC)
  target_compile_options(track_crossings PRIVATE /O2 /EHsc /bigobj /permissive- /Zc:__cplusplus)
  if(VC_OPENMP)
    target_compile_options(track_crossings PRIVATE /openmp:llvm)
  endif()
elseif(VC_OPENMP)
  find_package(OpenMP REQUIRED)
  target_link_libraries(track_crossings PRIVATE OpenMP::OpenMP_CXX)
endif()
