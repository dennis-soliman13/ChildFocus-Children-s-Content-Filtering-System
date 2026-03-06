@echo off
title ChildFocus Setup
color 0A
echo.
echo ================================================
echo   ChildFocus - Automated Setup Script
echo   Children's Content Filtering System
echo ================================================
echo.

:: -- Required Versions -------------------------------------------------------
set REQUIRED_NODE=24.14.0
set REQUIRED_FFMPEG=8.0.1
set REQUIRED_PYTHON=3.13

set NODE_URL=https://nodejs.org/dist/v24.14.0/node-v24.14.0-x64.msi
set FFMPEG_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
set PYTHON_URL=https://www.python.org/ftp/python/3.13.0/python-3.13.0-amd64.exe

:: -- Check for curl -----------------------------------------------------------
curl --version >nul 2>&1
if errorlevel 1 (
    echo [FAIL] curl not found. Windows 10/11 should have it built-in.
    echo        Please install prerequisites manually.
    pause
    exit /b 1
)

:: -- Check for PowerShell -----------------------------------------------------
powershell -Command "exit" >nul 2>&1
if errorlevel 1 (
    echo [FAIL] PowerShell not found. Required for ffmpeg extraction.
    pause
    exit /b 1
)

echo Checking your system for required tools...
echo.

:: =============================================================================
:: STEP 1 - PYTHON
:: =============================================================================
echo [1/6] Checking Python %REQUIRED_PYTHON%...
set PYTHON=

python --version >nul 2>&1
if not errorlevel 1 set PYTHON=python

py --version >nul 2>&1
if not errorlevel 1 set PYTHON=py

py -3.13 --version >nul 2>&1
if not errorlevel 1 set PYTHON=py -3.13

py -3.11 --version >nul 2>&1
if not errorlevel 1 if "%PYTHON%"=="" set PYTHON=py -3.11

if "%PYTHON%"=="" if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set PYTHON="%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if "%PYTHON%"=="" if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set PYTHON="%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if "%PYTHON%"=="" if exist "C:\Python313\python.exe" set PYTHON=C:\Python313\python.exe
if "%PYTHON%"=="" if exist "C:\Python311\python.exe" set PYTHON=C:\Python311\python.exe

if "%PYTHON%"=="" goto :PY_MISSING
%PYTHON% --version 2>&1 | findstr "3.13" >nul
if errorlevel 1 goto :PY_WRONG_VERSION
goto :PY_OK

:PY_MISSING
echo [MISSING] Python is not installed or not found in PATH.
echo.
set CONFIRM_PY=n
set /p CONFIRM_PY="Download and install Python %REQUIRED_PYTHON% now? (y/n): "
if /i "%CONFIRM_PY%"=="y" goto :PY_DOWNLOAD
echo [SKIP] Python not installed. Setup cannot continue without Python.
pause
exit /b 1

:PY_WRONG_VERSION
echo Found: & %PYTHON% --version
echo.
echo [WARN] Python 3.13 is recommended. You currently have a different version.
echo        Python 3.11 may work but some packages could behave differently.
echo.
echo   What would you like to do?
echo   [1] Install Python 3.13 alongside current version (both kept)
echo   [2] Uninstall current Python then install Python 3.13 (clean swap)
echo   [3] Keep current version and continue
echo.
set PY_CHOICE=3
set /p PY_CHOICE="Enter choice (1/2/3): "
if "%PY_CHOICE%"=="1" goto :PY_DOWNLOAD
if "%PY_CHOICE%"=="2" goto :PY_UNINSTALL_THEN_INSTALL
echo [CONTINUE] Keeping current Python version - continuing setup.
goto :PY_DONE

:PY_DOWNLOAD
echo Downloading Python %REQUIRED_PYTHON%...
curl -L -o "%~dp0python_installer.exe" "%PYTHON_URL%" --progress-bar
echo Installing Python %REQUIRED_PYTHON%...
"%~dp0python_installer.exe" /passive PrependPath=1
del "%~dp0python_installer.exe"
set PYTHON=py -3.13
echo [OK] Python %REQUIRED_PYTHON% installed.
echo      Please RESTART this script for PATH to update.
pause
exit /b 0

