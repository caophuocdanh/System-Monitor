@echo off
echo Killing running processes...
taskkill /f /im "SM Server.exe" >nul 2>&1
taskkill /f /im "smchost.exe" >nul 2>&1
taskkill /f /im "SM Dashboard.exe" >nul 2>&1

cd "server"
start "SM Dashboard" "SM Dashboard.exe"
start "SM Server" "SM Server.exe"


echo Starting programs...
cd "..\client"
start "smchost" "smchost.exe"