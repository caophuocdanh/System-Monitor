@echo off
echo Killing running processes...
taskkill /f /im "SM Server.exe"
taskkill /f /im "smchost.exe"
taskkill /f /im "SM Dashboard.exe"
taskkill /f /im "Audit Data Sample.exe"
taskkill /f /im "Config Editor.exe"
taskkill /f /im "client.exe"
taskkill /f /im "python.exe"

echo Removing Windows Service if exists...
sc stop smchost
sc delete smchost

echo Removing dist, build, __pycache__ folders and .spec files...
rmdir /S /Q dist
rmdir /S /Q build
rmdir /S /Q source
rmdir /S /Q __pycache__
del /f /q *.spec
del /f /q *.db*