:PY_UNINSTALL_THEN_INSTALL
echo.
echo [INFO] Uninstalling current Python via Windows...
powershell -Command "Get-Package -Provider msi -Name 'Python 3.11*' -ErrorAction SilentlyContinue | ForEach-Object { Start-Process msiexec -ArgumentList '/x',$_.FastPackageReference,'/passive','/norestart' -Wait }" >nul 2>&1
powershell -Command "Get-Package -Provider Programs -Name 'Python 3.11*' -ErrorAction SilentlyContinue | Uninstall-Package -Force" >nul 2>&1
echo [OK] Python 3.11 uninstalled.
echo.
echo Downloading Python %REQUIRED_PYTHON%...
curl -L -o "%~dp0python_installer.exe" "%PYTHON_URL%" --progress-bar
echo Installing Python %REQUIRED_PYTHON%...
"%~dp0python_installer.exe" /passive PrependPath=1
del "%~dp0python_installer.exe"
echo [OK] Python %REQUIRED_PYTHON% installed cleanly.
echo      Please RESTART this script for PATH to fully update.
pause
exit /b 0

:PY_OK
%PYTHON% --version
echo [OK] Python %REQUIRED_PYTHON% confirmed.

:PY_DONE
echo.

:: =============================================================================
:: STEP 2 - NODE.JS
:: =============================================================================
echo [2/6] Checking Node.js v%REQUIRED_NODE%...
node --version >nul 2>&1
if errorlevel 1 goto :NODE_MISSING
node --version 2>&1 | findstr "%REQUIRED_NODE%" >nul
if errorlevel 1 goto :NODE_WRONG_VERSION
goto :NODE_OK

:NODE_MISSING
echo [MISSING] Node.js is not installed.
echo.
set CONFIRM_NODE=n
set /p CONFIRM_NODE="Download and install Node.js v%REQUIRED_NODE% now? (y/n): "
if /i "%CONFIRM_NODE%"=="y" goto :NODE_DOWNLOAD
echo [SKIP] Node.js not installed. YouTube extraction will not work.
echo        Install manually from: https://nodejs.org
goto :NODE_DONE

:NODE_WRONG_VERSION
echo [WARN] Node.js v%REQUIRED_NODE% recommended but a different version was found:
node --version
echo.
echo   What would you like to do?
echo   [1] Uninstall current Node.js then install v%REQUIRED_NODE% (clean swap)
echo   [2] Keep current version and continue
echo.
set NODE_CHOICE=2
set /p NODE_CHOICE="Enter choice (1/2): "
if "%NODE_CHOICE%"=="1" goto :NODE_UNINSTALL_THEN_INSTALL
echo [CONTINUE] Keeping current Node.js version. May still work.
goto :NODE_DONE

:NODE_UNINSTALL_THEN_INSTALL
echo.
echo [INFO] Uninstalling current Node.js...
powershell -Command "Get-Package -Name 'Node.js*' -ErrorAction SilentlyContinue | ForEach-Object { Start-Process msiexec -ArgumentList '/x',$_.FastPackageReference,'/passive','/norestart' -Wait }" >nul 2>&1
echo [OK] Node.js uninstalled.
echo.

:NODE_DOWNLOAD
echo Downloading Node.js v%REQUIRED_NODE% ^(~30MB^)...
curl -L -o "%~dp0node_installer.msi" "%NODE_URL%" --progress-bar
echo Installing Node.js v%REQUIRED_NODE%...
msiexec /i "%~dp0node_installer.msi" /passive /norestart
del "%~dp0node_installer.msi"
echo [OK] Node.js v%REQUIRED_NODE% installed.
echo      Please RESTART this script for PATH to update.
pause
exit /b 0

:NODE_OK
node --version
echo [OK] Node.js v%REQUIRED_NODE% confirmed.

:NODE_DONE
echo.

:: =============================================================================
:: STEP 3 - FFMPEG
:: =============================================================================
echo [3/6] Checking ffmpeg %REQUIRED_FFMPEG%...

:: Check if already working in PATH first
ffmpeg -version >nul 2>&1
if not errorlevel 1 goto :FFMPEG_IN_PATH

:: Search for ffmpeg.exe in all likely locations and subfolder structures:
::   D:\ffmpeg\ffmpeg.exe
::   D:\ffmpeg\bin\ffmpeg.exe
::   D:\ffmpeg\ffmpeg-8.x.x-essentials_build\bin\ffmpeg.exe
set FFMPEG_FOUND_PATH=

if exist "D:\ffmpeg\ffmpeg.exe"     set FFMPEG_FOUND_PATH=D:\ffmpeg
if exist "D:\ffmpeg\bin\ffmpeg.exe" set FFMPEG_FOUND_PATH=D:\ffmpeg\bin

