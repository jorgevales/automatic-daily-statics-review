@echo off
rem Test run: same as Run_case_reviews_DIAGNOSE.cmd, but Edge is started with your normal
rem Windows user folders instead of the copies the tool keeps on S:.
rem Use it only when the diagnose report suggests it. Real submissions still happen.
call "%~dp0Run_case_reviews.cmd" --diagnose --edge-original-env %*
exit /b %ERRORLEVEL%
