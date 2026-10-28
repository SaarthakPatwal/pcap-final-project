cmake_minimum_required(VERSION 3.24)
project(datacenter_thermal LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
option(ENABLE_CUDA "Build NVIDIA CUDA backend when toolkit is installed" ON)

# The default /openmp implements an older standard. LLVM mode supports collapse
# and max reductions in recent Visual Studio (17.8+ recommended).
if(MSVC)
    set(OpenMP_RUNTIME_MSVC llvm)
    set(OpenMP_CXX_FLAGS "/openmp:llvm")
endif()
find_package(OpenMP REQUIRED)
add_library(thermal SHARED src/api.cpp src/cpu_sim.cpp src/omp_sim.cpp)
target_link_libraries(thermal PRIVATE OpenMP::OpenMP_CXX)
# Some MinGW CMake bundles detect the compile flag but omit libgomp at link time.
if(MINGW)
    target_link_options(thermal PRIVATE -fopenmp)
endif()
set_target_properties(thermal PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
if(MSVC)
    target_compile_options(thermal PRIVATE $<$<COMPILE_LANGUAGE:CXX>:/O2> $<$<COMPILE_LANGUAGE:CXX>:/fp:strict>)
else()
    target_compile_options(thermal PRIVATE $<$<COMPILE_LANGUAGE:CXX>:-O3> $<$<COMPILE_LANGUAGE:CXX>:-ffp-contract=off>)
endif()

if(ENABLE_CUDA)
    include(CheckLanguage)
    check_language(CUDA)
    if(CMAKE_CUDA_COMPILER)
        enable_language(CUDA)
        target_sources(thermal PRIVATE src/cuda_sim.cu)
        target_compile_definitions(thermal PRIVATE WITH_CUDA)
        # Match the CPU's separate float operations, rather than fused multiply-add.
        target_compile_options(thermal PRIVATE $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false>)
        set_target_properties(thermal PROPERTIES CUDA_STANDARD 14 CUDA_STANDARD_REQUIRED ON)
        message(STATUS "CUDA backend enabled")
    else()
        message(STATUS "CUDA Toolkit not found: building CPU + OpenMP")
    endif()
endif()
