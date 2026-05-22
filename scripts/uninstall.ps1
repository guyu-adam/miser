# Miser v1.5 Windows uninstaller
Write-Host "Stopping Miser..."
schtasks /end /tn Miser 2>$null
schtasks /delete /tn Miser /f 2>$null
Write-Host "Miser removed from Task Scheduler."
Write-Host "To remove source files, delete the miser directory."
