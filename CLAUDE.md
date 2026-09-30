# CLAUDE.md – Projektkontext für Claude Code

Vorgehen und Konventionen übernommen von `ludgerbeckmann/ha_smart_ventilation`.
Die README.md ist die Nutzerdokumentation; diese Datei enthält den Kontext
"hinter den Kulissen".

## Projektüberblick

Home-Assistant Custom Integration `ha_pool_manager` (Anzeigename "Pool
Manager"): Sammlung von Funktionen zur Nutzung eines Pools. Ein Config-Entry
entspricht einem Pool (eindeutig über die Pumpen-Entität). Aktueller
Funktionsumfang: Pumpe nach Zeitplan. Weitere Funktionen kommen bei Bedarf
als eigene Module dazu.

Aktuelle Version: siehe `custom_components/ha_pool_manager/manifest.json`.

## Feste Arbeitsanweisungen (immer befolgen, ohne erneute Aufforderung)

- **Vor jeder inhaltlichen Umsetzung zuerst eine kurze Zusammenfassung der
  geplanten Umsetzung im Chat posten und auf Bestätigung warten** (betroffene
  Dateien/Bereiche, neue Optionen/Entitäten/Konstanten, Verhaltensänderung,
  getroffene Annahmen). Kein vollständiger Implementierungsplan nötig.
- **Nach Bestätigung: Branch → Commit → Push → PR → CI-Verifikation → Merge
  (Squash) → Feature-Branch auf neuen `main`-Stand zurücksetzen komplett
  selbstständig**, ohne vor dem Merge erneut nachzufragen.
- **Bei jeder Änderung `version` in `manifest.json` anheben** (Patch:
  Bugfix/Text, Minor: neue Funktion, Major: Breaking Change). Der Workflow
  `auto-release.yml` erstellt daraus Tag + Release (erfordert "Read and write
  permissions" unter Settings → Actions → General).
- Nutzerdokumentation (README) und `strings.json` / `translations/{de,en}.json`
  bei jeder Verhaltensänderung mitpflegen; `strings.json` == `translations/en.json`.

## Dateistruktur

```
custom_components/ha_pool_manager/
├── __init__.py       # Setup/Unload, Dienst run_pump, Update-Listener (Reload)
├── manager.py        # PoolManager: Zeitplan-Auswertung, Schalten, Laufzeit
├── schedule.py       # Reine Zeitplan-Logik ohne HA-Imports (Window, is_active, next_start)
├── config_flow.py    # Config-Flow (Pool anlegen) + Options-Flow (Menü: Pumpe/Fenster)
├── entity.py         # Basisklasse, aktualisiert sich per Dispatcher-Signal
├── switch.py         # Zeitplan aktiv (RestoreEntity)
├── binary_sensor.py  # Pumpe soll laufen
├── sensor.py         # Nächster Start, Laufzeit heute
├── diagnostics.py
├── services.yaml, strings.json, translations/{de,en}.json
tests/                # pytest-homeassistant-custom-component
.github/              # validate (Hassfest+HACS), auto-release, release.yml
```

## Architektur / Lektionen

**1. Schalten nur bei Wechsel des Soll-Zustands.** `PoolManager._async_evaluate`
vergleicht den Soll-Zustand mit `_last_desired` und schaltet nur bei einem
Wechsel. Manuelle Eingriffe an der Pumpe bleiben so bis zum nächsten
Fensterwechsel bestehen. `_last_desired = None` beim Start erzwingt einmaliges
Angleichen.

**2. Nicht erreichbare Pumpe ≠ "aus".** Ist die Pumpe `unavailable`/`unknown`,
bleibt der Wechsel in `_pending` und wird bei jedem Minuten-Tick und bei
jeder Pumpen-Zustandsänderung erneut versucht (gleiche Lektion wie im
Referenz-Projekt, Lektion 2 dort).

**3. Startreihenfolge.** `manager.async_start()` läuft erst NACH
`async_forward_entry_setups`, weil der Schalter "Zeitplan aktiv" seinen
gespeicherten Zustand erst in `async_added_to_hass` wiederherstellt. Sonst
würde vor der Wiederherstellung einmal fälschlich geschaltet.

**4. Zeitfenster über Mitternacht.** `Window.days` bezieht sich immer auf den
Tag des Beginns; `is_active` prüft deshalb auch das Fenster von gestern.
`start == end` ist ungültig (Options-Flow lehnt ab, `parse_windows` ignoriert).

**5. Automatik aus ≠ Pumpe aus.** Bei deaktiviertem Zeitplan ist der
Soll-Zustand `None` (kein Eingriff). Ein manueller Lauf (`run_pump`) hat
Vorrang und schaltet die Pumpe danach ab bzw. gibt sie an den Zeitplan zurück.
Der manuelle Lauf wird nicht über Neustarts hinweg gespeichert.

**6. `OptionsFlow.config_entry` gibt es erst ab HA 2024.11.** Mindestversion
ist 2024.9, daher wird der Entry im Konstruktor übergeben (`self._entry`).

**7. Optionen überschreiben Daten.** `entry.options[CONF_PUMP_ENTITY]` hat
Vorrang vor `entry.data`. Jede Options-Änderung lädt den Eintrag neu.

**8. Tests laufen lokal nur bis HA 2024.3.3 (Python 3.11).** Entity-IDs in
Tests sind englisch (`switch.<pool>_schedule_active`), weil die Test-HA
Englisch nutzt. `tzdata` muss installiert sein.

**9. `py_compile` prüft keine fehlenden Imports.** Nach Änderungen an
`config_flow.py`/`manager.py` die Tests laufen lassen, nicht nur kompilieren.

## Offene/mögliche nächste Schritte

- Weitere Pool-Funktionen nach Bedarf (Temperatur-/Solarregelung,
  Abdeckung, Chlor/pH, Filterreinigung, Benachrichtigungen).
- Dashboard-Karte, Brand-Icons, offizielle HACS-Aufnahme.
