@echo off
echo Killing running processes...
taskkill /f /im "System Monitor Server.exe"
taskkill /f /im "System Monitor Client.exe"
taskkill /f /im "System Monitor Dashboard.exe"
taskkill /f /im "Audit Data Sample.exe"
taskkill /f /im "Config Editor.exe"
taskkill /f /im "python.exe"

echo Removing dist, build, __pycache__ folders and .spec files...
rmdir /S /Q dist
rmdir /S /Q build
rmdir /S /Q source
rmdir /S /Q __pycache__
del /f /q *.spec
del /f /q *.db*