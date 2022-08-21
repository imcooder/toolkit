#------------------------------- Import Modules BEGIN -------------------------------
# 引入 posh-git
Import-Module posh-git

# 引入 oh-my-posh
Import-Module oh-my-posh

# 引入 ps-read-line
Import-Module PSReadLine

Import-Module Get-ChildItemColor

# 设置 PowerShell 主题
Set-PoshPrompt aliens
#------------------------------- Import Modules END   -------------------------------

set-location c:
# Useful shortcuts for traversing directories
function cd...  { cd ..\.. }
function cd.... { cd ..\..\.. }

# Compute file hashes - useful for checking successful downloads 
function md5    { Get-FileHash -Algorithm MD5 $args }
function sha1   { Get-FileHash -Algorithm SHA1 $args }
function sha256 { Get-FileHash -Algorithm SHA256 $args }

# Quick shortcut to start notepad
function n      { notepad $args }

# ssh-baidu



# git
function gup	{ git pull }
function greset  { git reset --hard origin/master }
function gpush   { git push origin "HEAD:refs/for/master" }
function gs      { git status }
function gb      { git branch }


# Ensure that Get-ChildItemColor is loaded
# Set l and ls alias to use the new Get-ChildItemColor cmdlets
Set-Alias l Get-ChildItemColor -Option AllScope
Set-Alias ls Get-ChildItemColorFormatWide -Option AllScope
# ls
function ll	{
	ls $args
}

function touch($name) {
    if ($name) {
        $file_path = Split-Path -Path $name
        $file_name = Split-Path -Path $name -Leaf
        if ($file_path -eq "") {
            $file_path = "."
        }
        if (-Not (Test-Path($file_path))) {
            New-Item -ItemType "directory" -Path $file_path
        }
        New-Item -Path $file_path -Name $file_name -ItemType "file"
    }
    else {
        Write-Host "Command to create new file."
    }
}

function which($name)
{
    Get-Command $name | Select-Object -ExpandProperty Definition
}


#-------------------------------  Set Hot-keys BEGIN  -------------------------------
# 设置预测文本来源为历史记录
Set-PSReadLineOption -PredictionSource History

# 每次回溯输入历史，光标定位于输入内容末尾
Set-PSReadLineOption -HistorySearchCursorMovesToEnd

# 设置 Tab 为菜单补全和 Intellisense
Set-PSReadLineKeyHandler -Key "Tab" -Function MenuComplete

# 设置 Ctrl+d 为退出 PowerShell
Set-PSReadlineKeyHandler -Key "Ctrl+d" -Function ViExit

# 设置 Ctrl+z 为撤销
Set-PSReadLineKeyHandler -Key "Ctrl+z" -Function Undo

# 设置向上键为后向搜索历史记录
Set-PSReadLineKeyHandler -Key UpArrow -Function HistorySearchBackward

# 设置向下键为前向搜索历史纪录
Set-PSReadLineKeyHandler -Key DownArrow -Function HistorySearchForward
#-------------------------------  Set Hot-keys END    -------------------------------





#-------------------------------    Functions BEGIN   -------------------------------
# Python 直接执行
$env:PATHEXT += ";.py"

# 更新系统组件
function Update-Packages {
	# update pip
	Write-Host "Step 1: 更新 pip" -ForegroundColor Magenta -BackgroundColor Cyan
	$a = pip list --outdated
	$num_package = $a.Length - 2
	for ($i = 0; $i -lt $num_package; $i++) {
		$tmp = ($a[2 + $i].Split(" "))[0]
		pip install -U $tmp
	}

	# update TeX Live
	$CurrentYear = Get-Date -Format yyyy
	Write-Host "Step 2: 更新 TeX Live" $CurrentYear -ForegroundColor Magenta -BackgroundColor Cyan
	tlmgr update --self
	tlmgr update --all

	# update Chocolotey
	Write-Host "Step 3: 更新 Chocolatey" -ForegroundColor Magenta -BackgroundColor Cyan
	choco outdated
}
#-------------------------------    Functions END     -------------------------------





#-------------------------------   Set Alias BEGIN    -------------------------------
# 1. 编译函数 make
function MakeThings {
	nmake.exe $args -nologo
}
Set-Alias -Name make -Value MakeThings

# 2. 更新系统 os-update
Set-Alias -Name os-update -Value Update-Packages

# 3. 查看目录 ls & ll
function ListDirectory {
	(Get-ChildItem).Name
	Write-Host("")
}
# Set-Alias -Name ls -Value ListDirectory
# Set-Alias -Name ll -Value Get-ChildItem

# 4. 打开当前工作目录
function OpenCurrentFolder {
	param
	(
		# 输入要打开的路径
		# 用法示例：open C:\
		# 默认路径：当前工作文件夹
		$Path = '.'
	)
	Invoke-Item $Path
}
Set-Alias -Name open -Value OpenCurrentFolder
#-------------------------------    Set Alias END     -------------------------------





#-------------------------------   Set Network BEGIN    -------------------------------
# 1. 获取所有 Network Interface
function Get-AllNic {
	Get-NetAdapter | Sort-Object -Property MacAddress
}
Set-Alias -Name getnic -Value Get-AllNic

# 2. 获取 IPv4 关键路由
function Get-IPv4Routes {
	Get-NetRoute -AddressFamily IPv4 | Where-Object -FilterScript {$_.NextHop -ne '0.0.0.0'}
}
Set-Alias -Name getip -Value Get-IPv4Routes

# 3. 获取 IPv6 关键路由
function Get-IPv6Routes {
	Get-NetRoute -AddressFamily IPv6 | Where-Object -FilterScript {$_.NextHop -ne '::'}
}
Set-Alias -Name getip6 -Value Get-IPv6Routes
function Get-MyIp {
	curl -L tool.lu/ip
}
Set-Alias -Name getmyip -Value Get-MyIp
#-------------------------------    Set Network END     ----------------------------
# Import the Chocolatey Profile that contains the necessary code to enable
# tab-completions to function for `choco`.
# Be aware that if you are missing these lines from your profile, tab completion
# for `choco` will not function.
# See https://ch0.co/tab-completion for details.
$ChocolateyProfile = "$env:ChocolateyInstall\helpers\chocolateyProfile.psm1"
if (Test-Path($ChocolateyProfile)) {
  Import-Module "$ChocolateyProfile"
}
