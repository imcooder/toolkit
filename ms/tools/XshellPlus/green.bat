@ECHO OFF&PUSHD %~DP0 &TITLE 绿化 www.Laomo.me
>NUL 2>&1 REG.exe query "HKU\S-1-5-19" || (
    ECHO SET UAC = CreateObject^("Shell.Application"^) > "%TEMP%\Getadmin.vbs"
    ECHO UAC.ShellExecute "%~f0", "%1", "", "runas", 1 >> "%TEMP%\Getadmin.vbs"
    "%TEMP%\Getadmin.vbs"
    DEL /f /q "%TEMP%\Getadmin.vbs" 2>NUL
    Exit /b
)

taskkill /f /im Xftp* >NUL 2>NUL
taskkill /f /im Xshell* >NUL 2>NUL

net stop "FlexNet Licensing Service" >NUL 2>NUL
sc delete "FlexNet Licensing Service" >NUL 2>NUL
reg delete "HKCU\Software\Microsoft\NetLicense" /F>NUL 2>NUL
reg delete "HKLM\SYSTEM\CurrentControlSet\Services\FlexNet Licensing Service" /f >NUL 2>NUL

regsvr32 /s NsCopyHook3.dll

::关联会话文件格式
reg add "HKLM\SOFTWARE\Classes\.xfp" /f /ve /d "Xftp.xfp" >NUL 2>NUL
reg add "HKLM\SOFTWARE\Classes\.xsh" /f /ve /d "Xshell.xsh" >NUL 2>NUL
reg add "HKLM\SOFTWARE\Classes\.xts" /f /ve /d "Xtransport.xts" >NUL 2>NUL
reg add "HKLM\SOFTWARE\Classes\Xshell.xsh" /f /ve /d "Xshell session" >NUL 2>NUL
reg add "HKLM\SOFTWARE\Classes\Xshell.xsh\DefaultIcon" /f /ve /d "%~dp0Xshell.exe,0" >NUL 2>NUL
reg add "HKLM\SOFTWARE\Classes\Xshell.xsh\shell\open\command" /f /ve /d "\"%~dp0Xshell.exe\" \"%%1\"" >NUL 2>NUL
reg add "HKLM\SOFTWARE\Classes\Xftp.xfp\DefaultIcon" /f /ve /d "%~dp0Xftp.exe,0" >NUL 2>NUL
reg add "HKLM\SOFTWARE\Classes\Xftp.xfp\shell\open\command" /f /ve /d "\"%~dp0Xftp.exe\" \"%%1\"" >NUL 2>NUL
reg add "HKLM\SOFTWARE\Classes\Xtransport.xts\shell\open\command" /f /ve /d "\"%~dp0Xtransport.exe\" -f \"%%1\"" >NUL 2>NUL
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Xshell.exe" /f /ve /d "%~dp0Xshell.exe" >NUL 2>NUL
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Xagent.exe" /f /ve /d "%~dp0Xagent.exe" >NUL 2>NUL

::刷新关联会话文件图标
assoc .=.file >nul 2>nul & RunDll32.exe USER32.DLL,UpdatePerUserSystemParameters

::定义软件所在位置
if "%PROCESSOR_ARCHITECTURE%"=="x86" reg add "HKLM\SOFTWARE\NetSarang\Xftp\6" /f /v Path /d "%~dp0" >NUL 2>NUL
::关于显示版本号（如无该键值关于对话框则不显示版本号）
if "%PROCESSOR_ARCHITECTURE%"=="x86" reg add "HKLM\SOFTWARE\NetSarang\Xftp\6" /f /v Version /d "6.0.0183" >NUL 2>NUL
::必要产品检测信息（如果不存这二进制数据在则启动失败）
if "%PROCESSOR_ARCHITECTURE%"=="x86" reg add "HKLM\SOFTWARE\NetSarang\Xftp\6" /f /v MagicCode /t REG_BINARY /d "56754d0c95cb370583daaa4abc0aea90e40702001900" >NUL 2>NUL
If "%PROCESSOR_ARCHITECTURE%"=="AMD64" reg add "HKLM\SOFTWARE\Wow6432Node\NetSarang\Xftp\6" /f /v Path /d "%~dp0" >NUL 2>NUL
If "%PROCESSOR_ARCHITECTURE%"=="AMD64" reg add "HKLM\SOFTWARE\Wow6432Node\NetSarang\Xftp\6" /f /v Version /d "6.0.0183" >NUL 2>NUL
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" reg add "HKLM\SOFTWARE\Wow6432Node\NetSarang\Xftp\6" /f /v MagicCode /t REG_BINARY /d "56754d0c95cb370583daaa4abc0aea90e40702001900" >NUL 2>NUL

if "%PROCESSOR_ARCHITECTURE%"=="x86" reg add "HKLM\SOFTWARE\NetSarang\Xshell\6" /f /v Path /d "%~dp0" >NUL 2>NUL
if "%PROCESSOR_ARCHITECTURE%"=="x86" reg add "HKLM\SOFTWARE\NetSarang\Xshell\6" /f /v Version /d "6.0.0189" >NUL 2>NUL
if "%PROCESSOR_ARCHITECTURE%"=="x86" reg add "HKLM\SOFTWARE\NetSarang\Xshell\6" /f /v MagicCode /t REG_BINARY /d "56754d0c95cb370583daaa4abc0aea90e40702001900" >NUL 2>NUL
If "%PROCESSOR_ARCHITECTURE%"=="AMD64" reg add "HKLM\SOFTWARE\Wow6432Node\NetSarang\Xshell\6" /f /v Path /d "%~dp0" >NUL 2>NUL
If "%PROCESSOR_ARCHITECTURE%"=="AMD64" reg add "HKLM\SOFTWARE\Wow6432Node\NetSarang\Xshell\6" /f /v Version /d "6.0.0189" >NUL 2>NUL
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" reg add "HKLM\SOFTWARE\Wow6432Node\NetSarang\Xshell\6" /f /v MagicCode /t REG_BINARY /d "56754d0c95cb370583daaa4abc0aea90e40702001900" >NUL 2>NUL

ECHO.&ECHO 完成！创建桌面快捷方式？
ECHO.&ECHO 是敲任意键，否直接关闭！&PAUSE >NUL 2>NUL & CLS

mshta VBScript:Execute("Set a=CreateObject(""WScript.Shell""):Set b=a.CreateShortcut(a.SpecialFolders(""Desktop"") & ""\Xshell.lnk""):b.TargetPath=""%~dp0Xshell.exe"":b.WorkingDirectory=""%~dp0"":b.Save:close")
mshta VBScript:Execute("Set a=CreateObject(""WScript.Shell""):Set b=a.CreateShortcut(a.SpecialFolders(""Desktop"") & ""\Xftp.lnk""):b.TargetPath=""%~dp0Xftp.exe"":b.WorkingDirectory=""%~dp0"":b.Save:close")

ECHO.&ECHO 完成！&PAUSE >NUL 2>NUL & EXIT