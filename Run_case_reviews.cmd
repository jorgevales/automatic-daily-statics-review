@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Instruction case reviews
rem Keep this CMD, case_review_runner.py and your two Markdown files together on S:.
rem Double-click and paste a case root, or drag a folder onto this CMD.
rem Missing Python packages install automatically on S:; no separate setup is required.
rem For a fully recorded run use Run_case_reviews_DIAGNOSE.cmd (same run, plus two reports).
rem Your S: paths are asked once and saved in local_paths.cmd (never committed to Git).
set "DCR_LOCAL=%~dp0local_paths.cmd"
set "DCR_RUNNER=%~dp0case_review_runner.py"
set "DCR_ASKED="
if exist "%DCR_LOCAL%" call "%DCR_LOCAL%"
if /I not "%~d0"=="S:" goto wrongdrive
if not exist "%DCR_RUNNER%" goto norunner

:checkpython
if defined DCR_PYTHON if exist "%DCR_PYTHON%" goto checknode
echo.
echo ------------------------------------------------------------
echo SETUP (asked once; your answers are saved on this computer only)
echo.
echo Where is Python on the S: drive?
echo   What it is for : Python is the program that runs this review tool.
echo   What to paste  : the full path of the file called python.exe
echo                    Example: S:\Tools\Python\python.exe
echo   Tip: in File Explorer hold Shift, right-click python.exe and choose "Copy as path".
set "DCR_PYTHON="
set /p "DCR_PYTHON=Paste it here and press Enter: "
if not defined DCR_PYTHON goto checkpython
set "DCR_PYTHON=%DCR_PYTHON:"=%"
if /I not "%DCR_PYTHON:~0,2%"=="S:" goto badpython
if not exist "%DCR_PYTHON%" goto badpython
set "DCR_ASKED=1"
goto checknode
:badpython
echo.
echo That did not work: the path must start with S: and the file must exist.
set "DCR_PYTHON="
goto checkpython

:checknode
if defined DCR_NODE if exist "%DCR_NODE%" goto checkruntime
echo.
echo Where is Node.js on the S: drive?
echo   What it is for : Node.js is a helper program the tool uses to steer Edge.
echo   What to paste  : the full path of the file called node.exe
echo                    Example: S:\Tools\Node\node.exe
echo   Tip: same trick as before: Shift + right-click node.exe, "Copy as path".
set "DCR_NODE="
set /p "DCR_NODE=Paste it here and press Enter: "
if not defined DCR_NODE goto checknode
set "DCR_NODE=%DCR_NODE:"=%"
if /I not "%DCR_NODE:~0,2%"=="S:" goto badnode
if not exist "%DCR_NODE%" goto badnode
set "DCR_ASKED=1"
goto checkruntime
:badnode
echo.
echo That did not work: the path must start with S: and the file must exist.
set "DCR_NODE="
goto checknode

:checkruntime
if defined DCR_RUNTIME_ROOT if exist "%DCR_RUNTIME_ROOT%\" goto setupdone
echo.
echo Which S: folder may the tool use for its own working files?
echo   What it is for : the tool keeps its Edge profile, logs, results and temporary
echo                    files here. Nothing is stored anywhere else.
echo   What to paste  : a folder path. If the folder does not exist it is created.
echo                    Example: S:\CaseReviewRuntime
set "DCR_RUNTIME_ROOT="
set /p "DCR_RUNTIME_ROOT=Paste it here and press Enter: "
if not defined DCR_RUNTIME_ROOT goto checkruntime
set "DCR_RUNTIME_ROOT=%DCR_RUNTIME_ROOT:"=%"
if /I not "%DCR_RUNTIME_ROOT:~0,2%"=="S:" goto badruntime
if not exist "%DCR_RUNTIME_ROOT%\" mkdir "%DCR_RUNTIME_ROOT%"
if not exist "%DCR_RUNTIME_ROOT%\" goto badruntime
set "DCR_ASKED=1"
goto setupdone
:badruntime
echo.
echo That did not work: the path must start with S: and the folder must be creatable.
set "DCR_RUNTIME_ROOT="
goto checkruntime

:setupdone
if not defined DCR_ASKED goto prepared
>"%DCR_LOCAL%" echo rem Saved answers for this computer. Delete this file to be asked again. Never share or commit it.
>>"%DCR_LOCAL%" echo set "DCR_PYTHON=%DCR_PYTHON%"
>>"%DCR_LOCAL%" echo set "DCR_NODE=%DCR_NODE%"
>>"%DCR_LOCAL%" echo set "DCR_RUNTIME_ROOT=%DCR_RUNTIME_ROOT%"
echo.
echo Saved. You will not be asked again on this computer.
echo ------------------------------------------------------------
echo.

:prepared
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONNOUSERSITE=1"
set "PYTHONHOME="
set "PYTHONPATH="
set "TEMP=%DCR_RUNTIME_ROOT%\launcher-temp\%USERNAME%-%COMPUTERNAME%"
set "TMP=%TEMP%"
set "TMPDIR=%TEMP%"
if not exist "%TEMP%\" mkdir "%TEMP%"
if not exist "%TEMP%\" goto notemp
pushd "%~dp0"
if errorlevel 1 goto nocwd
"%DCR_PYTHON%" -B -s "%DCR_RUNNER%" %*
set "DCR_EXIT=%ERRORLEVEL%"
popd
echo.
if "%DCR_EXIT%"=="0" (echo Review run finished successfully.) else (echo Run ended with code %DCR_EXIT%. Read the error or summary path above.)
pause
exit /b %DCR_EXIT%
:wrongdrive
echo ERROR: Save these files together in a folder on S: before running.
goto failed
:norunner
echo ERROR: case_review_runner.py must be beside this CMD.
goto failed
:notemp
echo ERROR: Cannot create the S: launcher temporary folder. Check permissions.
goto failed
:nocwd
echo ERROR: Cannot access the runner folder on S:.
:failed
pause
exit /b 1
