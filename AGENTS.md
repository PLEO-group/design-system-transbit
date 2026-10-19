# WERSJA 1.0.0

# Instrukcje AGENTS.md dla design-system-transbit
<INSTRUCTIONS>
## Skille
Skill to lokalny zestaw instrukcji zapisany w pliku `SKILL.md`.

### Dostępne skille
- pleo-library-project-instruction-sync: Operacyjnie synchronizuje lokalne pliki `AGENTS.md`, `CLAUDE.md` i `GEMINI.md` z centralną biblioteką po `projectSlug`. Używaj przy jawnej prośbie o check, pull albo publish instrukcji projektowych oraz przed merytoryczną edycją tych plików, żeby najpierw sprawdzić aktualność lokalnej bazy. (file: skills/pleo-library-project-instruction-sync/SKILL.md)
- pleo-library-project-skill-bootstrap: Operacyjnie bootstrapuje repo pod pracę ze skillami bibliotecznymi. Używaj wyłącznie przy onboardingu repo, naprawie struktury `skills`, `.agent-library.yaml` albo sekcji skilli w `AGENTS.md`/`CLAUDE.md`/`GEMINI.md`; nie używaj jako pre-response. (file: skills/pleo-library-project-skill-bootstrap/SKILL.md)
- pleo-library-prompt-model-triage: Pierwszy router promptu po target-only version preflight. Szybko klasyfikuj bieżący prompt pod najlepszy poziom modelu, reasoning, koszt i dobór skilli wykonawczych. Nie raportuj tego skilla w telemetryce, bo jego nazwa zaczyna się od `pleo-library-`. (file: skills/pleo-library-prompt-model-triage/SKILL.md)
- pleo-library-shared-skill-sync: Sprawdza listę shared skilli w bibliotece i porównuje ją z lokalnym katalogiem `skills`. Używaj, gdy użytkownik chce zobaczyć brakujące shared skille, pobrać shared skille albo gdy `pleo-library-prompt-model-triage` wskaże ten skill; nie raportuj tego skilla w telemetryce. (file: skills/pleo-library-shared-skill-sync/SKILL.md)
- pleo-library-skill-publisher: Operacyjnie publikuje, audytuje, migruje scope, zmienia nazwę albo usuwa lokalny skill w centralnej bibliotece przez skrypt z `scripts/`. Używaj wyłącznie, gdy użytkownik jawnie prosi o publikację, audyt publikacji, migrację PROJECT/SHARED, rename albo delete skilla; nie używaj jako pre-response. (file: skills/pleo-library-skill-publisher/SKILL.md)
- pleo-library-skill-version-guard: Sprawdza wersję wskazanego skilla, pilnuje świeżości manifestu projektu i automatycznie aktualizuje wykryte nieaktualne skille, jeżeli ich katalogi są czyste w Git. Nie pyta o zgodę na bezpieczny pull i nie raportuje telemetryki. (file: skills/pleo-library-skill-version-guard/SKILL.md)
- pleo-library-spec-workflow-helper: Operacyjnie sprawdza, pobiera i publikuje workflow spec-review w PleoAI/DO Spaces oraz obsługuje kontekst i start prespecki. Używaj wyłącznie przy jawnych operacjach storage, publish, update albo pull dla `docs/sdd/versioning.md`, `specification.md`, `story-<jira>.md` i `affectedSpecifications` oraz przy `prespec-context` lub potwierdzonym `prespec-start`; nie używaj do zwykłego pisania specyfikacji. (file: skills/pleo-library-spec-workflow-helper/SKILL.md)
- pleo-library-telemetry-lifecycle: Raportuje eventy cyklu życia dla realnie użytych skilli, których nazwa nie zaczyna się od `pleo-library-`. Używaj po target-only version preflight telemetryki i przed wykonaniem skilla docelowego spoza `pleo-library-*`; nie raportuj skilli `pleo-library-*`, version preflightu ani samej telemetryki. (file: skills/pleo-library-telemetry-lifecycle/SKILL.md)
- pleo-library-versioning-rml: Pomocniczo dobieraj podbicie wersji lokalnych skillów i specyfikacji w modelu `R.M.L`. Używaj po decyzji, że artefakt w `skills/**` albo `docs/sdd/**` faktycznie jest zmieniany lub publikowany; nie używaj jako pre-response ani ogólnego triggera dla zwykłych zadań. (file: skills/pleo-library-versioning-rml/SKILL.md)

