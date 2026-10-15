@echo off
setlocal
cd /d "%~dp0"
call "%~dp0RUN_CURRENT_CLEAN_REBUILD_AND_RUN_ALL_8_1x10.bat"
exit /b %errorlevel%
