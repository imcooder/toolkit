@ECHO OFF&(PUSHD "%~DP0")&(REG QUERY "HKU\S-1-5-19">NUL 2>&1)||(
powershell -Command "Start-Process '%~sdpnx0' -Verb RunAs"&&EXIT)

VER|FINDSTR "5\.[0-9]\.[0-9][0-9]*" > NUL && (
ECHO.&ECHO ��ǰ�汾��֧��WinXP &PAUSE>NUL&EXIT)

rd/s/q "%AppData%\Sublime Text" 2>NUL

:MENU
ECHO.&ECHO 1�����ϵͳ�Ҽ� Sublime Text ����
ECHO.&ECHO 2��ɾ��ϵͳ�Ҽ� Sublime Text ����
IF EXIST "%WinDir%\System32\CHOICE.exe" CHOICE /C 12 /N >NUL 2>NUL
IF EXIST "%WinDir%\System32\CHOICE.exe" IF "%ERRORLEVEL%"=="2" GOTO RemoveMenu
IF EXIST "%WinDir%\System32\CHOICE.exe" IF "%ERRORLEVEL%"=="1" GOTO AddMenu
IF NOT EXIST "%WinDir%\System32\CHOICE.exe" ECHO.&SET /p choice=�����������ûس�����
IF NOT EXIST "%WinDir%\System32\CHOICE.exe" IF NOT "%choice%"=="" SET choice=%choice:~0,1%
IF NOT EXIST "%WinDir%\System32\CHOICE.exe" IF /I "%choice%"=="1" GOTO AddMenu
IF NOT EXIST "%WinDir%\System32\CHOICE.exe" IF /I "%choice%"=="2" GOTO RemoveMenu
IF NOT EXIST "%WinDir%\System32\CHOICE.exe" ECHO.&ECHO ������Ч &PAUSE&CLS&GOTO MENU

:AddMenu
reg add "HKCR\*\shell\Sublime Text" /f /v "" /d "�� &Sublime Text ��" >NUL 2>NUL
reg add "HKCR\*\shell\Sublime Text" /f /v "Icon" /d "%~dp0sublime_text.exe" >NUL 2>NUL
reg add "HKCR\*\shell\Sublime Text\command" /f /v "" /d "%~dp0sublime_text.exe \"%%1\"" >NUL 2>NUL
IF EXIST "%WinDir%\System32\CHOICE.exe" ( 
ECHO.&ECHO ����� &TIMEOUT /t 2 >NUL & CLS & GOTO MENU
) ELSE ( 
ECHO.&ECHO ����ӣ���������� &PAUSE>NUL&CLS&GOTO MENU) 

:RemoveMenu
reg delete "HKCR\*\shell\Sublime Text" /f >NUL 2>NUL
reg delete "HKLM\*\shell\Sublime Text" /f >NUL 2>NUL
IF EXIST "%WinDir%\System32\CHOICE.exe" ( 
ECHO.&ECHO ��ɾ�� &TIMEOUT /t 2 >NUL & CLS & GOTO MENU
) ELSE ( 
ECHO.&ECHO ��ɾ������������� &PAUSE>NUL&CLS&GOTO MENU) 