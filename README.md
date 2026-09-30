# Pool Manager für Home Assistant

[![Validate](https://github.com/ludgerbeckmann/ha_pool_manager/actions/workflows/validate.yml/badge.svg)](https://github.com/ludgerbeckmann/ha_pool_manager/actions/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/ludgerbeckmann/ha_pool_manager.svg)](https://github.com/ludgerbeckmann/ha_pool_manager/releases/)
[![GitHub license](https://img.shields.io/github/license/ludgerbeckmann/ha_pool_manager.svg)](https://github.com/ludgerbeckmann/ha_pool_manager/blob/main/LICENSE)

Eine Custom Integration, die verschiedene Funktionen zur Nutzung eines Pools
bereitstellt. Die Integration ist modular aufgebaut und wird nach Bedarf
erweitert. Aktuell enthalten:

- **Pumpe nach Zeitplan** – die Poolpumpe wird regelmäßig zu festen
  Zeitfenstern ein- und ausgeschaltet.

## Installation

### Über HACS (empfohlen)

1. HACS → Menü (⋮) → *Benutzerdefinierte Repositories*
2. `https://github.com/ludgerbeckmann/ha_pool_manager` eintragen, Kategorie
   **Integration** wählen
3. "Pool Manager" installieren und Home Assistant neu starten

### Manuell

Ordner `custom_components/ha_pool_manager` nach
`<config>/custom_components/ha_pool_manager` kopieren und Home Assistant neu
starten.

## Einrichtung

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Pool Manager**
2. Namen des Pools vergeben und den **Schalter der Pumpe** wählen
   (`switch` oder `input_boolean`). Pro Pumpe ist ein Pool möglich; mehrere
   Pools (mehrere Pumpen) sind erlaubt.
3. Über **Konfigurieren** am Pool die Zeitfenster pflegen:
   - **Zeitfenster hinzufügen**: Beginn, Ende und Wochentage. Liegt das Ende
     vor dem Beginn, läuft das Fenster über Mitternacht (die Wochentage
     beziehen sich dann auf den Tag des Beginns). Bis zu 8 Fenster.
   - **Zeitfenster entfernen**
   - **Pumpe ändern**

## Entitäten (pro Pool)

| Entität | Beschreibung |
|---|---|
| Schalter **Zeitplan aktiv** | Automatik an/aus. Der Zustand bleibt nach einem Neustart erhalten. Beim Ausschalten wird die Pumpe nicht angefasst. |
| Binärsensor **Pumpe soll laufen** | `on`, solange die Pumpe laut Zeitplan (oder manuellem Lauf) laufen soll. |
| Sensor **Nächster Start** | Zeitstempel des nächsten geplanten Fensterbeginns. |
| Sensor **Laufzeit heute** | Bisherige Laufzeit der Pumpe am heutigen Tag in Minuten (bleibt über Neustarts erhalten). |

## Verhalten im Detail

- Die Pumpe wird zu **Fensterbeginn eingeschaltet** und zu **Fensterende
  ausgeschaltet**. Geprüft wird jede Minute.
- **Nur bei einem Wechsel** wird geschaltet: Schaltest du die Pumpe von Hand
  während eines Fensters aus (oder außerhalb an), bleibt das bis zum nächsten
  Fensterwechsel bestehen.
- Nach einem **Neustart** von Home Assistant bzw. beim Aktivieren der
  Automatik wird die Pumpe einmalig an den Soll-Zustand angeglichen.
- Ist die Pumpe gerade `unavailable`/`unknown` (typisch beim Hochfahren),
  wird der Schaltvorgang **vorgemerkt** und nachgeholt, sobald sie wieder
  erreichbar ist.

## Aktionen

### `ha_pool_manager.run_pump`

Lässt die Pumpe unabhängig vom Zeitplan für eine bestimmte Zeit laufen (auch
bei ausgeschaltetem Zeitplan). Danach gilt wieder der Zeitplan.

```yaml
action: ha_pool_manager.run_pump
data:
  duration: 30        # Minuten (1–1440)
  # entry_id: ...     # optional; ohne Angabe sind alle Pools betroffen
```

## Diagnose

Am Pool unter **⋮ → Diagnose herunterladen** werden Konfiguration und
Live-Zustand (Zeitplan, nächster Start, Pumpenzustand) ausgegeben.

## Geplante Erweiterungen

Weitere Funktionen kommen bei Bedarf hinzu.

## Entwicklung

Tests (echtes Home Assistant über `pytest-homeassistant-custom-component`):

```bash
pip install pytest-homeassistant-custom-component
pytest
```
