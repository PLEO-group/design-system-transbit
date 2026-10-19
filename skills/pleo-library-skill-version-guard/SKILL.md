---
name: pleo-library-skill-version-guard
description: Sprawdza wersję wskazanego skilla, pilnuje świeżości manifestu projektu i automatycznie aktualizuje wykryte nieaktualne skille, jeżeli ich katalogi są czyste w Git. Nie pyta o zgodę na bezpieczny pull i nie raportuje telemetryki.
version: 1.8.2
author: p.karas@pleodigital.com
scope: SHARED
category: Library
tags: []
---
# Pleo Library Skill Version Guard

Podczas aktualizacji pomijaj katalogi `__pycache__` i pliki `.pyc`/`.pyo` oraz odrzucaj pliki tekstowe spoza UTF-8.

Guard utrzymuje wersje skilli bez ręcznego potwierdzania bezpiecznych aktualizacji.

## Zasady

- Uruchamiaj go tylko dla konkretnego skilla używanego w bieżącym procesie albo na jawne żądanie sprawdzenia wersji.
- `check` porównuje lokalne `version` z `latestVersion` w bibliotece.
- Po target-checku wykonuje lekki check statusu manifestu.
- Pełny sync listy lokalnych `skillName + installedVersion` wykonuje tylko wtedy, gdy manifest nie był zweryfikowany dzisiaj, zmieniła się liczba lokalnych skilli albo target został właśnie zaktualizowany.
- Każdy nieaktualny skill wykryty bezpośrednio albo przez manifest aktualizuje od razu bez pytania użytkownika.
- Jeśli katalog jest czysty, skrypt automatycznie wykonuje pull bez pytania użytkownika.
- Jeśli katalog ma zmiany staged, unstaged albo untracked, skrypt nie aktualizuje skilla i zwraca `blockedReason: local_changes`. Nie proś wtedy automatycznie o zgodę na nadpisanie zmian.
- W runtime Astrei skille są zarządzane per task. Gdy konfiguracja ma `runtimeManagedSkills: true`, guard używa zapisywalnego `workspace/skills`, pomija jego kontrolę Git, zachowuje atomową podmianę oraz próbuje zapisać snapshot faktycznie zainstalowanej aktualizacji pod ścieżką przekazaną przez `PLEO_ASTREA_SKILL_SNAPSHOT_DIR`. Snapshot jest opcjonalnym artefaktem technicznym publikatora, nie zmianą repozytorium: błąd jego zapisu jest raportowany diagnostycznie, ale nie cofa aktualizacji skilla i nie blokuje pracy Astrei.
- Dla aktywnego workspace'u utworzonego przez runtime używający read-only symlinka `workspace/skills -> /srv/pleo-agent/skills` guard jednorazowo materializuje task-localną kopię wszystkich skilli i od tej chwili aktualizuje wyłącznie ją. Nie próbuje tworzyć locka ani podmieniać plików w chronionym katalogu globalnym.
- W trybie Astrei konfigurację workspace wskaż przez `PLEO_ASTREA_WORKSPACE_ROOT`. Guard szuka jej przed fallbackiem do lokalizacji skryptu, dzięki czemu symlink `skills` do współdzielonego katalogu nie zmienia repo root.
- Przed podmianą guard ponownie porównuje aktualną wersję z wersją payloadu. Jeśli używana jest już ta sama albo nowsza wersja, nie nadpisuje katalogu; zapisuje jednak snapshot wersji używanej przez bieżący task, aby późniejsza publikacja była powtarzalna. Równoległość tego samego taska zabezpiecza nadrzędny `task.lock` runtime Astrei.
- Dla workspace Astrei utworzonego przez starszy runtime, którego `.agent-library.yaml` nie ma jeszcze `paths`, guard używa istniejącego `workspace/skills` jako zarządzanego katalogu. Dzięki temu aktualizacja runtime nie wymaga restartowania aktywnych tasków.
- Po aktualizacjach synchronizuje manifest ponownie. Liczba prób jest ograniczona liczbą lokalnych skilli.
- Katalog z `SKILL.md` bez poprawnego frontmatter `version` nie przerywa synchronizacji pozostałych skilli: guard pomija go w payloadzie manifestu i raportuje w `invalidLocalSkills` z przyczyną `invalid_skill_metadata`.
- Po automatycznym pullu odczytaj zaktualizowany skill ponownie, jeżeli dalsza praca zależy od jego instrukcji.
- Guard jest infrastrukturą; nie wysyłaj dla niego telemetryki.
- Przed uruchomieniem wymagana jest niepusta zmienna `TELEMETRY_USER_ID`.

## Uruchomienie

Wybierz dostępny launcher Pythona i uruchom:

```bash
python skills/pleo-library-skill-version-guard/scripts/run.py check --skill <skill-name>
```

Jawne `pull --skill <skill-name>` pozostaje dostępne operacyjnie, ale również odmawia nadpisania katalogu z lokalnymi zmianami.

## Wynik

Najważniejsze pola JSON:

- `versionRelation`: `missing_remote`, `local_newer`, `remote_newer` albo `same`;
- `needsPull`: czy biblioteka miała nowszą wersję;
- `localStateBeforeUpdate.clean`: czy katalog był czysty przed aktualizacją;
- `autoPull`: wynik automatycznej aktualizacji albo przyczyna blokady;
- `projectSkillStateSync.autoUpdatedSkills`: skille zaktualizowane na podstawie manifestu;
- `projectSkillStateSync.blockedSkills`: skille pominięte z powodu lokalnych zmian lub błędu;
- `projectSkillStateSync.invalidLocalSkills`: lokalne katalogi pominięte w manifeście z powodu brakującej lub nieprawidłowej wersji;
- `projectSkillStateSync.skipped`: `true`, gdy dzisiejszy manifest i liczba skilli pozwoliły pominąć pełny sync;
- `updateStrategy`: strategia zapisu zwrócona w `autoPull.pullResult`.
