---
name: pleo-library-project-instruction-sync
description: Operacyjnie synchronizuje lokalne pliki `AGENTS.md`, `CLAUDE.md` i `GEMINI.md` z centralną biblioteką po `projectSlug`. Używaj przy jawnej prośbie o check, pull albo publish instrukcji projektowych oraz przed merytoryczną edycją tych plików, żeby najpierw sprawdzić aktualność lokalnej bazy.
version: 1.0.6
author: p.karas@pleodigital.com
scope: SHARED
category: Library
tags: []
---
# Pleo Library Project Instruction Sync

Używaj tego skilla jako operacji utrzymaniowej, gdy repo ma lokalne `AGENTS.md`, `CLAUDE.md` albo `GEMINI.md`, które użytkownik chce sprawdzić, pobrać z biblioteki albo opublikować do biblioteki.
Używaj go też przed merytoryczną edycją lokalnych instrukcji projektu, żeby najpierw uruchomić `check` i upewnić się, że agent nie dopisuje zmian na nieaktualnej wersji z biblioteki.
Nie uruchamiaj go jako domyślnego kroku startowego przy zwykłej pracy w kodzie ani tylko dlatego, że bieżące zadanie dzieje się w repo z `.agent-library.yaml`.

## Wymagany config repo

Plik `.agent-library.yaml`:

```yaml
libraryBaseUrl: https://pleoai.example.com
projectSlug: org/repo-name
paths:
  agents: AGENTS.md
  claude: CLAUDE.md
  gemini: GEMINI.md
  skillsDir: skills
publish:
  defaultScope: PROJECT
```

`projectSlug` jest jedynym identyfikatorem projektu wymaganym przez ten skill.

## Jak uruchomić

Sprawdzenie statusu:

```bash
python skills/pleo-library-project-instruction-sync/scripts/run.py check
```

Pobranie konkretnego typu po zgodzie użytkownika:

```bash
python skills/pleo-library-project-instruction-sync/scripts/run.py pull --type AGENTS
```

Publikacja konkretnego typu po zgodzie użytkownika:

```bash
python skills/pleo-library-project-instruction-sync/scripts/run.py publish --type AGENTS
```

`publish` używa anonimowego endpointu `POST /library/projects/agent-instructions/remote/upsert` i wysyła `projectSlug`.

Skrypt wypisuje wynik jako JSON.

## Workflow agenta

1. Uruchom `check`.
2. Dla każdego typu `AGENTS`, `CLAUDE`, `GEMINI` porównaj `localVersion`, `remoteVersion`, `localSha256`, `remoteSha256`, `contentEqual` i `sameVersionDifferentContent`.
3. Jeśli biblioteka PLEO ma nowszą wersję, zapytaj:
`W bibliotece PLEO jest nowsza wersja {filename}: {localVersion} -> {remoteVersion}. Czy chcesz ją pobrać i podmienić lokalny plik?`
4. Dopiero po zgodzie uruchom `pull --type <TYPE>`.
5. Jeśli lokalna instrukcja ma zostać zmieniona merytorycznie, edytuj ją dopiero po obsłużeniu wyniku `check`.
6. Jeśli `sameVersionDifferentContent=true`, przed publikacją podbij `# WERSJA`; `publish` ma przerwać lokalnym błędem, jeśli treść różni się od remote przy tej samej wersji.
7. Jeśli użytkownik potwierdzi publikację lokalnie zmienionej instrukcji, uruchom `publish --type <TYPE>`.

## Ważne reguły

- Nie nadpisuj lokalnych plików bez wyraźnej zgody użytkownika.
- Przed merytoryczną edycją `AGENTS.md`, `CLAUDE.md` albo `GEMINI.md` `check` jest wymagany; `pull` i `publish` nadal wymagają wyraźnej zgody użytkownika.
- Traktuj `projectSlug` jako źródło wyboru projektu; nie zgaduj go z katalogu repo.
- Jeśli plik z biblioteki albo plik lokalny nie ma `# WERSJA`, przerwij z błędem.
- Przy `502`, `503` albo `504` z biblioteki skrypt może wykonać ograniczone retry; nie retryuj błędów walidacyjnych takich jak `400`, `403` albo konfliktów `409`.
- Jeśli biblioteka nie zwraca wpisu dla danego typu, zostaw lokalny plik bez zmian.
