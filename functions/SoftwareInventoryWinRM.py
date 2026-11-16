import base64
import configparser
import json
import os
import re
import warnings
from functools import lru_cache
from json import JSONDecodeError

import winrm

import functions.DatabaseManager as dm

JSON_DIR = os.path.join(dm.PROJECT_ROOT, "json")


@lru_cache(maxsize=None)
def _load_ps_credentials(config_file):
    """Liest und entschlüsselt die WinRM-Zugangsdaten nur einmal statt pro Host."""
    config = configparser.ConfigParser()
    config.read(config_file)
    user = config.get('ps-auth', 'user_ps')
    pwd = dm.decrypt_password(config.get('ps-auth', 'pwd_ps'))
    return user, pwd


def parse_txt_to_json(raw_text: str):
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


class SoftwareInventoryWinRM:
    def __init__(self, host, config_file=None, transport='ntlm'):
        self.config_file = os.path.normpath(config_file or dm.DEFAULT_CONFIG_FILE)
        self.log = dm.DatabaseManager()

        # No more static strings up here
        self.info = self.log.info
        self.debug = self.log.debug
        self.warning = self.log.warning
        self.error = self.log.error

        # import dynamic time updates from DatabaseManager
        self.get_logprint_info = self.log.get_logprint_info
        self.get_logprint_debug = self.log.get_logprint_debug
        self.get_logprint_warning = self.log.get_logprint_warning
        self.get_logprint_error = self.log.get_logprint_error

        self.output_file = None

        pwsh_script = r"""
                    $software = Get-ItemProperty HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\* |
                    Select-Object DisplayName, DisplayVersion, Publisher, InstallDate, EstimatedSize

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
        pwsh_script_2008 = r"""$lines = @()
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

        self.pwsh_script = pwsh_script
        self.pwsh_script_2008 = pwsh_script_2008

        self.user, self.pwd = _load_ps_credentials(self.config_file)
        self.host = host

        try:
            self.session = winrm.Session(
                target=self.host,
                auth=(self.user, self.pwd),
                transport=transport,
                read_timeout_sec=15,  # Timeout hinzufügen
                operation_timeout_sec=10
            )
        except Exception as e:
            self.log.logger.error(f"WinRM connection error to {host}: {str(e)}")
            raise ConnectionError(f"WinRM connection failed: {str(e)}")

    def get_installed_software(self, output_file: str = None):
        """
        Liest die installierte Software des Hosts aus.

        :param output_file: Zielpfad der JSON-Kopie, Standard ``json/<host>_output.json``
        :return: Liste der Software-Einträge
        """
        if not output_file:
            output_file = os.path.join(JSON_DIR, f"{self.host}_output.json")

        # Due to incompatibility for win server 2008 in the powershell_script its necessary to check the OS-version.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            os_result = self.session.run_ps("(Get-WmiObject Win32_OperatingSystem).Caption")
        os_name = os_result.std_out.decode('utf-8', errors='ignore').strip()

        if "2008" in os_name:
            print(f"{self.get_logprint_info()} {self.host} is a windows server 2008 system.\n"
                  f"{self.get_logprint_info()} Nutze Text-Ausgabe Methode.")
            script = self.pwsh_script_2008
        else:
            print(f"{self.get_logprint_info()} {self.host} is using modern windows OS. Using direct JSON-output")
            script = self.pwsh_script

        try:
            return self.warn_catch(script, output_file=output_file)
        except Exception as e:
            raise ValueError(f"Processing or saving error: {e}") from e

    def warn_catch(self, script, output_file: str):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = self.session.run_ps(script)

        if result.status_code != 0:
            raise RuntimeError(
                f"Fehler beim Ausführen des Skripts: {result.std_err.decode(errors='ignore')}")
        base64_output = result.std_out.decode('utf-8').strip()
        decoded_json = base64.b64decode(base64_output).decode('utf-8', errors='ignore')
        if not decoded_json.strip():
            print(f"{self.get_logprint_debug()} Leere JSON-Ausgabe von Host {self.host}")
            print(f"{self.get_logprint_debug()} PowerShell-Ausgabe: {base64_output}")
            raise ValueError("Base64-Dekodierung war leer oder ungültig.")

        try:
            software_list = json.loads(decoded_json)
        except JSONDecodeError as e:
            print(f"{self.get_logprint_warning()} JSON-Parsingerror: {e}")
            print(f"{self.get_logprint_debug()} Initial output:\n{decoded_json[:500]}...")
            # Fallback zu Text-Parser
            software_list = parse_txt_to_json(decoded_json)

        # Write hostname into software_list
        if isinstance(software_list, dict):
            software_list = [software_list]
        for entry in software_list:
            entry["Hostname"] = self.host

        # JSON-Kopie zur Nachvollziehbarkeit; die Daten selbst werden direkt zurückgegeben
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(software_list, f, indent=2, ensure_ascii=False)
        print(f"{self.get_logprint_info()} Software with hostname has been saved to '{output_file}'")
        return software_list
