---
name: pleo-library-telemetry-lifecycle
description: Raportuje eventy cyklu życia dla realnie użytych skilli, których nazwa nie zaczyna się od `pleo-library-`. Używaj po target-only version preflight telemetryki i przed wykonaniem skilla docelowego spoza `pleo-library-*`; nie raportuj skilli `pleo-library-*`, version preflightu ani samej telemetryki.
version: 1.2.4
author: p.karas@pleodigital.com
scope: SHARED
category: Library
tags: []
---
# Pleo Library Telemetry Lifecycle

Używaj tego skilla jako wspólnego kontraktu telemetrycznego dla innych skilli.
Ten skill podlega target-only version preflight przez `pleo-library-skill-version-guard` przed pierwszym eventem telemetrycznym w rozmowie.
Raportuj wyłącznie skill docelowy spoza prefiksu `pleo-library-`.
Nie raportuj telemetrycznie skilli `pleo-library-*`, samego version preflightu ani użycia `pleo-library-telemetry-lifecycle`.

## Co raportować

- `start` na początku użycia skilla docelowego.
- `progress` tylko przy realnej zmianie etapu pracy nad skillem docelowym; w krótkim zadaniu bez takiej zmiany pomiń ten event.
- `finish` przy zakończeniu pracy z jawnym `--status success` tylko wtedy, gdy cel skilla został osiągnięty, albo `--status error`, gdy wykonanie lub wymagany wynik się nie powiódł.
- `interrupt` best effort przy przerwaniu pracy przed ustaleniem wyniku; domyślny status to `cancelled`.
- Nie wysyłaj heartbeatów; aktywna sesja bez terminalnej wiadomości zostanie automatycznie uznana za przerwaną po 30 minutach bez nowych eventów.
- Wysyłka wymaga niepustego `TELEMETRY_USER_ID`; skrypt dołącza je jako `telemetryUserId` i `libraryUserId`.

## Zakres obowiązku

- Każdy realnie użyty skill spoza `pleo-library-*` raportuj osobno: `start`, opcjonalne `progress` wyłącznie przy zmianie etapu, a potem `finish` albo `interrupt`.
- Nie raportuj skilli `pleo-library-*`, w tym `pleo-library-prompt-model-triage`, `pleo-library-shared-skill-sync`, `pleo-library-skill-version-guard` i `pleo-library-telemetry-lifecycle`.
- Nie raportuj `pleo-library-skill-version-guard`, gdy działa jako target-only version preflight.
- W telemetryce podawaj nazwę skilla docelowego w argumencie `--skill`, a nie nazwę `pleo-library-telemetry-lifecycle`.

## Skrypt

Skrypt: `skills/pleo-library-telemetry-lifecycle/scripts/run.py`

Konfiguracja:

- `libraryBaseUrl` z `.agent-library.yaml` (wymagane)
- `--source` (wymagane, np. `codex`, `claude`, `gemini`)
- `--skill` (wymagane, nazwa śledzonego skilla docelowego)
- `--project-slug` (opcjonalne, ale zalecane przy raportowaniu do heatmap per projekt)
- `--allow-pleo-library-skill` jest pozostawione tylko jako legacy flaga kompatybilności i nie odblokowuje raportowania skilli `pleo-library-*`
- `TELEMETRY_USER_ID` w env (wymagane do wysyłki; skrypt bez niego kończy się błędem przed wywołaniem API)

Uwaga: skrypt zawsze używa endpointu:
`/api/agent-telemetry/events`

Uwaga: kolejność flag i komendy jest elastyczna. Działają zarówno:
`python .../run.py --source codex start ...`
jak i
`python .../run.py start --source codex ...`

## Workflow agenta

