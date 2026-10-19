---
name: pleo-library-versioning-rml
description: >
  Pomocniczo dobieraj podbicie wersji lokalnych skillów i specyfikacji w modelu `R.M.L`.
  Używaj po decyzji, że artefakt w `skills/**` albo `docs/sdd/**` faktycznie jest zmieniany
  lub publikowany; nie używaj jako pre-response ani ogólnego triggera dla zwykłych zadań.
version: 1.1.3
author: j.gajecki@pleodigital.com
scope: SHARED
category: Library
tags: []
---
# Pleo Library Versioning RML

## Cel

Używaj tego skilla przed zmianą frontmatter `version` w lokalnym skillu z `skills/` oraz przed zmianą wersji lokalnej specyfikacji w `docs/sdd/`, ale dopiero po decyzji, że dany artefakt faktycznie jest zmieniany lub publikowany.
Nie uruchamiaj go jako pierwszego skilla przy zwykłym promptcie; routing należy do `pleo-library-prompt-model-triage`.
Celem jest przewidywalne i spójne wersjonowanie artefaktów publikowanych do Pleo Library.

## Model wersji

Każdą wersję traktuj jako `R.M.L`:

- `R` = release,
- `M` = major,
- `L` = lesser.

Przykład: `1.4.0` oznacza release `1`, major `4`, lesser `0`.

## Reguły decyzji

Stosuj poniższe reguły w kolejności.

### 1. Release bump

Podbij `R` tylko na bezpośrednią prośbę użytkownika.

Przykład: `1.4.3` -> `2.0.0`.

Reguły:

- nigdy nie podbijaj `R` samodzielnie,
- nowy release zawsze resetuje `M` i `L` do `0`,
- traktuj release jako zmianę wyjątkową i świadomą.

### 2. Major bump

Podbij `M`, gdy artefakt dostaje istotną zmianę wpływającą na sposób użycia albo zachowanie.

Przykład: `1.4.3` -> `1.5.0`.

Typowe przypadki:

- nowe gałęzie workflow albo nowe drzewka decyzyjne,
- nowe obowiązkowe kroki,
- nowe bramki jakości albo silniejsze reguły walidacji,
- zmienione warunki uruchamiania skilla,
- nowe zasoby istotnie rozszerzające możliwości skilla,
- zmiany wpływające na decyzję, output albo proces agenta,
- nowe istotne wymagania lub flow w specyfikacji.

Reguły:

- nowy major zawsze resetuje `L` do `0`,
- liczba zmienionych linii jest tylko wskazówką; decyduje wpływ funkcjonalny,
- używaj `M` tylko wtedy, gdy zmiana realnie zmienia workflow, granice możliwości, triggery albo wymaganą ścieżkę decyzyjną,
- nie traktuj każdej zmiany logiki jako major; wąskie doprecyzowanie może być `L`.

### 3. Lesser bump

Podbij `L` dla małych i niedestrukcyjnych zmian.

Przykład: `1.4.3` -> `1.4.4`.

Typowe przypadki:

- literówki,
- doprecyzowanie treści,
- małe przykłady,
- niewielkie doprecyzowania logiki bez zmiany głównego workflow,
- wąskie reguły, które nie zmieniają głównych założeń,
- drobne dodatki porządkujące artefakt.

Reguły:

- używaj `L`, gdy zmiana jest korektą, opisem albo wąskim dodatkiem,
- używaj `L` także dla małych zmian klasyfikacji, jeśli nie redefiniują głównego kontraktu,
- nie używaj `L`, gdy zmienia się główny workflow, granica możliwości albo wymagana ścieżka decyzji.

## Workflow

1. Ustal, jaki artefakt wersjonujesz:
   - lokalny skill w `skills/`,
   - lokalną specyfikację w `docs/sdd/`.
2. Oceń skalę zmiany:
   - wording, przykłady, doprecyzowania albo małe korekty logiki -> kandydat na `L`,
   - istotna zmiana workflow, możliwości, triggerów albo ścieżki decyzyjnej -> kandydat na `M`.
3. Sprawdź, czy poprzednie lokalne zmiany tego artefaktu zostały już opublikowane.
   - jeśli nie, zachowaj obecną wersję i kontynuuj pracę na tej samej nieopublikowanej wersji,
   - nie dokładaj kolejnego bumpa zanim pierwsza wersja zostanie opublikowana.
4. Sprawdź, czy użytkownik jawnie poprosił o nowy release.
5. Wybierz bump:
   - jawna prośba o release -> `R`,
   - istotna zmiana workflow albo zachowania -> `M`,
   - pozostałe przypadki -> `L`.
6. Zastosuj wersję konsekwentnie:
   - dla skilla zaktualizuj frontmatter `version` w `SKILL.md`,
   - dla specyfikacji zaktualizuj dokument i powiązany rejestr, np. `docs/sdd/versioning.md`.
7. W podsumowaniu krótko podaj wybrany typ bumpa.

## Nowy skill

- Jeśli nowy lokalny skill powstał w bieżącym zadaniu i dopiero dostaje pierwszą pełną treść, zostaw wersję `1.0.0`.
- Nie rób sztucznego bumpa tylko dlatego, że skeleton został wypełniony.
- Pierwszy realny bump wykonuj dopiero w kolejnym zadaniu aktualizującym już gotowy skill.

## Nowa specyfikacja

- Jeśli nowa główna specyfikacja powstała w bieżącym zadaniu i dopiero dostaje pierwszą pełną treść, zostaw wersję `1.0.0`.
- Nie rób sztucznego bumpa tylko dlatego, że skeleton został wypełniony.
- Gdy specyfikacja zostaje przy `1.0.0`, utrzymaj zgodność z `docs/sdd/versioning.md`.

## Nieopublikowane zmiany lokalne

- Jeśli artefakt ma już lokalne istotne zmiany, które nie zostały opublikowane, nie podbijaj wersji ponownie.
- Kontynuuj edycję pod aktualną nieopublikowaną wersją.
- Kolejny bump `R`, `M` albo `L` wykonuj dopiero po publikacji poprzedniej zmiany.
- Stosuj tę regułę zarówno dla skillów, jak i specyfikacji.

## Domyślna interpretacja

Jeśli właściwy bump nie jest oczywisty:

- nie eskaluj do `R` bez jawnej prośby,
- preferuj `M` tylko przy istotnej zmianie workflow, triggerów, granic możliwości albo decyzji,
- preferuj `L`, gdy zmiana jest mała i nie zmienia głównych założeń,
- krótko opisz przyjęte założenie.
