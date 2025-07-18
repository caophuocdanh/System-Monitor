@echo off
echo Killing running processes...
taskkill /f /im "System Monitor Server.exe"
taskkill /f /im "System Monitor Client.exe"
taskkill /f /im "System Monitor Dashboard.exe"
taskkill /f /im "Audit Data Sample.exe"
taskkill /f /im "Config Editor.exe"

echo Removing dist, build, __pycache__ folders and .spec files...
rmdir /S /Q dist
rmdir /S /Q build
rmdir /S /Q source
rmdir /S /Q __pycache__
del /f /q *.spec

echo Installing dependencies from requirements.txt...
pip install -r requirements/requirements.txt

echo Building System Monitor Server executable...
pyinstaller --console --onefile --name="System Monitor Server" --icon="requirements\server.ico" server.py

echo Building System Monitor Client executable...
pyinstaller --noconsole --onefile --name="System Monitor Client" --icon="requirements\client.ico" client.py

echo Building System Monitor Dashboard executable...
pyinstaller --noconsole --onefile --name="System Monitor Dashboard" --icon="requirements\dashboard.ico" dashboard.py

echo Building Audit Data executable...
pyinstaller --noconsole --onefile --icon="requirements\sample.ico" --name="Audit Data Sample" "Audit Data.py"

echo Building Config Editor executable...
pyinstaller --noconsole --onefile --icon="requirements\config.ico" --name="Config Editor" "config_editor.py"

mkdir "source"
mkdir "source\server"
mkdir "source\client"

echo Move all file from dist to source
move /Y "dist\*" "source\"

echo Copying static and template files to dist folder...
xcopy static "source\server\static" /E /I /Y
xcopy templates "source\server\templates" /E /I /Y
copy config.ini "source\server\config.ini" /Y
copy config.ini "source\client\config.ini" /Y

move /Y "source\System Monitor Dashboard.exe" "source\server\"
move /Y "source\System Monitor Server.exe" "source\server\"
move /Y "source\System Monitor Client.exe" "source\client\"

copy "requirements\kill_all.bat" "source\kill_all.bat" /Y
copy "requirements\run_server.bat" "source\run_server.bat" /Y
rmdir /S /Q dist
rmdir /S /Q build
del /f /q *.spec


echo Starting the application...
start source

echo Done!