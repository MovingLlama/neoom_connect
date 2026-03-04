# neoom Connect für Home Assistant

<img src="https://neoom.com/hubfs/01_neoom%20Website%20neu/Icons/Icon_Systemicons/neoom_round_c.svg" width="60" height="60" align="center" alt="neoom Logo">

**neoom Connect** ist eine inoffizielle "Custom Integration" für [Home Assistant](https://www.home-assistant.io/), die eine hybride Verbindung zu Ihren neoom-Systemen (wie Kjuube, Beaam, etc.) herstellt. 

Sie verbindet das Beste aus zwei Welten:
1. **Ntuity Cloud:** Für Tarifdaten, Wettervorhersagen und statistische Werte.
2. **Lokales BEAAM Gateway:** Für Echtzeit-Daten (im Sekundentakt) ohne spürbare Cloud-Verzögerung.

---

## 🚀 Funktionen

* **Echtzeit-Überwachung:** Liest Leistungs-, Energie- und Spannungsdaten blitzschnell direkt vom lokalen BEAAM Gateway im Netzwerk.
* **Dynamische Hardware-Erkennung:** Findet automatisch Wechselrichter, Batterien (z. B. Kjuube), Ladestationen und Zähler, ohne dass Sie diese manuell konfigurieren müssen.
* **Steuerung (Beta):** Unterstützung zum Setzen von Ladeleistungsgrenzen oder Betriebsmodi (z. B. 1-Phasig/3-Phasig Laden) direkt über Home Assistant-Entitäten (Slider und Dropdowns).
* **Tarif-Informationen:** Integriert aktuelle Strompreise und Einspeisevergütungen aus der Ntuity Cloud.
* **Voll integriert:** Alle Sensoren sind mit den korrekten Home Assistant "Device Classes" und "State Classes" vorkonfiguriert, sodass sie nahtlos im nativen Energie-Dashboard (Energy Dashboard) verwendet werden können.

## 📋 Voraussetzungen

Bevor Sie mit der Installation starten, benötigen Sie folgende vier Informationen aus Ihrem neoom/Ntuity-Konto bzw. von Ihrer Hardware:

1. **Ntuity Bearer Token:** Ihr API-Zugriffsschlüssel für die Ntuity Cloud.
2. **Site ID:** Die eindeutige UUID Ihres Standorts (z. B. `b60bf800-...`).
3. **BEAAM IP-Adresse:** Die lokale IP-Adresse Ihres BEAAM Gateways in Ihrem Heimnetzwerk (z. B. `192.168.1.50`).
4. **BEAAM API Key:** Das lokale Passwort bzw. der Local-API-Key für den Zugriff auf das Gateway.

## 🛠 Installation

Die einfachste Methode zur Installation ist über [HACS](https://hacs.xyz/) (Home Assistant Community Store).

1. Öffnen Sie **HACS** in Ihrem Home Assistant.
2. Gehen Sie zum Reiter **Integrations**.
3. Klicke oben rechts auf die drei Punkte `...` und wählen Sie **Custom repositories** (Benutzerdefinierte Repositories).
4. Fügen Sie die URL dieses Repositories hinzu: `https://github.com/MovingLlama/neoom_connect`
5. Wählen Sie als Kategorie **Integration**.
6. Klicken Sie auf "Hinzufügen" und anschließend in der Liste auf "Herunterladen" bzw. "Installieren".
7. ⚠️ **WICHTIG:** Starten Sie Home Assistant komplett neu (`Einstellungen` -> `System` -> `Neu starten`), damit Home Assistant den neuen Code laden kann.

## ⚙️ Konfiguration

1. Gehen Sie nach dem Neustart in Home Assistant zu **Einstellungen -> Geräte & Dienste**.
2. Klicken Sie unten rechts auf **Integration hinzufügen**.
3. Suchen Sie in der Liste nach **neoom Connect**.
4. Geben Sie die erforderlichen Daten (Token, Site ID, IP und Key) in das Formular ein und speichern Sie.

Nach erfolgreicher Einrichtung tauchen Ihre Geräte und Entitäten automatisch auf.

## 📊 Unterstützte Hardware & Sensoren (Auszug)

Die Integration erstellt automatisch Geräte (Devices) basierend auf der an Ihr BEAAM Gateway angebundenen Hardware:

| Gerät / Schnittstelle | Verfügbare Sensoren & Steuerungen |
| :--- | :--- |
| **Ntuity Cloud** | Strompreis (EUR/kWh), Einspeisetarif (ct/kWh) |
| **BEAAM Gateway (Lokal)** | Gesamt-Netzbezug, Gesamte Einspeisung, Netzfrequenz, Spannungen (L1/L2/L3) |
| **Wechselrichter (Inverter)** | Aktuelle Leistung (W), Produzierte Energie (kWh), Phasen-Ströme (A) |
| **Batteriespeicher (Kjuube)**| Ladezustand / SoC (%), Lade-/Entladeleistung (W), Temperatur, State of Health |
| **E-Ladestation** | Status (Verbunden/Lädt), Ladeleistung, Modi (1P/3P Umschaltung über Select-Entität) |

> **Hinweis zur Skalierung:**
> Home Assistant zeigt Ihnen standardmäßig die nativen Einheiten an (z. B. Watt oder Wattstunden). Sie können die Anzeigeeinheit direkt in der Benutzeroberfläche von Home Assistant umstellen (z. B. auf Kilowatt `kW`), indem Sie auf das Zahnrad-Symbol der jeweiligen Entität klicken.

## 🐛 Fehlerbehebung (Troubleshooting)

**Fehler: "Invalid handler specified" beim Hinzufügen**
Dies passiert, wenn Home Assistant die neuen Integrationsdateien noch nicht in den Cache geladen hat.
* Lösung: Starten Sie Home Assistant neu (ggf. auch den Browser-Cache leeren).

**Keine lokalen Echtzeit-Daten kommen an (oder Entitäten sind nicht verfügbar)**
Die Verbindung zur Ntuity Cloud funktioniert meist auf Anhieb, lokale API-Probleme treten jedoch auf, wenn:
1. Die IP-Adresse des BEAAM Gateways falsch ist oder sich geändert hat (Tipp: Weisen Sie dem Gateway im Router eine statische IP zu).
2. Der verwendete BEAAM API Key inkorrekt ist.
3. Die Hardware temporär überlastet ist.

**Erweitertes Logging aktivieren**
Um herauszufinden, warum die Integration nicht funktioniert, fügen Sie folgenden Block in Ihre `configuration.yaml` ein und starten Sie Home Assistant neu:

```yaml
logger:
  default: info
  logs:
    custom_components.neoom_connect: debug
```
Suchen Sie anschließend unter *Einstellungen -> System -> Protokolle* nach Einträgen mit dem Präfix `neoom_connect`.

---

**Disclaimer:** 
*Dies ist ein Open-Source-Community-Projekt und **keine** offizielle Software der neoom ag. Nutzung auf eigene Gefahr.*
