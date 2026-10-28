@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
if errorlevel 1 exit /b %errorlevel%

set "CMAKE_EXE=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
"%CMAKE_EXE%" -S . -B build-cuda-vs -G "Visual Studio 17 2022" -A x64 -DENABLE_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89
if errorlevel 1 exit /b %errorlevel%
"%CMAKE_EXE%" --build build-cuda-vs --config Release -j 4
exit /b %errorlevel%
