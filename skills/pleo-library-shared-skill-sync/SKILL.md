---
name: pleo-library-shared-skill-sync
description: Sprawdza listę shared skilli w bibliotece i porównuje ją z lokalnym katalogiem `skills`. Używaj, gdy użytkownik chce zobaczyć brakujące shared skille, pobrać shared skille albo gdy `pleo-library-prompt-model-triage` wskaże ten skill; nie raportuj tego skilla w telemetryce.
version: 1.2.8
author: p.karas@pleodigital.com
scope: SHARED
category: Library
tags: []
---
# Pleo Library Shared Skill Sync

Podczas pobierania pomijaj katalogi `__pycache__` i pliki `.pyc`/`.pyo` oraz odrzucaj pliki tekstowe spoza UTF-8.

Uruchamiaj ten skill wtedy, gdy użytkownik chce porównać lokalny projekt z listą shared skilli dostępnych w bibliotece, dociągnąć brakujące katalogi skilli do repo albo gdy `pleo-library-prompt-model-triage` wskaże, że do zadania potrzebny jest sync shared skilli.
Nie uruchamiaj go przed pierwszym routingiem triage, chyba że użytkownik jawnie prosi właśnie o sync shared skilli.
Nie raportuj tego skilla w telemetryce, bo nazwa zaczyna się od `pleo-library-`.

## Jak działa

Skrypt z `scripts/run.py`:

1. pobiera listę shared skilli z biblioteki przez publiczny `GET /skills/remote/shared`,
2. pobiera listę dostępnych kategorii shared skilli przez publiczny `GET /skills/remote/shared/categories` tylko dla jawnej komendy `categories`; zwykły `check` nie zależy od tego endpointu,
3. potrafi filtrować shared skille po kategorii, tagach albo obu naraz,
4. porównuje wynik z lokalnym katalogiem `skills/`,
5. wskazuje brakujące shared skille oraz ich `latestVersion`,
6. porównuje lokalną i zdalną wersję shared skilli oraz zwraca `versionState`, `needsPull`, `needsPublish`, `localNewerThanRemote` i `remoteNewerThanLocal`,
7. przed pobraniem waliduje wszystkie wskazane nazwy, rozpoznaje jednoznaczne aliasy nazw i nie blokuje poprawnych pozycji przez jedną błędną pozycję,
8. po pokazaniu użytkownikowi listy brakujących skilli i uzyskaniu wyboru pobiera tylko wskazane brakujące skille do `skills/`,
9. odświeża sekcję `## Skille` w `AGENTS.md`, `CLAUDE.md` i `GEMINI.md`.

## Jak uruchamiać

Sprawdzenie braków:

```bash
python skills/pleo-library-shared-skill-sync/scripts/run.py categories
python skills/pleo-library-shared-skill-sync/scripts/run.py check
python skills/pleo-library-shared-skill-sync/scripts/run.py check --category "<category>"
python skills/pleo-library-shared-skill-sync/scripts/run.py check --tag "<tag>"
python skills/pleo-library-shared-skill-sync/scripts/run.py check --category "<category>" --tag "<tag>"
```

Pobranie wskazanych brakujących skilli:

```bash
python skills/pleo-library-shared-skill-sync/scripts/run.py pull --skill pleo-example-skill
python skills/pleo-library-shared-skill-sync/scripts/run.py pull --skill pleo-example-skill --tag "<tag>"
```

Skrypt wypisuje wynik jako JSON.

## Zasady

- W standardowym flow może go poprzedzać target-only check przez `pleo-library-skill-version-guard`, jeśli trzeba sprawdzić aktualność skilla użytego w aktualnym procesie.
- Nie raportuj telemetryki dla tego skilla i nie używaj `--allow-pleo-library-skill` w zwykłym flow.
- Gdy użytkownik chce najpierw zobaczyć dostępne kategorie, uruchom osobną komendę `categories`. `check` — także z `--category` — korzysta bezpośrednio z `GET /skills/remote/shared` i nie może być blokowany przez awarię pomocniczego endpointu kategorii.
- Traktuj `GET /skills/remote/shared` jako publiczne źródło prawdy dla shared skilli w wybranym filtrze: kategorii, tagach albo obu naraz.
- Gdy `pull --skill` dostaje kilka nazw, najpierw rozwiąż wszystkie nazwy względem listy remote; pobieraj jednoznacznie rozpoznane pozycje, a nierozpoznane albo niejednoznaczne zwracaj w `requestedSkillResolution.unresolvedSkills`.
- Jeśli dokładna nazwa nie istnieje, traktuj jednoznaczne dopasowanie aliasu jako poprawne tylko wtedy, gdy kandydat jest unikalny; przy wielu kandydatach nie zgaduj.
- Nie proponuj pobrania wszystkich shared skilli ani wszystkich braków, chyba że użytkownik wyraźnie poprosi o hurtowe pobranie.
- Nie pobieraj wszystkich brakujących shared skilli hurtowo; po `check` pokaż użytkownikowi listę braków i pobierz tylko jawnie wybrane pozycje przez `pull --skill`.
- Przy `check` traktuj `localNewerThanRemote` jako sygnał, że lokalna wersja powinna zostać opublikowana przez `pleo-library-skill-publisher`, a `remoteNewerThanLocal` jako sygnał do pull przez `pleo-library-skill-version-guard`.
- Nie nadpisuj istniejącego lokalnego skilla przy `pull`; ten skill służy do pobierania brakujących katalogów, nie do aktualizacji już obecnych.
- Po `pull` zawsze odśwież lokalne `AGENTS.md`, `CLAUDE.md` i `GEMINI.md`.
- Przy odświeżaniu instrukcji utrzymaj bramkę triage: reasoning `medium` albo niżej kontynuuje bez pytania, a reasoning powyżej `medium` wymaga potwierdzenia użytkownika przed dalszą pracą.
- Przy odświeżaniu instrukcji utrzymaj zasadę `pleo-library-skill-version-guard`: check targetu i statusu manifestu bez telemetryki, pełny sync tylko gdy potrzebny oraz automatyczny pull wykrytych nieaktualnych skilli z czystymi katalogami Git.
- Przy odświeżaniu instrukcji utrzymaj zasadę telemetryki bez heartbeatów: `progress` tylko przy realnej zmianie etapu, a sesja bez terminalnego eventu zostanie automatycznie uznana za przerwaną po 30 minutach bez nowych eventów.
- Po `pull` uznaj wcześniej zaczytane w czacie wersje nowo pobranych skilli oraz odświeżonych plików instrukcji za nieaktualne.
- Jeśli dalsza praca zależy od któregoś z pobranych skilli albo od zaktualizowanych `AGENTS.md`, `CLAUDE.md` lub `GEMINI.md`, odczytaj te pliki ponownie z dysku i kontynuuj na świeżej treści.
- Jeśli użytkownik chce zaktualizować już istniejący lokalny skill do nowszej wersji, użyj `pleo-library-skill-version-guard`, nie tego skilla.
- Jeśli po pobraniu zmieniły się lokalne instrukcje projektu albo nowe skille w `skills/**`, na końcu przypomnij o świadomym podbiciu frontmatter `version` tam, gdzie to potrzebne, i zapytaj użytkownika, czy opublikować zmiany do biblioteki.
