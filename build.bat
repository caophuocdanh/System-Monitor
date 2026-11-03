@echo off
echo Killing running processes...
taskkill /f /im "SM Server.exe" >nul 2>&1
taskkill /f /im "smchost.exe" >nul 2>&1
taskkill /f /im "SM Dashboard.exe" >nul 2>&1
taskkill /f /im "Audit Data Sample.exe" >nul 2>&1
taskkill /f /im "Config Editor.exe" >nul 2>&1
taskkill /f /im "client.exe" >nul 2>&1

echo Removing dist, build, __pycache__ folders and .spec files...
rmdir /S /Q dist 2>nul
rmdir /S /Q build 2>nul
rmdir /S /Q source 2>nul
rmdir /S /Q __pycache__ 2>nul
del /f /q *.spec 2>nul

echo Installing dependencies from requirements.txt...
pip install -r requirements/requirements.txt

echo Building SM Server executable...
python -m PyInstaller --console --onefile --name="SM Server" --icon="requirements\server.ico" server.py
pyinstaller --console --onefile --name="SM Server" --icon="requirements\server.ico" server.py


echo Building System Monitor Client executable (smchost)...
python -m PyInstaller --noconsole --onefile --hidden-import=win32timezone --name="smchost" --icon="requirements\client.ico" client.py
pyinstaller --noconsole --onefile --hidden-import=win32timezone --name="smchost" --icon="requirements\client.ico" client.py


echo Building SM Dashboard executable...
python -m PyInstaller --noconsole --onefile --name="SM Dashboard" --icon="requirements\dashboard.ico" dashboard.py
pyinstaller --noconsole --onefile --name="SM Dashboard" --icon="requirements\dashboard.ico" dashboard.py


echo Building Audit Data executable...
echo python -m PyInstaller --noconsole --onefile --icon="requirements\sample.ico" --name="Audit Data Sample" "Audit Data.py"
echo pyinstaller --noconsole --onefile --icon="requirements\sample.ico" --name="Audit Data Sample" "Audit Data.py"

echo Building Config Editor executable...
python -m PyInstaller --noconsole --onefile --icon="requirements\config.ico" --name="Config Editor" "config_editor.py"
pyinstaller --noconsole --onefile --icon="requirements\config.ico" --name="Config Editor" "config_editor.py"

mkdir "source"
mkdir "source\server"
mkdir "source\client"

echo Move all file from dist to source
move /Y "dist\*" "source\"

echo Copying static and template files to server folder...
xcopy static "source\server\static" /E /I /Y
xcopy templates "source\server\templates" /E /I /Y
copy config.ini "source\server\config.ini" /Y
copy config.ini "source\client\config.ini" /Y

move /Y "source\SM Dashboard.exe" "source\server\"
move /Y "source\SM Server.exe" "source\server\"
move /Y "source\Audit Data Sample.exe" "source\server\"
move /Y "source\Config Editor.exe" "source\" 2>nul
move /Y "source\smchost.exe" "source\client\"

copy "requirements\kill_all.bat" "source\kill_all.bat" /Y
copy "requirements\run_server.bat" "source\run_server.bat" /Y
copy "requirements\README.md" "source\README.md" /Y

echo.
echo ==========================================================
echo Packaging Client and Config into client_setup.exe...
echo ==========================================================
python -m PyInstaller --noconsole --onefile --name="client" --icon="requirements\client.ico" --add-data "source\client\smchost.exe;." --add-data "config.ini;." requirements\installer.py
pyinstaller --noconsole --onefile --name="client" --icon="requirements\client.ico" --add-data "source\client\smchost.exe;." --add-data "config.ini;." requirements\installer.py


move /Y "dist\client.exe" "source\client\client_setup.exe"

echo.
echo ==========================================================
echo Deploying client_setup.exe and data.zip to updates folder...
echo ==========================================================
if not exist "static\updates" mkdir "static\updates"
if not exist "source\server\static\updates" mkdir "source\server\static\updates"

:: 1. Nén client_setup.exe thành data.zip để phục vụ cập nhật
echo Compressing client_setup.exe into data.zip...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'source\client\client_setup.exe' -DestinationPath 'static\updates\data.zip' -Force"
copy /Y "static\updates\data.zip" "source\server\static\updates\data.zip"

:: 2. Đảm bảo file update.bat có sẵn trong thư mục updates
if exist "static\updates\update.bat" copy /Y "static\updates\update.bat" "source\server\static\updates\update.bat"

:: 3. Xóa các file source trong thư mục updates để giảm dung lượng không cần thiết
echo Cleaning redundant source files from updates folders...
del /F /Q "static\updates\client_setup.exe" 2>nul
del /F /Q "static\updates\smchost.exe" 2>nul
del /F /Q "static\updates\config.ini" 2>nul
del /F /Q "static\updates\updater.bat" 2>nul

del /F /Q "source\server\static\updates\client_setup.exe" 2>nul
del /F /Q "source\server\static\updates\smchost.exe" 2>nul
del /F /Q "source\server\static\updates\config.ini" 2>nul
del /F /Q "source\server\static\updates\updater.bat" 2>nul

rmdir /S /Q dist 2>nul
rmdir /S /Q build 2>nul
del /f /q *.spec 2>nul

echo Starting the application...
start source

echo Done!
