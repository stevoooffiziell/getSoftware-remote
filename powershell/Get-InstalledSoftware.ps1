Get-ItemProperty HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\* |
Select-Object DisplayName, Publisher, InstallDate, EstimatedSize, DisplayVersion |
Where-Object { $_.DisplayName -ne $null } |
ForEach-Object {
    [PSCustomObject]@{
        Name = $_.DisplayName
        Publisher = $_.Publisher
        InstallDate = if ($_.InstallDate) { $_.InstallDate } else { $null }
        Size = if ($_.EstimatedSize) { $_.EstimatedSize } else { $null }
        Version = $_.DisplayVersion
    }
} | ConvertTo-Json -Depth 2