if "%FFMPEG_FOUND_PATH%"=="" (
    for /d %%D in ("D:\ffmpeg\*") do (
        if exist "%%D\bin\ffmpeg.exe" if "%FFMPEG_FOUND_PATH%"=="" set FFMPEG_FOUND_PATH=%%D\bin
        if exist "%%D\ffmpeg.exe"     if "%FFMPEG_FOUND_PATH%"=="" set FFMPEG_FOUND_PATH=%%D
    )
)

if exist "C:\ffmpeg\ffmpeg.exe"     if "%FFMPEG_FOUND_PATH%"=="" set FFMPEG_FOUND_PATH=C:\ffmpeg
if exist "C:\ffmpeg\bin\ffmpeg.exe" if "%FFMPEG_FOUND_PATH%"=="" set FFMPEG_FOUND_PATH=C:\ffmpeg\bin

if "%FFMPEG_FOUND_PATH%"=="" (
    for /d %%D in ("C:\ffmpeg\*") do (
        if exist "%%D\bin\ffmpeg.exe" if "%FFMPEG_FOUND_PATH%"=="" set FFMPEG_FOUND_PATH=%%D\bin
        if exist "%%D\ffmpeg.exe"     if "%FFMPEG_FOUND_PATH%"=="" set FFMPEG_FOUND_PATH=%%D
    )
)

if "%FFMPEG_FOUND_PATH%"=="" goto :FFMPEG_MISSING

echo [INFO] Found ffmpeg.exe at: %FFMPEG_FOUND_PATH%
echo [INFO] Adding to session PATH and persisting to system PATH...
set PATH=%PATH%;%FFMPEG_FOUND_PATH%
powershell -Command "[Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path','Machine') + ';%FFMPEG_FOUND_PATH%', 'Machine')" >nul 2>&1
echo [OK] PATH updated permanently.

:FFMPEG_IN_PATH
ffmpeg -version 2>&1 | findstr "%REQUIRED_FFMPEG%" >nul
if errorlevel 1 goto :FFMPEG_WRONG_VERSION
goto :FFMPEG_OK

:FFMPEG_MISSING
echo [MISSING] ffmpeg not found in PATH or any of these locations:
echo          D:\ffmpeg, D:\ffmpeg\bin, D:\ffmpeg\^<subfolder^>\bin
echo          C:\ffmpeg, C:\ffmpeg\bin, C:\ffmpeg\^<subfolder^>\bin
echo.
set CONFIRM_FF=n
set /p CONFIRM_FF="Download and install ffmpeg %REQUIRED_FFMPEG% now? (y/n): "
if /i "%CONFIRM_FF%"=="y" goto :FFMPEG_DOWNLOAD
echo [SKIP] ffmpeg not installed. Audio analysis will use fallback.
echo        Install manually from: https://www.gyan.dev/ffmpeg/builds/
goto :FFMPEG_DONE

:FFMPEG_WRONG_VERSION
echo [WARN] ffmpeg %REQUIRED_FFMPEG% recommended but a different version was found:
ffmpeg -version 2>&1 | findstr "ffmpeg version"
echo.
echo   What would you like to do?
echo   [1] Uninstall current ffmpeg then install %REQUIRED_FFMPEG% (clean swap)
echo   [2] Keep current version and continue
echo.
set FF_CHOICE=2
set /p FF_CHOICE="Enter choice (1/2): "
if "%FF_CHOICE%"=="1" goto :FFMPEG_REMOVE_OLD
echo [CONTINUE] Keeping current ffmpeg version. May still work.
goto :FFMPEG_DONE

:FFMPEG_REMOVE_OLD
echo [INFO] Removing old ffmpeg from C:\ffmpeg and D:\ffmpeg...
if exist "C:\ffmpeg" rmdir /s /q "C:\ffmpeg"
if exist "D:\ffmpeg" rmdir /s /q "D:\ffmpeg"
powershell -Command "$p=[Environment]::GetEnvironmentVariable('Path','Machine'); $p=$p -replace ';C:\\ffmpeg\\bin',''; $p=$p -replace ';D:\\ffmpeg\\bin',''; [Environment]::SetEnvironmentVariable('Path',$p,'Machine')" >nul 2>&1
echo [OK] Old ffmpeg removed.

