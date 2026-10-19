---
name: pleo-library-project-skill-bootstrap
description: Operacyjnie bootstrapuje repo pod pracę ze skillami bibliotecznymi. Używaj wyłącznie przy onboardingu repo, naprawie struktury `skills`, `.agent-library.yaml` albo sekcji skilli w `AGENTS.md`/`CLAUDE.md`/`GEMINI.md`; nie używaj jako pre-response.
version: 1.3.9
author: p.karas@pleodigital.com
scope: SHARED
category: Library
tags: []
---
# Pleo Library Project Skill Bootstrap

Uruchamiaj ten skill tylko przy onboardingu nowego repo do biblioteki skilli albo gdy użytkownik jawnie chce naprawić instrukcje projektowe, `.agent-library.yaml` lub lokalny katalog `skills`.
Nie używaj go jako pierwszego skilla dla zwykłych zadań kodowych, review, researchu ani pracy ze skillami merytorycznymi.

## Zakres

Skrypt z `scripts/run.py` robi cztery rzeczy:

1. sprawdza strukturę `skills/` i zgłasza katalogi bez `SKILL.md`, bez frontmatter `version` albo z rozjazdem między nazwą folderu i frontmatter `name`,
2. sprawdza `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` i porównuje ich sekcję `## Skille` z aktualną listą lokalnych skilli oraz z wymaganymi regułami telemetryki, a także pilnuje sekcji `## Zgoda Na Pleo Library`,
3. sprawdza, czy w środowisku jest ustawione `TELEMETRY_USER_ID`, i zgłasza brak tej zmiennej jako rekomendowaną konfigurację telemetryki użytkownika,
4. zgłasza brak `.agent-library.yaml`, a w trybie `fix` tworzy ten plik z domyślnym `libraryBaseUrl: https://pleoai-69566.ondigitalocean.app`,
5. w trybie `fix` dopisuje lub odświeża sekcję skilli wraz z obowiązkową informacją o `pleo-library-telemetry-lifecycle`, dopisuje sekcję `## Zgoda Na Pleo Library` oraz tworzy brakujące pliki instrukcji, kopiując istniejący plik instrukcji jako bazę albo generując minimalny szablon.

## Jak uruchamiać

Najpierw sprawdzenie:

```bash
python skills/pleo-library-project-skill-bootstrap/scripts/run.py check
```

Symulacja zmian bez zapisu:

```bash
python skills/pleo-library-project-skill-bootstrap/scripts/run.py fix --dry-run
```

Zapis zmian:

```bash
python skills/pleo-library-project-skill-bootstrap/scripts/run.py fix
```

Skrypt wypisuje wynik jako JSON.

## Zasady działania

- Traktuj `.agent-library.yaml` jako preferowane źródło ścieżek, ale jeśli pliku nie ma, `fix` ma go utworzyć z domyślną konfiguracją biblioteki.
- Przy tworzeniu `.agent-library.yaml` ustaw `libraryBaseUrl` na `https://pleoai-69566.ondigitalocean.app` i spróbuj wywnioskować `projectSlug` z `git remote origin`.
- Nie nadpisuj istniejącego `.agent-library.yaml`, jeśli już jest w repo; bootstrap ma go utworzyć tylko wtedy, gdy brakuje pliku.
- Nie nadpisuj całych instrukcji projektu, jeśli wystarczy podmienić tylko sekcję `## Skille`.
- Przy poprawie sekcji `## Skille` bootstrap ma dopilnować flow: `pleo-library-skill-version-guard` jako target-only check aktualności skilli użytych w aktualnym procesie, routing, potem skille wykonawcze.
- Przy poprawie sekcji `## Skille` bootstrap ma dopilnować bramki triage: reasoning `medium` albo niżej kontynuuje bez pytania, a reasoning powyżej `medium` wymaga potwierdzenia użytkownika przed dalszą pracą.
- Przy poprawie sekcji `## Skille` bootstrap ma dopilnować, żeby żaden skill `pleo-library-*` nie był raportowany w telemetryce.
- Przy poprawie sekcji `## Skille` bootstrap ma dopilnować, żeby `pleo-library-skill-version-guard` był opisany jako infrastrukturalny check bez telemetryki: sprawdza target i status manifestu, robi pełny sync tylko dla nieświeżego manifestu, zmiany liczby skilli albo po aktualizacji targetu oraz automatycznie aktualizuje wykryte nieaktualne skille z czystymi katalogami Git.
- Przy poprawie sekcji `## Skille` bootstrap ma dopilnować reguły braku utraty informacji przy refaktorze, tłumaczeniu albo porządkowaniu skilli.
- Bootstrap ma także utrzymywać sekcję `## Zgoda Na Pleo Library`, która mówi, że obecność `.agent-library.yaml` oznacza zgodę na wywołania do skonfigurowanego `libraryBaseUrl`, w tym sync manifestu wersji projektu i telemetrykę.
- Bootstrap ma raportować, czy bieżące środowisko ma ustawione `TELEMETRY_USER_ID`; gdy go brakuje, agent powinien zapytać użytkownika, czy chce skonfigurować tę zmienną na poziomie użytkownika systemu, i podpowiedzieć, że wartość identyfikatora jest dostępna w sekcji profilu w PleoAI.
- Reguła telemetry jest twarda tylko dla skilli spoza `pleo-library-*`: wysyłaj `start`, `progress` tylko przy realnej zmianie etapu, a potem `finish` albo `interrupt`; nie raportuj samego version preflightu ani żadnych skilli `pleo-library-*`. Nie wysyłaj heartbeatów; aktywna sesja bez terminalnej wiadomości zostanie automatycznie uznana za przerwaną po 30 minutach bez nowych eventów.
- Gdy trzeba utworzyć brakujący `CLAUDE.md` albo `GEMINI.md`, preferuj skopiowanie istniejącego pliku instrukcji i zmianę nagłówka na właściwy plik docelowy.
- Jeśli nie istnieje żaden plik instrukcji, wygeneruj minimalny plik z `frontmatter `version` 1.0.0`, nagłówkiem projektu i sekcją `## Skille`.
- Jeśli zmieniasz lokalne `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` albo `.agent-library.yaml`, na końcu przypomnij użytkownikowi o świadomym podbiciu frontmatter `version` tam, gdzie to potrzebne, i zapytaj, czy opublikować zmiany do biblioteki.
- Aktualizacja albo synchronizacja lokalnego skilla z biblioteki przez `pleo-library-skill-version-guard` lub `pleo-library-shared-skill-sync` nie jest traktowana jako lokalna zmiana merytoryczna na potrzeby reguł frontmatter `version` i pytania o publikację.
- Jeśli zmieniasz lokalny skill w `skills/**` merytorycznie, na końcu również zapytaj użytkownika, czy opublikować go do biblioteki.

