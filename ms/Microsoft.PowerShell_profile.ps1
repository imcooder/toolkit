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

# ls
function ll		{ ls $args }

# git
function gup	{ git pull }
function greset  { git reset --hard origin/master }
function gpush   { git push origin "HEAD:refs/for/master" }
function gs      { git status }
function gb      { git branch }