:FFMPEG_DOWNLOAD
echo.
echo Downloading ffmpeg %REQUIRED_FFMPEG% ^(~90MB^)...
set FFMPEG_ZIP=%~dp0ffmpeg-download.zip
curl -L -o "%FFMPEG_ZIP%" "%FFMPEG_URL%" --progress-bar
if errorlevel 1 (
    echo [FAIL] Download failed. Check internet connection.
    echo        Download manually: https://www.gyan.dev/ffmpeg/builds/
    del "%FFMPEG_ZIP%" >nul 2>&1
    goto :FFMPEG_DONE
)
echo Download complete. Extracting...

set CHILDFOCUS_DRIVE=%~d0
if /i "%CHILDFOCUS_DRIVE%"=="D:" (
    set FFMPEG_DIR=D:\ffmpeg
) else (
    set FFMPEG_DIR=C:\ffmpeg
)

echo [INFO] Installing ffmpeg to %FFMPEG_DIR%...
if exist "%FFMPEG_DIR%" rmdir /s /q "%FFMPEG_DIR%"

set FFMPEG_EXTRACT=%~dp0ffmpeg-extract
if exist "%FFMPEG_EXTRACT%" rmdir /s /q "%FFMPEG_EXTRACT%"
powershell -Command "Expand-Archive -Path '%FFMPEG_ZIP%' -DestinationPath '%FFMPEG_EXTRACT%' -Force"
if errorlevel 1 (
    echo [FAIL] Extraction failed.
    del "%FFMPEG_ZIP%" >nul 2>&1
    goto :FFMPEG_DONE
)

powershell -Command "Get-ChildItem '%FFMPEG_EXTRACT%' | Select-Object -First 1 | ForEach-Object { Move-Item $_.FullName '%FFMPEG_DIR%' -Force }"
rmdir /s /q "%FFMPEG_EXTRACT%" >nul 2>&1
del "%FFMPEG_ZIP%" >nul 2>&1

powershell -Command "[Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path','Machine') + ';%FFMPEG_DIR%\bin', 'Machine')" >nul 2>&1
set PATH=%PATH%;%FFMPEG_DIR%\bin

echo [OK] ffmpeg %REQUIRED_FFMPEG% installed to %FFMPEG_DIR%\bin
echo      PATH updated. Verifying...
"%FFMPEG_DIR%\bin\ffmpeg.exe" -version 2>&1 | findstr "ffmpeg version"
echo.
goto :FFMPEG_DONE

:FFMPEG_OK
ffmpeg -version 2>&1 | findstr "ffmpeg version"
echo [OK] ffmpeg %REQUIRED_FFMPEG% confirmed.

:FFMPEG_DONE
echo.

:: =============================================================================
:: STEP 4 - ANDROID STUDIO (MANUAL INSTALL - NOT AUTO-INSTALLED BY THIS SCRIPT)
:: =============================================================================
echo [4/6] Checking Android Studio...
echo.

set AS_FOUND=0
reg query "HKEY_LOCAL_MACHINE\SOFTWARE\Android Studio" >nul 2>&1
if not errorlevel 1 set AS_FOUND=1
reg query "HKEY_CURRENT_USER\SOFTWARE\Android Studio" >nul 2>&1
if not errorlevel 1 set AS_FOUND=1
if exist "%LOCALAPPDATA%\Google\AndroidStudio2025.3.1\studio.exe" set AS_FOUND=1
if exist "%PROGRAMFILES%\Android\Android Studio\bin\studio64.exe" set AS_FOUND=1
if exist "D:\Android Studio\bin\studio64.exe" (
    echo [INFO] Found Android Studio binary on D: drive.
    set AS_FOUND=1
)

if "%AS_FOUND%"=="0" goto :AS_MISSING

:: Read version from registry
set AS_VER_FOUND=
for /f "tokens=2*" %%A in ('reg query "HKEY_LOCAL_MACHINE\SOFTWARE\Android Studio" /v "Version" 2^>nul') do set AS_VER_FOUND=%%B
if "%AS_VER_FOUND%"=="" for /f "tokens=2*" %%A in ('reg query "HKEY_CURRENT_USER\SOFTWARE\Android Studio" /v "Version" 2^>nul') do set AS_VER_FOUND=%%B

if "%AS_VER_FOUND%"=="" goto :AS_VERSION_UNKNOWN