1. Jeśli skill docelowy zaczyna się od `pleo-library-`, nie uruchamiaj telemetryki.
2. Przed version preflightem telemetryki i przed wywołaniem skryptu sprawdź, czy `TELEMETRY_USER_ID` jest ustawione i niepuste. Nie wypisuj jego wartości. Jeśli go brakuje, pomiń całą wysyłkę jako best effort (również `start`, `progress`, `finish` i `interrupt`), kontynuuj pracę nad skillem docelowym i odnotuj brak telemetryki w podsumowaniu; nie ponawiaj wywołań skryptu bez zmiany środowiska.
3. Jeśli identyfikator jest dostępny, przed pierwszym eventem telemetrycznym w rozmowie wykonaj target-only version preflight `pleo-library-telemetry-lifecycle`. Gdy ten preflight się nie powiedzie, pomiń wszystkie eventy telemetryczne dla bieżącego użycia skilla, kontynuuj pracę nad skillem docelowym i odnotuj pominięcie oraz przyczynę w podsumowaniu. Nie ponawiaj eventów, dopóki przyczyna nie zostanie usunięta.
4. Tylko przy dostępnej telemetryce przygotuj osobny `runId` dla każdego skilla docelowego spoza `pleo-library-*`.
5. Przy dostępnej telemetryce wyślij `start` przed realnym rozpoczęciem pracy nad skillem docelowym.
6. Jeśli skill docelowy nie był jeszcze sprawdzony w tej rozmowie ani w dziennym cache version guarda, wykonaj jego target-only version preflight niezależnie od stanu telemetryki: po `start`, jeśli został wysłany, albo bez niego, gdy telemetryka została pominięta.
7. Przy dostępnej telemetryce i realnej zmianie etapu wysyłaj `progress`. Jeśli etap się nie zmienił, przejdź bezpośrednio od `start` do `finish` albo `interrupt`; nie wysyłaj sztucznych heartbeatów.
8. Przy dostępnej telemetryce na końcu wyślij `finish` z jawnym statusem: `success` po osiągnięciu celu, `error` po nieudanym wykonaniu skilla lub nieosiągnięciu wymaganego wyniku. Skrypt odrzuca `finish` bez `--status`; nie zakładaj powodzenia na podstawie samego zakończenia pracy.
9. Jeśli praca została przerwana w sposób kontrolowany przed wynikiem, przy dostępnej telemetryce wyślij `interrupt` best effort zamiast `finish`.
10. Jeśli nie zostanie wysłana terminalna wiadomość, backend automatycznie uzna sesję za przerwaną po 30 minutach bez nowych eventów.

## Przykładowe wywołania

Start:

```bash
python skills/pleo-library-telemetry-lifecycle/scripts/run.py start --source codex --run-id run-123 --skill aidock-rag-indexing-pgvector --project-slug gocouriers/aidock
```

Progress:

```bash
python skills/pleo-library-telemetry-lifecycle/scripts/run.py --source codex progress --run-id run-123 --skill aidock-rag-indexing-pgvector --project-slug gocouriers/aidock --stage analysis --message "Collecting context"
```

Finish:

```bash
python skills/pleo-library-telemetry-lifecycle/scripts/run.py --source codex finish --run-id run-123 --skill aidock-rag-indexing-pgvector --project-slug gocouriers/aidock --status success
```

Finish po nieudanym wykonaniu skilla:

```bash
python skills/pleo-library-telemetry-lifecycle/scripts/run.py finish --source codex --run-id run-123 --skill aidock-rag-indexing-pgvector --project-slug gocouriers/aidock --status error
```

## Wymagany config repo

Skrypt odczytuje z `.agent-library.yaml` tylko `libraryBaseUrl`:

```yaml
libraryBaseUrl: https://pleoai-69566.ondigitalocean.app
```

Inne pola konfiguracji repo mogą być potrzebne pozostałym skillom, ale skrypt telemetryki ich nie odczytuje. Slug projektu dla eventu podaj jawnie przez `--project-slug`, gdy jest potrzebny.

## Ważne reguły

- Nie raportuj skilli `pleo-library-*`.
- Nie raportuj version preflightu wykonywanego przez `pleo-library-skill-version-guard`.
- Nie używaj nazwy `pleo-library-telemetry-lifecycle` w `--skill`, jeśli telemetryka ma opisywać użycie innego skilla.
- Nie używaj komendy `heartbeat`; została usunięta. Nie wysyłaj też sztucznych heartbeatów przez `progress`.
- Nie zgaduj `telemetryUserId` z maila, git config ani loginu systemowego; używaj wyłącznie niepustego `TELEMETRY_USER_ID`.
- Jeśli telemetryka nie może zostać wysłana, traktuj to jako best effort i jasno odnotuj brak pełnej weryfikacji w podsumowaniu.
