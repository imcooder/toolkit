@ECHO OFF&PUSHD %~DP0 &TITLE 卸载 www.Laomo.me
>NUL 2>&1 REG.exe query "HKU\S-1-5-19" || (
    ECHO SET UAC = CreateObject^("Shell.Application"^) > "%TEMP%\Getadmin.vbs"
    ECHO UAC.ShellExecute "%~f0", "%1", "", "runas", 1 >> "%TEMP%\Getadmin.vbs"
    "%TEMP%\Getadmin.vbs"
    DEL /f /q "%TEMP%\Getadmin.vbs" 2>NUL
    Exit /b
)

taskkill /f /im Xftp* >NUL 2>NUL
taskkill /f /im Xshell* >NUL 2>NUL

regsvr32 /s /u NsCopyHook3.dll

rd/s/q "%ProgramData%\NetSarang" 2>NUL
rd/s/q "%AllUsersProfile%\NetSarang\Xshell"2>NUL
reg delete "HKCU\Software\NetSarang\Xftp" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\NetSarang\Xftp" /F>NUL 2>NUL
reg delete "HKCU\Software\NetSarang\Xshell" /F>NUL 2>NUL
reg delete "HKCU\Software\Microsoft\NetLicense" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\NetSarang\Common" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\NetSarang\Xshell" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\Wow6432Node\NetSarang\Xftp" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\Wow6432Node\NetSarang\Xshell" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\Wow6432Node\NetSarang\Common" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\Classes\.xfp" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\Classes\.xsh" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\Classes\.xts" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\Classes\Xftp.xfp" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\Classes\Xshell.xsh" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\Classes\Xtransport.xts" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\Classes\Xshell.Document" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Xftp.exe" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Xshell.exe" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Xagent.exe" /F>NUL 2>NUL
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Xactivator.exe" /F>NUL 2>NUL
assoc .=.file >nul 2>nul & RunDll32.exe USER32.DLL,UpdatePerUserSystemParameters
del/f "%userprofile%\桌面\Xftp.lnk" >NUL  2>NUL 
del/f "%userprofile%\Desktop\Xftp.lnk" >NUL  2>NUL
del/f "%userprofile%\桌面\Xshell.lnk" >NUL  2>NUL 
del/f "%userprofile%\Desktop\Xshell.lnk" >NUL  2>NUL 

ECHO.&ECHO 完成！是否删除默认保存数据？
ECHO.&ECHO 如果自定义的路径请手动删除。
ECHO.&ECHO 是请按任意键，否直接关闭呗！&PAUSE >NUL 2>NUL & CLS

for /f "skip=2 tokens=3 delims= " %%i in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v personal') do (
       for /f "delims=*" %%j in ('echo %%i') do rd/s/q "%%j\NetSarang" 2>NUL)
for /f "skip=2 tokens=3 delims= " %%i in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v personal') do (
       for /f "delims=*" %%j in ('echo %%i') do rd/s/q "%%j\NetSarang Computer" 2>NUL)
ECHO.&ECHO 完成！&PAUSE >NUL 2>NUL & EXIT