:: Accept any 2025.3.x patch - the whole Panda 1 series is compatible
echo "%AS_VER_FOUND%" | findstr "2025.3" >nul
if errorlevel 1 goto :AS_WRONG_VERSION
goto :AS_OK

:AS_MISSING
echo [NOT FOUND] Android Studio is not installed.
echo.
echo ================================================
echo   ANDROID STUDIO - MANUAL INSTALL REQUIRED
echo ================================================
echo.
echo   Required version : Panda 1  ^|  2025.3.1 Patch 1
echo   Your team has agreed on this version.
echo.
echo   Why this version?
echo     Your project uses:
echo       AGP      8.9.0           ^(build.gradle.kts^)
echo       Kotlin   2.0.21
echo       KSP      2.0.21-1.0.28
echo       SDK      35  ^(compile + target^)
echo       Java     21
echo     All of these are fully supported by Panda 1.
echo     Using a different version risks Gradle sync
echo     errors and build mismatches across the team.
echo.
echo   Download:
echo     https://developer.android.com/studio/archive
echo     Find    : Android Studio Panda  ^|  2025.3.1
echo     Choose  : Windows ^(64-bit^) .exe
echo.
echo   Install tips:
echo     Default path : C:\Program Files\Android\Android Studio
echo     D: drive     : Change path to  D:\Android Studio
echo     After install on D:, run in a new CMD:
echo       setx ANDROID_HOME "D:\Android\Sdk"
echo       setx PATH "%%PATH%%;D:\Android\Sdk\platform-tools"
echo.
echo ================================================
echo.
echo Setup will continue. Re-run setup.bat after
echo installing Android Studio to verify the version.
echo.
goto :AS_DONE

:AS_WRONG_VERSION
echo [WARN] Android Studio found but wrong version detected.
echo.
echo ================================================
echo   WRONG ANDROID STUDIO VERSION
echo ================================================
echo.
echo   Found    : %AS_VER_FOUND%
echo   Required : Panda 1  ^|  2025.3.1  ^(any 2025.3.x^)
echo.
echo   Your team uses Panda 1. Using a different
echo   version may cause Gradle sync failures or
echo   build errors for other team members.
echo.
echo   To install the correct version:
echo     https://developer.android.com/studio/archive
echo     Find   : Android Studio Panda  ^|  2025.3.1
echo     Choose : Windows ^(64-bit^) .exe
echo.
echo ================================================
echo.
goto :AS_DONE

:AS_VERSION_UNKNOWN
echo [WARN] Android Studio is installed but the version could not be read.
echo.
echo   Please verify manually:
echo     1. Open Android Studio
echo     2. Click  Help  ^>  About
echo     3. Confirm version shows  2025.3.x  ^(Panda 1^)
echo.
echo   Required : Panda 1  ^|  2025.3.1
echo   Download : https://developer.android.com/studio/archive
echo.
goto :AS_DONE

:AS_OK
echo [OK] Android Studio %AS_VER_FOUND% confirmed ^(Panda 1^).

:AS_DONE
echo.

:: =============================================================================
:: STEP 5 - PYTHON PACKAGES
:: =============================================================================
echo [5/6] Installing Python packages from requirements.txt...
echo       This may take 3-5 minutes on first run...
echo.
if not exist "backend\requirements.txt" (
    echo [FAIL] backend\requirements.txt not found.
    echo        Make sure you run setup.bat from the root ChildFocus folder.
    pause
    exit /b 1
)
cd backend
%PYTHON% -m pip install --upgrade pip --quiet
%PYTHON% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [FAIL] Package installation failed.
    echo        Try right-clicking setup.bat and selecting "Run as Administrator"
    pause
    exit /b 1
)
echo.
echo [OK] All Python packages installed.
echo.

:: =============================================================================
:: STEP 6 - CREATE .ENV + VERIFY IMPORTS
:: =============================================================================
echo [6/6] Checking .env and verifying packages...
if not exist ".env" (
    echo [INFO] No .env file found. Creating template...
    (
        echo YOUTUBE_API_KEY=your_youtube_api_key_here
        echo FLASK_ENV=development
        echo FLASK_DEBUG=1
    ) > .env
    echo.
    echo [ACTION REQUIRED] Open backend\.env and replace:
    echo    your_youtube_api_key_here
    echo    with your YouTube Data API v3 key from:
    echo    https://console.cloud.google.com/apis/credentials
    echo    ^> Create Credentials ^> API Key ^> restrict to YouTube Data API v3
    echo.
) else (
    findstr "your_youtube_api_key_here" .env >nul
    if not errorlevel 1 (
        echo [WARN] .env exists but API key is still a placeholder.
        echo        Open backend\.env and replace your_youtube_api_key_here
        echo        with your real YouTube Data API v3 key.
    ) else (
        echo [OK] .env file found and API key is set.
    )
)
echo.

