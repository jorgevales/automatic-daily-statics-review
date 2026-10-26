@echo off
rem Same run as Run_case_reviews.cmd (real submissions), recorded in full.
rem At the end it prints the likely cause in plain English and saves two reports:
rem   INTERNAL_do_not_share.md  - everything, keep inside the VDI
rem   EXTERNAL_safe_to_share.md - identifying details removed, safe to send back
call "%~dp0Run_case_reviews.cmd" --diagnose %*
exit /b %ERRORLEVEL%
