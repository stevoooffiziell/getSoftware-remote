import re

import winrm
from cryptography.fernet import Fernet

import DatabaseManager
import json
import base64
import configparser



class SoftwareInventoryWinRM:
    def __init__(self, host, config_file="config\\config.ini", transport='ntlm'):

        config = configparser.ConfigParser()
        config.read(config_file)

        encrypted_pwd_ps = config.get('ps-auth', 'pwd_ps')
        self.user = config.get('ps-auth', 'user_ps')
        self.pwd = DatabaseManager.decrypt_password(encrypted_pwd_ps)
        self.host = host

        self.session = winrm.Session(
            target=self.host,
            auth=(self.user, self.pwd),
            transport=transport
        )

    def get_installed_software(self, output_file: str):
        # Due to incompatibility for win server 2008 in the powershell_script its necessary to check the OS-version.
        os_check_script = "(Get-WmiObject Win32_OperatingSystem).Caption"
        os_result = self.session.run_ps(os_check_script)
        os_name = os_result.std_out.decode('utf-8', errors='ignore').strip()

        if "2008" in os_name:
            print(f"[INFO] {self.host} ist ein Windows Server 2008 System.\n"
                  f"[INFO] Nutze Text-Ausgabe Methode.")
            powershell_script = r"""$lines = @()
            $software = Get-ItemProperty HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\* |
                Select-Object DisplayName, DisplayVersion, Publisher, InstallDate, EstimatedSize
            $software += Get-ItemProperty HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\* |
                Select-Object DisplayName, DisplayVersion, Publisher, InstallDate, EstimatedSize
            $software = $software | Where-Object { $_.DisplayName -ne $null } | Sort-Object DisplayName
            foreach ($item in $software) {
                $lines += "Name       : $($item.DisplayName)"
                $lines += "Version    : $($item.DisplayVersion)"
                $lines += "Publisher  : $($item.Publisher)"
                $lines += "Installiert: $($item.InstallDate)"
                $lines += "Größe      : $($item.EstimatedSize) KB"
                $lines += "-------------------------------"
            }
            $fullText = $lines -join "`r`n"
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($fullText)
            [Convert]::ToBase64String($bytes)
            """

            result = self.session.run_ps(powershell_script)
            if result.status_code != 0:
                raise RuntimeError(f"Fehler beim Ausführen des Skripts: {result.std_err.decode(errors='ignore')}")
            try:
                base64_output = result.std_out.decode('utf-8').strip()
                decoded_json = base64.b64decode(base64_output).decode('utf-8', errors='ignore')
                if not decoded_json.strip():
                    raise ValueError("Base64-Dekodierung war leer oder ungültig.")
                software_list = self.parse_txt_to_json(decoded_json)
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(software_list, f, indent=2, ensure_ascii=False)

                if isinstance(software_list, dict):
                    software_list = [software_list]
                for entry in software_list:
                    entry["Hostname"] = self.host
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(software_list, f, indent=2, ensure_ascii=False)
                print(f"Softwaredaten mit Hostname in '{output_file}' gespeichert.")
            except Exception as e:
                raise ValueError(f"Fehler beim Verarbeiten oder Speichern: {e}")

        else:
            print(f"[INFO] {self.host} verwendet modernes Windows. Verwende direkte JSON-Ausgabe.")
            powershell_script = r"""
            $software = Get-ItemProperty HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\* |
            Select-Object DisplayName, DisplayVersion, Publisher, InstallDate

            $software += Get-ItemProperty HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\* |
            Select-Object DisplayName, DisplayVersion, Publisher, InstallDate, EstimatedSize

            $software = $software | Where-Object { $_.DisplayName -ne $null} | 
                ForEach-Object {
                    [PSCustomObject]@{
                        Name = if ($_.DisplayName) {$_.DisplayName} else { $null }
                        Publisher   = if ($_.Publisher) { $_.Publisher } else { $null }
                        InstallDate = if ($_.InstallDate) { $_.InstallDate } else { $null }
                        Size        = if ($_.EstimatedSize) { $_.EstimatedSize } else { 0 }
                        Version     = if ($_.DisplayVersion) {$_.DisplayVersion} else { $null }}
                    } |
                Sort-Object DisplayName

            $json = $software | ConvertTo-Json -Depth 3
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
            [Convert]::ToBase64String($bytes)
            """

            result = self.session.run_ps(powershell_script)
            if result.status_code != 0:
                raise RuntimeError(f"Fehler beim Ausführen des Skripts: {result.std_err.decode(errors='ignore')}")

            try:
                base64_output = result.std_out.decode('utf-8').strip()
                decoded_json = base64.b64decode(base64_output).decode('utf-8', errors='ignore')
                if not decoded_json.strip():
                    raise ValueError("Base64-Dekodierung war leer oder ungültig.")
                software_list = json.loads(decoded_json)
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(software_list, f, indent=2, ensure_ascii=False)
                if isinstance(software_list, dict):
                    software_list = [software_list]
                for entry in software_list:
                    entry["Hostname"] = self.host
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(software_list, f, indent=2, ensure_ascii=False)
                print(f"Softwaredaten mit Hostname in '{output_file}' gespeichert.")
            except Exception as e:
                raise ValueError(f"Fehler beim Verarbeiten oder Speichern: {e}")

    def parse_txt_to_json(self, raw_text: str):
        software_list = []
        current = {}
        for line in raw_text.splitlines():
            line = line.strip()
            if line.startswith("Name"):
                current["Name"] = line.split(":", 1)[1].strip()
            elif line.startswith("Version"):
                current["Version"] = line.split(":", 1)[1].strip()
            elif line.startswith("Publisher"):
                current["Publisher"] = line.split(":", 1)[1].strip()
            elif line.startswith("Installiert"):
                current["InstallDate"] = line.split(":", 1)[1].strip()
            elif line.startswith("Größe"):
                size_part = re.search(r"(\d+)", line)
                current["Size"] = int(size_part.group(1)) if size_part else 0
            elif line.startswith("---"):
                if current:
                    software_list.append(current)
                    current = {}
        if current:
            software_list.append(current)
        return software_list