### Jak używać skilli
- Uruchom skill, gdy zadanie wyraźnie pasuje do jego opisu.
- `pleo-library-skill-version-guard` wykonuje target-only check wskazanego skilla i lekki check statusu manifestu; pełny sync robi tylko dla manifestu niezweryfikowanego dzisiaj, zmiany liczby skilli albo po aktualizacji targetu.
- Wszystkie wykryte nieaktualne skille z czystymi katalogami Git aktualizuje automatycznie bez pytania użytkownika; lokalne zmiany blokują pull danego skilla.
- Nie raportuj telemetrycznie samego `pleo-library-skill-version-guard`, bo to infrastrukturalny check aktualności skilli.
- Przed użyciem lokalnych skilli uruchom `pleo-library-skill-version-guard`, jeśli chcesz potwierdzić aktualność skilli w repo.
- Po routingu `pleo-library-prompt-model-triage` kontynuuj bez pytania, jeśli rekomendowany reasoning to `medium` albo niżej; jeśli reasoning jest wyższy niż `medium`, zatrzymaj się i czekaj na jasne potwierdzenie użytkownika przed dalszą pracą.
- Nie raportuj telemetrycznie żadnych skilli `pleo-library-*`, w tym `pleo-library-prompt-model-triage`, `pleo-library-shared-skill-sync`, `pleo-library-skill-version-guard` i `pleo-library-telemetry-lifecycle`.
- Jeśli triage wskazuje `pleo-library-shared-skill-sync`, wykonaj go bez telemetryki.
- Dla skilli docelowych spoza `pleo-library-*` wyślij `start`, wysyłaj `progress` tylko przy realnej zmianie etapu, a na końcu `finish` albo `interrupt`.
- Pełny audyt wersji wszystkich skilli albo synchronizację całego stanu projektu wykonuj tylko na jawne polecenie użytkownika.
- Jeśli zadanie dotyczy dodania nowego skilla do biblioteki albo publikacji zmian lokalnego skilla do biblioteki, użyj `pleo-library-skill-publisher`.
- Jeśli zadanie zmodyfikowało lokalny skill w `skills/**` albo lokalny plik `AGENTS.md`, `CLAUDE.md` lub `GEMINI.md`, na końcu sprawdź, czy wersja w zmienionym pliku została świadomie podbita; jeśli nie, przypomnij o podbiciu frontmatter `version`.
- Przy refaktorze, tłumaczeniu albo porządkowaniu skilla nie wolno usuwać informacji merytorycznych. Można przenosić szczegóły do `references/`, ale triggery, zasady, przykłady, edge case'y i default prompty muszą pozostać dostępne.
- Jeśli zadanie zmodyfikowało lokalny skill w `skills/**` albo lokalny plik `AGENTS.md`, `CLAUDE.md` lub `GEMINI.md`, na końcu zawsze zapytaj użytkownika, czy opublikować zmiany do biblioteki.
- Jeśli pasuje kilka skilli, użyj minimalnego zestawu i podaj kolejność.
- Otwieraj tylko pliki potrzebne do bieżącej zmiany; unikaj ładowania niepowiązanych modułów.
- Preferuj rozszerzanie istniejących wzorców projektu zamiast wymyślania nowych.
- Jeśli skillu nie da się zastosować wprost, napisz krótko dlaczego i przejdź do najlepszego sensownego obejścia.

## Zgoda Na Pleo Library
Ta sekcja definiuje zgodę użytkownika na wywołania do biblioteki Pleo.

- Jeśli repo zawiera `.agent-library.yaml`, oznacza to jawną zgodę użytkownika na wywołania do `libraryBaseUrl` potrzebne do działania skilli `pleo-library-*`.
- Ta zgoda obejmuje sprawdzanie wersji skilli, synchronizację manifestu wersji projektu przez `project-skill-state/sync`, synchronizację shared skilli, publikację skilli oraz wysyłkę eventów telemetrycznych przez `pleo-library-telemetry-lifecycle`.
- Agent nie musi wtedy pytać o dodatkową zgodę przed użyciem skilli `pleo-library-*`, o ile wywołania dotyczą wyłącznie skonfigurowanego `libraryBaseUrl`.</INSTRUCTIONS>