%PYTHON% -c "import flask, cv2, librosa, yt_dlp, numpy, requests, dotenv; print('[OK] All core packages verified.')"
if errorlevel 1 (
    echo [WARN] Some packages may not have installed correctly.
    echo        Try: pip install -r requirements.txt
    echo        Or run setup.bat as Administrator.
)
echo.
cd ..

:: =============================================================================
:: DONE - CHECKLIST + NEXT STEPS
:: =============================================================================
echo.
echo ================================================
echo   ChildFocus Setup - COMPLETE
echo ================================================
echo.
echo ------------------------------------------
echo   INSTALLATION CHECKLIST
echo   Review each item before starting the server.
echo ------------------------------------------
echo.
echo   AUTO-CHECKED BY THIS SCRIPT
echo   --------------------------------
echo   [ ] Python 3.13
echo       Verify : py --version  ^>  Python 3.13.x
echo.
echo   [ ] Node.js v24.14.0
echo       Verify : node --version  ^>  v24.14.0
echo.
echo   [ ] ffmpeg 8.0.1
echo       Verify : ffmpeg -version  ^>  ffmpeg version 8.0.1
echo.
echo   [ ] Python packages
echo       Verify : step 6 above showed [OK]
echo.
echo   MANUAL STEPS REQUIRED
echo   --------------------------------
echo   [ ] Android Studio Panda 1  ^|  2025.3.1 Patch 1
echo       Download : https://developer.android.com/studio/archive
echo       Verify   : Help ^> About ^> version shows 2025.3.x
echo       ---
echo       This version is required for your project:
echo         AGP 8.9.0 / Kotlin 2.0.21 / KSP 2.0.21-1.0.28
echo         compileSdk 35 / targetSdk 35 / Java 21
echo       All 3 team members must use the same version.
echo.
echo   [ ] YouTube API key in backend\.env
echo       Replace  your_youtube_api_key_here  with real key:
echo       https://console.cloud.google.com/apis/credentials
echo.
echo ------------------------------------------
echo   STEP-BY-STEP: RUNNING CHILDFOCUS
echo ------------------------------------------
echo.
echo   STEP 1 - Open a NEW Command Prompt
echo            Start Menu ^> type cmd ^> Enter
echo            ^(fresh window loads updated PATH^)
echo.
echo   STEP 2 - Navigate to the backend folder:
echo            cd /d "%~dp0backend"
echo.
echo   STEP 3 - Start the server:
echo            py run.py
echo            Wait for:  * Running on http://127.0.0.1:5000
echo.
echo   STEP 4 - Test ^(in a SECOND CMD window^):
echo.
echo   curl -X POST http://localhost:5000/classify_full -H "Content-Type: application/json" -d "{\"video_url\":\"https://www.youtube.com/watch?v=pkD3Q2bpsqs\",\"thumbnail_url\":\"https://i.ytimg.com/vi/pkD3Q2bpsqs/hqdefault.jpg\"}"
echo.
echo   STEP 5 - Stop the server:
echo            Ctrl + C  in the server CMD window.
echo.
echo ------------------------------------------
echo   TROUBLESHOOTING QUICK REFERENCE
echo ------------------------------------------
echo.
echo   'py' not recognized     ^> Restart CMD or reinstall Python
echo                              with "Add to PATH" checked.
echo.
echo   pip install fails       ^> Right-click setup.bat
echo                              ^> Run as Administrator.
echo.
echo   Gradle sync errors      ^> Confirm Android Studio is Panda 1
echo                              ^(2025.3.x^) via Help ^> About.
echo                              Wrong version = AGP/Kotlin conflicts.
echo.
echo   ANDROID_HOME not set    ^> If SDK is on D:, run in new CMD:
echo                              setx ANDROID_HOME "D:\Android\Sdk"
echo                              setx PATH "%%PATH%%;D:\Android\Sdk\platform-tools"
echo                              Then restart CMD and Android Studio.
echo.
echo   Server port 5000 in use ^> Close other apps or change port
echo                              in backend\run.py.
echo.
echo ================================================
pause
