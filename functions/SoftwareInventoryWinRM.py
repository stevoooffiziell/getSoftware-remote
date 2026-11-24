# -*- coding: utf-8 -*-
import base64
import configparser
import json
import re
import warnings

import winrm

from functions.DatabaseManager import decrypt_password
from vars.paths import CONFIG_FILE

_UNINSTALL_KEYS = r"""
$software  = Get-ItemProperty HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\* |
    Select-Object DisplayName, DisplayVersion, Publisher, InstallDate, EstimatedSize
$software += Get-ItemProperty HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\* |
    Select-Object DisplayName, DisplayVersion, Publisher, InstallDate, EstimatedSize
$software  = $software | Where-Object { $_.DisplayName -ne $null } | Sort-Object DisplayName
"""

# Moderne Systeme: direkte JSON-Ausgabe
PWSH_SCRIPT = _UNINSTALL_KEYS + r"""
$json = $software | ForEach-Object {
    [PSCustomObject]@{
        Name        = $_.DisplayName
        Publisher   = $_.Publisher
        InstallDate = $_.InstallDate
        Size        = if ($_.EstimatedSize) { $_.EstimatedSize } else { 0 }
        Version     = $_.DisplayVersion
    }
} | ConvertTo-Json -Depth 3
[Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($json))
"""

# Windows Server 2008 (kein ConvertTo-Json): Textausgabe
PWSH_SCRIPT_2008 = _UNINSTALL_KEYS + r"""
$lines = @()
foreach ($item in $software) {
    $lines += "Name       : $($item.DisplayName)"
    $lines += "Version    : $($item.DisplayVersion)"
    $lines += "Publisher  : $($item.Publisher)"
    $lines += "Installiert: $($item.InstallDate)"
    $lines += "Größe      : $($item.EstimatedSize) KB"
    $lines += "-------------------------------"
}
[Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes(($lines -join "`r`n")))
"""

_TEXT_FIELDS = {"Name": "Name", "Version": "Version", "Publisher": "Publisher", "Installiert": "InstallDate"}


def parse_txt_to_json(raw_text: str) -> list:
    """Wandelt die Textausgabe von ``PWSH_SCRIPT_2008`` in eine Liste von Dicts um."""
    software_list = []
    current = {}
    for line in raw_text.splitlines():
        line = line.strip()
        if line.startswith("---"):
            if current:
                software_list.append(current)
                current = {}
            continue
        if ":" not in line:
            continue
        label, value = (part.strip() for part in line.split(":", 1))
        if label in _TEXT_FIELDS:
            current[_TEXT_FIELDS[label]] = value
        elif label == "Größe":
            size = re.search(r"(\d+)", value)
            current["Size"] = int(size.group(1)) if size else 0
    if current:
        software_list.append(current)
    return software_list


class SoftwareInventoryWinRM:
    """Liest die installierte Software eines Remote-Hosts per WinRM aus."""

    def __init__(self, host: str, config_file: str = CONFIG_FILE, transport: str = 'ntlm'):
        config = configparser.ConfigParser()
        config.read(config_file)

        self.host = host
        self.session = winrm.Session(
            target=host,
            auth=(config.get('ps-auth', 'user_ps'), decrypt_password(config.get('ps-auth', 'pwd_ps'))),
            transport=transport,
            read_timeout_sec=15,
            operation_timeout_sec=10,
        )

    def _run_ps(self, script: str):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return self.session.run_ps(script)

    def get_installed_software(self) -> list:
        """Gibt die installierte Software des Hosts als Liste von Dicts zurück."""
        os_result = self._run_ps("(Get-WmiObject Win32_OperatingSystem).Caption")
        os_name = os_result.std_out.decode('utf-8', errors='ignore').strip()
        script = PWSH_SCRIPT_2008 if "2008" in os_name else PWSH_SCRIPT

        result = self._run_ps(script)
        if result.status_code != 0:
            raise RuntimeError(f"Fehler beim Ausführen des Skripts: {result.std_err.decode(errors='ignore')}")

        decoded = base64.b64decode(result.std_out.decode('utf-8').strip()).decode('utf-8', errors='ignore')
        if not decoded.strip():
            raise ValueError(f"Leere Ausgabe von Host {self.host}")

        try:
            software_list = json.loads(decoded)
        except json.JSONDecodeError:
            software_list = parse_txt_to_json(decoded)

        if isinstance(software_list, dict):
            software_list = [software_list]
        return software_list
