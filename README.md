# mRemoteNG-Windows-Tests

Automatisierte Abnahme der mRemoteNG-Sicherheitsbranches in einem eigenen
Windows-Labor. Produktänderungen und ihre NUnit-Regressionstests bleiben im
[mRemoteNG-Fork](https://github.com/ckbaker10/mRemoteNG).

Der Windows-Build und die GPO-/Anwendungskontrollabnahme sind noch offen.
Hosttests und Syntaxprüfungen sind kein Nachweis der Windows-Durchsetzung.

## Einrichtung auf dem Linux-Host

Voraussetzungen: KVM-Zugriff ohne root, QEMU, swtpm, OVMF mit Microsoft-Schlüsseln,
xorriso und ausreichend RAM/Plattenplatz. Die Startkonfiguration verwendet die
Ubuntu-OVMF-Pfade in `lab/manage.py`.

```bash
uv venv .venv
uv pip sync --python .venv/bin/python requirements.txt --require-hashes
python3 -m unittest discover -s tests -v
```

VM-Zustände, Medien, Setupantworten, temporäre Laborpasswörter und Rohbelege
gehören ausschließlich in das ignorierte `work/`. Die Programme geben keine
Laborpasswörter aus. Zugangsdaten in `credentials.json` sind nur für die eigenen
wegwerfbaren Gäste bestimmt. Setup-ISOs enthalten diese temporären Zugangsdaten.

Standardzustand: `work/windows-lab`. Ein vorhandenes Labor kann ausdrücklich
übernommen werden, ohne Platten zu verschieben:

```bash
export MRNG_LAB_ROOT=/opt/paseo-development/mRemoteNG/work/windows-lab
```

Offizielle Evaluierungsmedien unter `$MRNG_LAB_ROOT/media/windows11.iso` und
`server2025.iso` bereitstellen. Quellen:
[Windows 11](https://www.microsoft.com/en-us/evalcenter/evaluate-windows-11-enterprise),
[Windows Server 2025](https://www.microsoft.com/en-us/evalcenter/evaluate-windows-server-2025).
Download-URL, Datum, ISO-Hash und Werkzeugversionen im lokalen Nachweis erfassen.
Medien und Gastsysteme werden nicht mit diesem Repository verteilt.

```bash
.venv/bin/python lab/manage.py start server
.venv/bin/python lab/manage.py start client
.venv/bin/python lab/manage.py boot server
.venv/bin/python lab/manage.py boot client
```

`boot` setzt die jeweilige VM zurück und quittiert einmalig den CD-Boot-Prompt.
Nur beim ersten Start verwenden. Bei längeren Arbeiten die eigenen Prozesse
über User-Systemd-Units mit PIDFile ausführen; bestehende fremde Prozesse und
belegte Ports nicht übernehmen. Die Verwaltung bindet ausschließlich an
Loopback (Client 55985, Server 55986); die getrennte Gastverbindung nutzt 55990.
VNC und QMP verwenden Unix-Sockets im geschützten Zustandsverzeichnis.

## Gastverwaltung und Build

Nach abgeschlossener Installation:

```bash
.venv/bin/python lab/remote.py client scripts/Get-LabStatus.ps1
.venv/bin/python lab/remote.py client scripts/Clear-LabSetupSecrets.ps1
.venv/bin/python lab/manage.py eject-seed client
.venv/bin/python lab/manage.py eject-install client
.venv/bin/python lab/remote.py client scripts/Initialize-BuildClient.ps1
```

Für den Server Status und Setupbereinigung ebenfalls ausführen. WinRM benutzt
NTLM mit erzwungener Nachrichtenverschlüsselung; unverschlüsselte Nachrichten
werden im Gast abgelehnt. Die Laboradministration ist kein Produktionsprofil.

`Initialize-BuildClient.ps1` prüft die Microsoft-Authenticode-Signatur des
Installers und installiert Visual Studio 2026 Build Tools mit Desktop-Workload
und Windows SDK 26100. Nach einem erforderlichen Neustart den Status erneut
prüfen. Die installierte .NET-10-SDK-Version vor dem Build erfassen.

Einen sauberen, expliziten Quellcommit mit `git archive --format=zip` übertragen.
`scripts/Invoke-SourceTests.ps1` verlangt Quellcommit und SHA-256 des Archivs,
extrahiert in ein neues Laufverzeichnis, baut mit Windows-MSBuild und erzeugt
TRX, Binlog und `result.json`. Der Commitparameter ist die Host-Provenienz des
Archivs; der Gast kann einen Git-Commit aus einem ZIP allein nicht verifizieren.
Archivhash und `git archive`-Befehl deshalb gemeinsam im Hostnachweis erfassen.

Der Standardfilter deckt Sicherheit, Settings und Credential-Serializer ab.
WinForms-Dialogtests benötigen eine interaktive Windows-Sitzung. Registrytests
verwenden eigene HKCU-Testschlüssel; reale HKLM-/GPO-Abnahme wird gesondert im
Labor ausgeführt. Kein produktives GPO oder App-Control-Profil wird angewendet.

## Nachweise

Rohbelege unter `work/` mit exakten Befehlen, Eingabe-SHA-256, Werkzeugversionen,
Hostzeit und Exitstatus erfassen. Bereinigte Ergebnisberichte dürfen unter
`reports/` versioniert werden. Fehlgeschlagene und übersprungene Prüfungen
ausweisen. Vor erzwungener Anwendungskontrolle einen konsistenten Snapshot und
einen getesteten Wiederherstellungsweg bereitstellen.

Technische Referenzen:
[pywinrm-Nachrichtenverschlüsselung](https://github.com/diyan/pywinrm#encryption),
[Build-Tools-Komponenten](https://learn.microsoft.com/en-us/visualstudio/install/workload-component-id-vs-build-tools?view=vs-2026).
