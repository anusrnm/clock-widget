@echo off
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
pythonw "%SCRIPT_DIR%clock_widget.py" --transparent --no-date
