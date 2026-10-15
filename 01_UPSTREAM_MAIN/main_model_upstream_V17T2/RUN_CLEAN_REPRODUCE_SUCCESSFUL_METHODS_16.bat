@echo off
setlocal
cd /d "%~dp0"
call "%~dp0CHECK_CLEAN_PACKAGE_MANIFEST.bat"
if errorlevel 1 exit /b 1
call "%~dp0RUN_V17T4R3_STANDALONE_CLEAN_REBUILD_AND_RUN_ALL_16_1x10.bat"
exit /b %errorlevel%
