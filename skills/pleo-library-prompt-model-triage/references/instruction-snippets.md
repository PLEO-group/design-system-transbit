# Snippety Instrukcji Do Podłączenia Repo

# WERSJA 2.7.8 — zsynchronizowana z SKILL.md 2.7.8

# AUTOR d.kawula@pleodigital.com

`doc_date`: 2026-07-22
`stale_after_days`: `14`

Używaj tego pliku wtedy, gdy repo ma zostać doprowadzone do stanu, w którym `pleo-library-prompt-model-triage` działa jako pierwszy router po obowiązkowym target-only version check, bez kanibalizowania innych skilli i bez raportowania skilli `pleo-library-*` w telemetryce.

## Co musi znaleźć się w instrukcjach repo

We wszystkich trzech plikach:

- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`

trzeba utrzymać ten sam kontrakt:

1. skill `pleo-library-prompt-model-triage` jest wpisany na listę dostępnych skilli
2. `pleo-library-skill-version-guard` wykonuje target-only check skilli użytych w aktualnym procesie
3. guard robi lekki check statusu manifestu, pełny sync tylko dla nieświeżego manifestu, zmiany liczby skilli albo po aktualizacji targetu, a wykryte nieaktualne skille z czystymi katalogami Git aktualizuje automatycznie
4. `pleo-library-prompt-model-triage` wykonuje szybki routing i wskazuje następny potrzebny skill
5. agent inicjuje `execution_gate: continue` dla niskiej niejednoznaczności; Prompt Quality Check nadpisuje bramkę od poziomu `medium`, a `blocked` zatrzymuje wykonanie przed skillem docelowym, tool callami wykonawczymi i edycjami
6. przy brakach zmieniających scope/target, środowisko, oczekiwany rezultat lub typ operacji agent zadaje jedno minimalne pytanie zamiast przyjmować założenia
7. po routingu agent kontynuuje bez pytania przy reasoning `medium` albo niżej tylko wtedy, gdy `execution_gate` ma wartość `continue` albo `continue_with_assumptions`; po `read_only_discovery` najpierw przelicza bramkę
8. jeśli routing wskazuje reasoning powyżej `medium`, agent czeka na jasne potwierdzenie użytkownika przed dalszym odczytem repo, tool callami albo edycjami
9. jasne potwierdzenie oczekującego reasoningu bez nowych wymagań wznawia jedno powiązane zadanie bez ponownego preflightu i routingu; potwierdzenie jest jednorazowe, nie rozszerza scope'u ani uprawnień i nie działa dla `execution_gate: blocked`
10. jawne `bez routingu` albo `skip routing` pomija tylko dobór i prezentację routingu; agent nadal inicjuje i ocenia `execution_gate`, a fraza nie stanowi zgody na zapis ani akcję zewnętrzną
11. skille `pleo-library-*`, w tym `pleo-library-prompt-model-triage` i `pleo-library-shared-skill-sync`, nie są raportowane w telemetryce
12. dla skilla docelowego spoza `pleo-library-*` agent wysyła telemetry `start`, wykonuje pracę i kończy telemetry `finish` albo `interrupt`
13. `pleo-library-shared-skill-sync` odpala się dopiero wtedy, gdy użytkownik albo triage wskazuje potrzebę sprawdzenia lub pobrania shared skilli

## Minimalne reguły do wstawienia

```text
- Przed użyciem `pleo-library-prompt-model-triage` wykonaj target-only check:
  `python skills/pleo-library-skill-version-guard/scripts/run.py check --skill pleo-library-prompt-model-triage`

- `pleo-library-skill-version-guard` sprawdza wskazany skill i status manifestu. Pełny sync robi
  tylko dla nieświeżego manifestu, zmiany liczby skilli albo po aktualizacji targetu, a wykryte
  nieaktualne skille z czystymi katalogami Git aktualizuje automatycznie.
  Lokalne zmiany blokują pull danego skilla.

- Nie raportuj telemetrycznie żadnych skilli `pleo-library-*`, w tym `pleo-library-prompt-model-triage`
  i `pleo-library-shared-skill-sync`.

- `pleo-library-prompt-model-triage` ma wskazać najtańszy sensowny model, poziom reasoning,
  potrzebę narzędzi, `execution_gate` i kolejny skill. Dla niskiej niejednoznaczności inicjuj
  `execution_gate: continue`; routing może zostać pokazany zawsze.
  Dla każdej nowej tury wykonuj routing po preflightcie, chyba że użytkownik jawnie wpisze
  `bez routingu` albo `skip routing`. Wtedy pomiń wyłącznie dobór i prezentację modelu,
  reasoningu, kosztu oraz skilli; nadal zainicjuj i oceń `execution_gate`. Ta fraza nie jest
  zgodą na zapis, akcję zewnętrzną ani blokujące założenie.
  Jeśli brak zmienia scope/target, środowisko, oczekiwany rezultat lub typ operacji, ustaw
  `execution_gate: blocked`, zadaj jedno minimalne pytanie i nie przechodź do wykonania.
  Jeśli bramka nie jest zablokowana i reasoning to `medium` albo niżej, agent kontynuuje
  zadanie bez pytania o potwierdzenie. Jeśli reasoning jest wyższy niż `medium`, agent zatrzymuje się
  po routingu i czeka na jasne potwierdzenie użytkownika, np. `ok`, `tak`, `go`, `start`, `zatwierdzam`.
  Takie potwierdzenie bez nowych wymagań jest jednorazową kontynuacją jednego oczekującego zadania:
  nie uruchamiaj ponownie preflightu ani routingu, tylko wznów pracę z poprzednim wyborem. Nie rozszerza
  ono scope'u ani uprawnień i nie odblokowuje `execution_gate: blocked`. Jeśli wiadomość zmienia scope,
  wykonaj routing jak dla nowej merytorycznej tury.

- Jeśli routing wskazuje `pleo-library-shared-skill-sync`, wykonaj go bez telemetryki.

- Jeśli routing wskazuje skill spoza `pleo-library-*`, wyślij `start`, wysyłaj `progress`
  tylko przy realnej zmianie etapu, a na końcu `finish` albo `interrupt`.

- `pleo-library-skill-version-guard` zaczyna od skilla docelowego użytego w aktualnym procesie,
  a następnie przez manifest aktualizuje pozostałe wykryte nieaktualne skille bez lokalnych zmian.
```

## Opcjonalne sekcje do rozszerzenia

Jeśli repo ma dodatkowe sekcje w instrukcjach, takie jak:

- `Available skills` — dodaj `pleo-library-prompt-model-triage` do listy.
- `Mini Routing` lub `Quick Prompts` — dodaj wzmiankę, że routing działa po obowiązkowym target-only version check.
- `Trigger Rules` — dodaj regułę, że skille `pleo-library-*` nie są raportowane w telemetryce.
- `Skill Versioning` — dopisz, że guard działa target-only dla skilli użytych w aktualnym procesie.

## Uwagi

- Jeśli repo ma własne reguły telemetryczne albo workflow do synchronizacji instrukcji,
  zachowaj je i tylko rozszerz o ten skill.
- Utrzymuj wersję tych snippetów zsynchronizowaną z wersją `SKILL.md`.
  Jeśli `SKILL.md` zmienia kontrakt, zaktualizuj też ten plik i wersję.
- Snippety są kontraktem zachowania, ale w plikach repo można je dopasować stylistycznie,
  o ile nie zmieni się zasada: target-only version guard dla skilli użytych w aktualnym procesie, brak telemetryki dla `pleo-library-*`,
  telemetryka tylko dla skilli docelowych spoza `pleo-library-*`.
