<img src="https://neoom.com/hubfs/01_neoom%20Website%20neu/Icons/Icon_Systemicons/neoom_round_c.svg" width="60" height="60" align="center" alt="neoom Logo"> neoom Connect

Eine Hybrid-Integration für neoom Systeme (Kjuube, Beaam, etc.), die das Beste aus zwei Welten verbindet:

Ntuity Cloud: Für Tarifdaten, Wettervorhersagen und statistische Werte.

Lokales BEAAM Gateway: Für Echtzeit-Daten (Sekundentakt) ohne Cloud-Verzögerung.

<img src="https://neoom.com/hubfs/01_neoom%20Website%20neu/Icons/Icon_Systemicons/neoom_round_c.svg" width="100" align="right">

Funktionen

🚀 Echtzeit-Überwachung: Liest Daten direkt vom lokalen BEAAM Gateway.

🔋 Dynamische Erkennung: Findet automatisch Wechselrichter, Batterien (Kjuube), Ladestationen und Zähler.

💰 Tarif-Informationen: Integriert Strompreise und Einspeisevergütungen aus der Ntuity Cloud.

⚡ Energiefluss: Berechnet Produktion, Verbrauch, Netzbezug und Speicherladung.

Voraussetzungen

Bevor du startest, benötigst du folgende Informationen:

Ntuity Bearer Token: Deinen API Zugriffsschlüssel für die Cloud.

Site ID: Die ID deines Standorts (z.B. b60bf800-...).

BEAAM IP-Adresse: Die lokale IP deines Gateways (z.B. 192.168.1.xxx).

BEAAM API Key: Das Passwort oder der Key für den lokalen Zugriff.

Installation via HACS

Öffne HACS in deinem Home Assistant.

Gehe zu "Integrations".

Klicke oben rechts auf die drei Punkte ... und wähle Custom repositories.

Füge die URL dieses Repositories hinzu: https://github.com/MovingLlama/neoom_connect

Wähle als Kategorie Integration.

Klicke auf "Hinzufügen" und installiere die Integration.

WICHTIG: Starte Home Assistant komplett neu (Einstellungen -> System -> Neu starten).

Konfiguration

Gehe zu Einstellungen -> Geräte & Dienste.

Klicke auf Integration hinzufügen.

Suche nach neoom Connect.

Gib die erforderlichen Daten (Token, IDs, IP) in das Formular ein.

Unterstützte Sensoren (Auszug)

Die Integration erstellt automatisch Geräte basierend auf deiner Hardware:

Gerät

Sensoren

Ntuity Cloud

Strompreis, Einspeisetarif

BEAAM Gateway

Netzbezug, Einspeisung, Netzfrequenz, Spannungen (L1/L2/L3)

PV Anlage

Aktuelle Leistung (W), Produzierte Energie (kWh), Ströme

Batterie (Kjuube)

SoC (%), Lade-/Entladeleistung, Temperatur, State of Health

Ladestation

Status (Verbunden/Lädt), Aktuelle Leistung, Geladene Energie

Fehlerbehebung

Fehler: "Invalid handler specified"

Dies passiert, wenn Home Assistant die Integrationsdateien noch nicht vollständig geladen hat.

Prüfe, ob der Ordner unter /config/custom_components/ exakt neoom_connect heißt.

Starte Home Assistant neu.

Keine Daten

Sollten keine Daten ankommen:

Prüfe, ob das BEAAM Gateway unter der angegebenen IP erreichbar ist.

Stelle sicher, dass der Ntuity Token noch gültig ist.

Aktiviere das Logging in der configuration.yaml für mehr Details:

logger:
  default: info
  logs:
    custom_components.neoom_connect: debug


Disclaimer: Dies ist keine offizielle Integration von neoom.