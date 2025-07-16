@echo off
echo Killing running processes...
taskkill /f /im "System Monitor Server.exe" >nul 2>&1
taskkill /f /im "System Monitor Client.exe" >nul 2>&1
taskkill /f /im "System Monitor Dashboard.exe" >nul 2>&1

echo Starting programs...
start "" "System Monitor Client.exe"
start "" "System Monitor Dashboard.exe"
start "System Monitor Server" "System Monitor Server.exe"