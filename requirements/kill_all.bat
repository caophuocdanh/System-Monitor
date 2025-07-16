@echo off
echo Killing running processes...
taskkill /f /im "System Monitor Server.exe" >nul 2>&1
taskkill /f /im "System Monitor Client.exe" >nul 2>&1
taskkill /f /im "System Monitor Dashboard.exe" >nul 2>&1