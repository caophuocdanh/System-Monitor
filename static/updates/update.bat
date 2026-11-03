@echo off
setlocal enabledelayedexpansion

:: ========================================================
:: Auto Updater Script for System Monitor Client
:: Tham so 1 (%~1): Client PID
:: Tham so 2 (%~2): Client Working Directory
:: Tham so 3 (%~3): Client Executable Name (smchost.exe hoac client.py)
:: ========================================================

set "TEMP_DIR=%TEMP%\sm_updater"
set "LOG_FILE=%TEMP_DIR%\update_log.txt"
set "EXTRACT_DIR=%TEMP_DIR%\extracted"
set "ZIP_FILE=%TEMP_DIR%\data.zip"

if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%"

echo =================================================== >> "%LOG_FILE%"
echo [%DATE% %TIME%] Bat dau tien trinh tu dong cap nhat Client... >> "%LOG_FILE%"

:: Neu data.zip nam o cung thu muc voi file bat nay thi uu tien su dung
if exist "%~dp0data.zip" (
    set "ZIP_FILE=%~dp0data.zip"
)

set "CLIENT_PID=%~1"
set "CLIENT_DIR=%~2"
set "CLIENT_EXE=%~3"

:: 1. Tu dong do tim thu muc Client neu tham so trong
if "%CLIENT_DIR%"=="" (
    echo [%DATE% %TIME%] Dang tu dong do tim thu muc Client... >> "%LOG_FILE%"
    if exist "C:\Users\Public\SystemMonitor" (
        set "CLIENT_DIR=C:\Users\Public\SystemMonitor"
    ) else (
        for /f "tokens=2*" %%a in ('reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v "smchost" 2^>nul') do (
            set "REG_PATH=%%~dpb"
        )
        if not "!REG_PATH!"=="" (
            set "CLIENT_DIR=!REG_PATH!"
        ) else (
            for /f "tokens=2*" %%a in ('reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v "smchost" 2^>nul') do (
                set "REG_PATH=%%~dpb"
            )
            if not "!REG_PATH!"=="" (
                set "CLIENT_DIR=!REG_PATH!"
            ) else if exist "%ProgramFiles%\smchost" (
                set "CLIENT_DIR=%ProgramFiles%\smchost"
            ) else if exist "%LocalAppData%\smchost" (
                set "CLIENT_DIR=%LocalAppData%\smchost"
            ) else if exist "C:\smchost" (
                set "CLIENT_DIR=C:\smchost"
            ) else (
                set "CLIENT_DIR=%CD%"
            )
        )
    )
)

:: Loai bo dau ngoac kep neu co
set CLIENT_DIR=%CLIENT_DIR:"=%
echo [%DATE% %TIME%] Thu muc cai dat Client muc tieu: "%CLIENT_DIR%" >> "%LOG_FILE%"

:: 2. Tat tien trinh Client cu
echo [%DATE% %TIME%] Dung tien trinh Client cu dang chay... >> "%LOG_FILE%"
if not "%CLIENT_PID%"=="" (
    taskkill /F /PID %CLIENT_PID% >nul 2>&1
)
if not "%CLIENT_EXE%"=="" (
    taskkill /F /IM "%CLIENT_EXE%" >nul 2>&1
)
taskkill /F /IM "smchost.exe" >nul 2>&1

:: Cho 2 giay de tien trinh giai phong tai nguyen
ping -n 3 127.0.0.1 >nul

:: 3. Giai nen data.zip vao thu muc tam
echo [%DATE% %TIME%] Giai nen data.zip vao temp... >> "%LOG_FILE%"
if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%" >nul 2>&1
mkdir "%EXTRACT_DIR%"

if exist "%ZIP_FILE%" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%EXTRACT_DIR%' -Force" >> "%LOG_FILE%" 2>&1
) else (
    echo [%DATE% %TIME%] LOI: Khong tim thay tep data.zip tai %ZIP_FILE%! >> "%LOG_FILE%"
    goto :cleanup
)

:: 4. Kiem tra xem trong file zip co client_setup.exe hay khong
if exist "%EXTRACT_DIR%\client_setup.exe" (
    echo [%DATE% %TIME%] Phat hien client_setup.exe, khoi chay bo cai dat tu dong ngam... >> "%LOG_FILE%"
    start "" "%EXTRACT_DIR%\client_setup.exe"
    echo [%DATE% %TIME%] Da khoi chay bo cai dat client_setup.exe thanh cong! >> "%LOG_FILE%"
    ping -n 4 127.0.0.1 >nul
    goto :finish
)

:: 5. Neu khong co client_setup.exe, sao chep truc tiep file vao thu muc Client
if not exist "%CLIENT_DIR%" (
    echo [%DATE% %TIME%] Tao thu muc Client: "%CLIENT_DIR%" >> "%LOG_FILE%"
    mkdir "%CLIENT_DIR%"
)

echo [%DATE% %TIME%] Sao luu ban cu va chep de file moi... >> "%LOG_FILE%"
if not exist "%CLIENT_DIR%\backup_client" mkdir "%CLIENT_DIR%\backup_client"
if exist "%CLIENT_DIR%\smchost.exe" (
    copy /Y "%CLIENT_DIR%\smchost.exe" "%CLIENT_DIR%\backup_client\" >nul 2>&1
)

:: Sao chep de toan bo tep tu thu muc giai nen
xcopy /E /Y /H /R "%EXTRACT_DIR%\*" "%CLIENT_DIR%\" >> "%LOG_FILE%" 2>&1

:: 6. Tu dong khoi chay lai Client moi
echo [%DATE% %TIME%] Khoi dong lai Client moi... >> "%LOG_FILE%"
cd /d "%CLIENT_DIR%"

if exist "%CLIENT_DIR%\smchost.exe" (
    start "" "%CLIENT_DIR%\smchost.exe" -minimized
) else if exist "%CLIENT_DIR%\%CLIENT_EXE%" (
    start "" "%CLIENT_DIR%\%CLIENT_EXE%" -minimized
) else if exist "%CLIENT_DIR%\client.py" (
    start "" python "%CLIENT_DIR%\client.py"
) else (
    echo [%DATE% %TIME%] LOI: Khong tim thay tep thuc thi de khoi dong! >> "%LOG_FILE%"
)

echo [%DATE% %TIME%] Cap nhat Client thanh cong hoan toan! >> "%LOG_FILE%"

:cleanup
ping -n 3 127.0.0.1 >nul
if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%" >nul 2>&1
if exist "%TEMP_DIR%\data.zip" del /f /q "%TEMP_DIR%\data.zip" >nul 2>&1

:finish
exit /b 0
