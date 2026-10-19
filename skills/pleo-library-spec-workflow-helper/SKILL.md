---
name: pleo-library-spec-workflow-helper
description: Operacyjnie sprawdza, pobiera i publikuje workflow spec-review w PleoAI/DO Spaces oraz obsługuje kontekst i start prespecki. Używaj wyłącznie przy jawnych operacjach storage, publish, update albo pull dla `docs/sdd/versioning.md`, `specification.md`, `story-<jira>.md` i `affectedSpecifications` oraz przy `prespec-context` lub potwierdzonym `prespec-start`; nie używaj do zwykłego pisania specyfikacji.
version: 2.6.6
author: p.karas@pleodigital.com
scope: SHARED
category: Library
tags: []
---
# Pleo Library Spec Workflow Helper

## Overview

Używaj tego skilla do operacji utrzymaniowych na speckach utrzymywanych w workflow spec-review i archiwizowanych w DO Spaces.
Nie używaj go jako domyślnego skilla do pisania albo analizy specyfikacji; do tego służą skille merytoryczne, a ten helper wchodzi dopiero przy jawnej operacji storage/publish/pull.
Skill obsługuje następujące klasy zadań:

- sprawdzenie, czy lokalne wersje z `docs/sdd/versioning.md` są najnowsze względem wersji zapisanych w storage,
- jednorazowy bootstrap DO Spaces z lokalnych `specification.md` i `task/story-*.md`,
- selektywny upload do archiwum pojedynczego `featureSlug` tylko z `specification.md/spec.md` albo opcjonalnie także ze `story-*.md`,
- pobranie bieżącego pliku workflow po `jiraKey`,
- pobranie konkretnej wersji specki bezpośrednio ze storage po ścieżce,
- publikację lub aktualizację workflow przez `specification.md`, opcjonalny `story-<jira>.md` oraz opcjonalne `affectedSpecifications`,
- pobranie kontekstu taska `[SPEC]` do aktualizacji specyfikacji na podstawie zaakceptowanego story.
- pobranie kontekstu Jira i stanu prespecki przed analizą albo authoringiem,
- uruchomienie nowej rewizji prespecki z walidowanego payloadu pytań albo import zakończonej konwersacji Astrei z odpowiedziami, pytaniami uzupełniającymi i wynikiem rewalidacji.

Centralnym źródłem prawdy do selekcji specyfikacji do pobrania jest faktyczny stan repozytorium specyfikacji w PleoAI dla danego `projectSlug`.
`docs/sdd/versioning.md` pozostaje lokalnym rejestrem wersji i pomocniczym indeksem do porównań wersji już istniejących lokalnie, ale nie może ograniczać listy specyfikacji, które mają zostać pobrane z PleoAI.
Skill od pisania specek ma utrzymywać jednocześnie:

- `# WERSJA` w samym `specification.md`,
- wpis `featureSlug: version` w `docs/sdd/versioning.md`.

Dokument z kontraktem dla Codexa, który ma pisać specki w innym projekcie, znajduje się w:
`docs/codex-spec-authoring-publish-contract.md`

## Zakres API

- `GET /integrations/spec-review/{jiraKey}/current-spec`
- `GET /integrations/spec-review/{jiraKey}/source-spec`
- `GET /integrations/spec-review/{jiraKey}/workflow-files`
- `GET /integrations/spec-review/spec-task/{jiraKey}/context`
- `GET /integrations/prespec/{jiraKey}/context`
- `POST /integrations/prespec/start`
- `POST /integrations/spec-review/publish`
- `PUT /integrations/spec-review/{jiraKey}/current-spec`
- `GET /api/spec-review/storage/tree`
- `GET /api/spec-review/storage/file`
- `POST /api/spec-review/storage/upload`

## Konwencje repo i plików

- Selekcja specyfikacji do pobrania przy aktualizacji projektu działa na podstawie zdalnego repozytorium PleoAI dla `projectSlug`, a nie tylko na podstawie lokalnego `docs/sdd/versioning.md`.
- `docs/sdd/versioning.md` nie jest źródłem prawdy o kompletności zbioru specyfikacji w projekcie.
- Format wpisu w `versioning.md`: `featureSlug: version`.
- `bootstrap-storage` czyta pliki feature’a względem stałego `docs/sdd`, niezależnie od lokalizacji `versioning.md`.
- `projectSlug` helper bierze z argumentu CLI i przekazuje go dalej:
  - jako osobne pole requestu do `publish` i `update`,
  - jako identyfikator projektu w payloadzie `affectedSpecifications`.
- Każdy publikowany dokument, również `--story-file`, musi mieć własny nagłówek `# WERSJA x.y.z`. Wersja story nie aktualizuje wpisu głównej specki w `versioning.md`.
- `Feature slug` w markdownzie nadal jest wymagany do prawidłowego mapowania storage.
- Przy `publish` albo `update` workflow agent musi najpierw spróbować ustalić `jiraKey` z publikowanego `specification.md`, zanim zapyta użytkownika o podanie klucza.
- Źródła `jiraKey` w specyfikacji sprawdzaj w tej kolejności:
  - linia metadanych `Powiązane zgłoszenia: <JIRA-KEY>`,
  - linia metadanych `Powiazane zgloszenia: <JIRA-KEY>`,
  - inne jednoznaczne wystąpienie klucza w formacie `[A-Z][A-Z0-9]+-\d+` w sekcji `Metadane`.
- Jeśli w metadanych jest dokładnie jeden klucz Jira, użyj go w komendzie bez zadawania pytania o `jiraKey`.
- Jeśli w metadanych jest kilka kluczy Jira albo nie ma żadnego, dopiero wtedy zapytaj użytkownika o wybór lub podanie `jiraKey`.
- `affectedSpecifications` to tablica JSON z obiektami:
  - `projectSlug`
  - `featureSlug`
  - opcjonalnie `displayName`
- `affectedSpecifications` nie przyjmuje `expectedVersion`; status uzupełnienia workflow wynika z pojawienia się nowej wersji w archiwum

## CLI

### 1. Status lokalnych wersji vs storage

```bash
python skills/pleo-library-spec-workflow-helper/scripts/run.py status \
  --project-slug skillbox/frontend \
  --versioning-file .\docs\sdd\versioning.md
```

Wynik zawiera:

- listę lokalnych wpisów z `versioning.md`,
- dla każdego feature’a `localPresent` i `localFilePath` ustalone przez fizyczną obecność `specification.md` albo `spec.md` w katalogu obok wskazanego `versioning.md`,
- ich lokalną wersję,
- najnowszą wersję obecną w storage,
- ścieżkę do najnowszej wersji w storage,
- listę `outdatedSpecs`,
- pełną listę `remoteSpecs` odkrytą dla projektu niezależnie od lokalnego indeksu,
- listę `missingLocalSpecs` wraz z `latestRemotePath`,
- łączną listę `specsToPull` obejmującą pozycje nieaktualne i brakujące lokalnie.

### 2. Jednorazowy bootstrap DO Spaces z lokalnych specek

```bash
python skills/pleo-library-spec-workflow-helper/scripts/run.py bootstrap-storage \
  --versioning-file .\docs\sdd\versioning.md \
  --confirm-upload
```

Reguły:

- `projectSlug` domyślnie bierze z `.agent-library.yaml`,
- lokalne katalogi feature’ów helper zawsze czyta z `docs/sdd`,
- dla każdego wpisu `featureSlug: version` helper szuka:
  - `docs/sdd/<featureSlug>/specification.md` albo `spec.md`,
  - wszystkich `story-*.md` pod katalogiem feature,
- helper uploaduje tylko feature’y, których wersja w storage nie istnieje albo jest starsza,
- uploaduje zarówno główną speckę, jak i wszystkie znalezione `story-*.md`.

### 2a. Selektywny upload jednej specki do archiwum

```bash
python skills/pleo-library-spec-workflow-helper/scripts/run.py bootstrap-storage \
  --project-slug skillbox/frontend \
  --feature-slug pwa-dashboard-statistics-for-today-widget \
  --specification-only \
  --expected-version 1.1.0 \
  --confirm-upload
```

Opcjonalnie ze story:

```bash
python skills/pleo-library-spec-workflow-helper/scripts/run.py bootstrap-storage \
  --project-slug skillbox/frontend \
  --feature-slug pwa-dashboard-statistics-for-today-widget \
  --expected-version 1.1.0 \
  --include-stories \
  --confirm-upload
```

Reguły:

- `--feature-slug` ogranicza upload do jednego feature’a,
- w trybie pojedynczego feature’a domyślnie uploadowana jest tylko `specification.md/spec.md`,
- `--include-stories` jawnie dodaje lokalne `story-*.md`,
- `--specification-only` zostawia upload wyłącznie na głównej specce,
- `--expected-version` pozwala pominąć odczyt wersji z `versioning.md`,
- jeśli nie podasz `--expected-version`, helper szuka wersji wskazanego feature’a w `versioning.md`.

### 3. Pobranie aktualnego pliku workflow po Jira

```bash
python skills/pleo-library-spec-workflow-helper/scripts/run.py get \
  --jira-key INPOS-123 \
  --output .\tmp\current-workflow-file.md
```

`get` respektuje dokładnie `--output`: obecność `Feature slug` w pobranym markdownzie nie przenosi pliku do `docs/sdd/**` ani nie podmienia istniejącego `spec.md` lub `specification.md`. Jeśli `--output` wskazuje katalog, helper dopisuje do niego nazwę pobranego pliku. Dodaj `--confirm-local-write` tylko wtedy, gdy wyznaczony cel już istnieje albo sam jawnie wskazuje kanoniczną ścieżkę `docs/sdd/**`.

### 4. Pobranie bieżącego dokumentu i opcjonalnie kontekstu zależności

```bash
python skills/pleo-library-spec-workflow-helper/scripts/run.py workflow-pull \
  --jira-key INPOS-123 \
  --with-affected \
  --confirm-local-write
```

Komenda:

- gdy `documentType` jest obecny, pobiera wyłącznie `currentFile` przez `current-spec`; nie pobiera `sourceFile`, który może być wcześniejszą iteracją tego samego dokumentu, a nie główną specką;
- `SPECIFICATION` zapisuje jako główną speckę (`specification.md` albo istniejący `spec.md`), a `STORY` pod `task/`, niezależnie od roli TESTER;
- tylko dla legacy bez `documentType` stosuje dawny fallback: z TESTEREM pobiera jeden `currentFile` jako główną speckę; bez TESTERA pobiera `sourceFile` i `currentFile`, przy kolizji ścieżek pierwszeństwo ma `current-spec`;
- rozpoznany `Feature slug` wyznacza kanoniczne ścieżki `docs/sdd/<featureSlug>/...`; `--output-dir` pozwala wskazać inny katalog dokumentów workflow;
- z `--with-affected` dla `STORY` (także z TESTEREM) pobiera brakujące lub starsze lokalne główne specki wskazane w `affectedSpecifications` i aktualizuje ich wpisy w `versioning.md`; zapis zależności pozostaje kanoniczny również przy `--output-dir`;
- dla `SPECIFICATION` pomija zależności; bez typu zachowuje legacy fallback według obecności TESTERA;
- nie gwarantuje pełnego kontekstu feature: jeśli głównej specki nie ma lokalnie i nie figuruje w `affectedSpecifications`, ustal jej właściwy projekt, slug i wersję przez `status`, następnie użyj `pull-storage` z konkretną zwróconą ścieżką;
- po pobraniu sprawdź `files`, `affectedSpecifications.updated`, `affectedSpecifications.skipped` i fizyczną obecność potrzebnych dokumentów; pustej listy zależności nie traktuj jako dowodu kompletności kontekstu;
- pozycje z powodem `affected spec belongs to different project: <projectSlug>` raportuj jako pominięte i niesynchronizowane (z `label` i obcym `projectSlug`); wymagają pobrania w kontekście właściwego projektu. Nie przedstawiaj ich jako zsynchronizowanych.

### 5. Pobranie kontekstu taska `[SPEC]`

```bash
python skills/pleo-library-spec-workflow-helper/scripts/run.py spec-task-context \
  --jira-key INPOS-9001
```

Wynik zawiera metadane taska `[SPEC]`, zaakceptowany markdown story oraz aktualny markdown wskazanej specyfikacji głównej.
Używaj tego w trybie `spec-update-from-story` skilla od pisania specyfikacji.

### 6. Pobranie konkretnej wersji specki ze storage

```bash
python skills/pleo-library-spec-workflow-helper/scripts/run.py pull-storage \
  --path specs/SkillBox/payments-ledger/versions/specification-1.2.0.md \
  --output .\docs\sdd\payments-ledger\spec.md \
  --versioning-file .\docs\sdd\versioning.md \
  --confirm-local-write
```

Używaj tego po `status`, gdy użytkownik zgodzi się pobrać nowszą wersję. Przy zapisie dokładnie do `<sdd-root>/<featureSlug>/specification.md` albo istniejącego `spec.md` helper odczytuje `featureSlug` i wersję z `--path`, a następnie aktualizuje lub dopisuje wpis w `--versioning-file` (domyślnie `docs/sdd/versioning.md`). Wynik zwraca `versioningUpdated`, `versioningFile`, `featureSlug` i `specificationVersion`. Przy zapisie do ścieżki tymczasowej helper nie modyfikuje rejestru i zwraca `versioningUpdated=false`.

### 6a. Pobranie kontekstu prespecki

```bash
python skills/pleo-library-spec-workflow-helper/scripts/run.py prespec-context \
  --jira-key INPOS-123
```

Wynik zawiera dane taska i jego parenta oraz stan i Q&A istniejącej prespecki. Komenda jest bezpieczna i służy zarówno `pleo-prespec-grill`, jak i bramce przed authoringiem w `pleo-specification-driven-development`.

### 6b. Uruchomienie prespecki

```bash
python skills/pleo-library-spec-workflow-helper/scripts/run.py prespec-start \
  --jira-key INPOS-123 \
  --project-slug skillbox/frontend \
  --payload-file .\tmp\prespec-inpos-123.json \
  --confirm-start
```

Legacy payload zawiera `questions`, `analysisLimitations` i `analyzedRepositories`. Konwersacyjny flow Astrei najpierw ustawia `astreaConversationManaged: true` i `astreaConversationCompleted: false`, aby utworzyć standardowy root prespecki na kanale speckowym i przepiąć do niego rozmowę. Import zakończonej rozmowy przesyła oba pola jako `true`, a pytania mogą zawierać `finalAnswer`, `answerType`, `parentQuestionId`, `revalidationNote` i `answeredBySlackUserId`. Helper wymaga odpowiedzi dla wszystkich pytań importowanych z Astrei, waliduje relacje pytań uzupełniających, wymaga notatki dla `OUTDATED`, odrzuca dodatkowe pola oraz lokalne ścieżki repozytoriów. `jiraKey`, `projectSlug` i `libraryUserId` dołącza samodzielnie. `prespec-context` domyślnie nie zwraca pytań `OUTDATED`, aby nie trafiały do skilla tworzącego specyfikację; wyłącznie skill prowadzący prespeckę używa `--include-outdated` do audytu wcześniejszych rewizji.

### 7. Publikacja nowego workflow

```bash
python skills/pleo-library-spec-workflow-helper/scripts/run.py publish \
  --jira-key INPOS-123 \
  --project-slug skillbox/frontend \
  --document-type STORY \
  --story-file .\docs\sdd\checkout\task\story-inpos-123.md \
  --affected-specifications-file .\tmp\affected-specifications.json \
  --confirm-publish
```

Wysyłaj dokładnie jeden dokument i jawne `--document-type`:
- story istniejącego feature: `--document-type STORY --story-file .../task/story-<jira>.md`;
- pierwsze story nowego feature, stanowiące główną speckę: `--document-type SPECIFICATION --specification-file .../specification.md`;
- `AS_IS`, główna specyfikacja oraz `[SPEC]`: `--document-type SPECIFICATION --specification-file .../specification.md`.

Historyczny wariant dwóch plików (źródłowa specyfikacja oraz bieżące story, dawniej opisane odwróconymi
etykietami Story/Specyfikacja) nie jest kontraktem zapisu. Helper odrzuca oba pliki przed requestem.
Typ dokumentu jest niezależny od obecności TESTERA; backend utrwala go i używa do wyboru ścieżki w Spaces.

Przed zbudowaniem komendy `publish` ustal typ nowego workflow z jawnego kontekstu skilla authoringowego albo zlecenia:

- tryb `specification`, tryb `spec-update-from-story` albo task Jira `[SPEC]` oznacza workflow z TESTEREM,
- tryb `story` oznacza zwykły workflow,
- jeżeli żaden z tych sygnałów nie jest dostępny lub sygnały są sprzeczne, zapytaj użytkownika o typ workflow przed pokazaniem komendy i przed `--confirm-publish`,
- nie rozpoznawaj typu workflow wyłącznie po tym, które pliki istnieją lokalnie; brak albo obecność `story-<jira>.md` nie jest wystarczającym dowodem.

### 8. Aktualizacja istniejącego workflow

```bash
python skills/pleo-library-spec-workflow-helper/scripts/run.py update \
  --jira-key INPOS-123 \
  --project-slug skillbox/frontend \
  --document-type STORY \
  --story-file .\docs\sdd\checkout\task\story-inpos-123.md \
  --affected-specifications-file .\tmp\affected-specifications.json \
  --confirm-update
```

`update` podmienia dokładnie jeden plik: `specification.md` albo `story-<jira>.md`.
Podaj `--document-type` zgodne z `documentType` istniejącego workflow. Jeśli nie znasz typu,
najpierw odczytaj same metadane — ta komenda wykonuje tylko GET workflow-files, bez pobierania
załączników i bez zapisu lokalnych plików:

```bash
python skills/pleo-library-spec-workflow-helper/scripts/run.py workflow-info --jira-key <JIRA-KEY>
```

Użyj zwróconego `documentType` (`SPECIFICATION` albo `STORY`) w `update`.
Jeśli pole jest puste, nieobecne lub nieznane, nie wykonuj aktualizacji i nie zgaduj typu z nazwy
pliku ani ról reviewerów. Zgłoś niesklasyfikowany workflow i ustal właściwy typ dokumentu
z właścicielem zadania przed jego jawnym sklasyfikowaniem. Nie uruchamiaj `workflow-pull` tylko
po to, żeby poznać typ; służy on do świadomego pobierania plików.
Historyczna opcja wysłania obu plików naraz nie jest już obsługiwana. `AS_IS` używa SPECIFICATION,
a pierwsze story nowego feature ma SPECIFICATION od początku workflow i po zatwierdzeniu
tworzy główną speckę wraz z pierwszą wersją historii. Kolejne story mają STORY.

To służy zarówno do głównej specki i story dla aktywnego taska, jak i do pobocznych specek, jeśli użytkownik aktualizuje ich własny workflow.

## Workflow agenta

1. Ustal, czy użytkownik chce:
   - sprawdzić aktualność specek,
   - zrobić jednorazowy bootstrap DO Spaces,
   - pobrać nową wersję,
   - pobrać bieżący dokument workflow i opcjonalnie główne specki stanowiące kontekst,
   - pobrać kontekst taska `[SPEC]` przez `spec-task-context`,
   - pobrać kontekst prespecki przez `prespec-context`, opcjonalnie z `--include-outdated` dla audytu prowadzonego przez skill prespecki,
   - uruchomić albo wznowić prespeckę przez `prespec-start`,
   - opublikować nowy workflow,
   - zaktualizować istniejący workflow.
2. Dla pytań typu "czy wszystkie specki są najnowsze" albo "pobierz / zaktualizuj specyfikacje dla projektu" traktuj repozytorium PleoAI dla danego `projectSlug` jako źródło prawdy o pełnej liście dostępnych specyfikacji.
3. Przy ogólnej aktualizacji specyfikacji bez wskazania konkretnego `featureSlug`:
   - sprawdź zdalny stan repozytorium specyfikacji w PleoAI dla projektu,
   - pobierz wszystkie dostępne zdalnie specyfikacje dla tego projektu, które są nowsze od lokalnych albo nie istnieją lokalnie,
   - nie ograniczaj listy pobrań do wpisów już obecnych w `docs/sdd/versioning.md`.
4. Jeśli użytkownik prosi o aktualizację konkretnej specyfikacji, ogranicz zakres tylko do tej wskazanej pozycji.
5. Jeśli dana specyfikacja istnieje w repozytorium PleoAI, ale nie istnieje lokalnie, pobierz ją do kanonicznej ścieżki `docs/sdd/<featureSlug>/...` i dopisz odpowiedni wpis do `docs/sdd/versioning.md`.
6. Dla pytań typu "czy wszystkie specki są najnowsze" uruchom `status`, ale interpretuj wynik razem ze zdalną listą dostępnych specyfikacji dla projektu.
7. Dla jednorazowego zasiania storage albo selektywnego uploadu do archiwum uruchom `bootstrap-storage` dopiero po jawnej zgodzie użytkownika.
8. Jeśli zdalny stan projektu pokaże nowsze lub brakujące lokalnie specyfikacje, wypisz użytkownikowi różnice tylko wtedy, gdy pytanie dotyczy audytu stanu; przy poleceniu aktualizacji pobierz je bez dodatkowej selekcji, chyba że użytkownik zawęził zakres do konkretnej specyfikacji.
9. Po zgodzie użyj `pull-storage` dla konkretnych ścieżek `latestRemotePath` i zapisz każdą speckę do jej kanonicznego `specification.md` albo `spec.md`; sprawdź w wyniku `versioningUpdated=true`, aby potwierdzić, że odpowiadający wpis w `versioning.md` został zaktualizowany razem z plikiem.
10. Po każdym pobraniu albo aktualizacji lokalnych plików specyfikacji uznaj wcześniej zaczytaną w czacie treść tych specyfikacji oraz `docs/sdd/versioning.md` za nieaktualną.
11. Jeśli dalsza praca zależy od pobranych lub zaktualizowanych specyfikacji, odczytaj je ponownie z dysku i kontynuuj wyłącznie na świeżo pobranej treści.
12. Dla `publish` albo `update` najpierw ustal `jiraKey` z metadanych publikowanej specyfikacji; jeśli jest jednoznaczny, użyj go bez pytania o klucz, a pytaj tylko o brakujący albo wieloznaczny `jiraKey`.
13. Przed `publish` ustal typ nowego workflow z jawnego trybu authoringu lub taska `[SPEC]`; jeżeli typ nie jest jednoznaczny, zapytaj użytkownika i nie przygotowuj finalnego payloadu przez zgadywanie na podstawie dostępnych plików.
14. Jeśli aktualizacja dotyczy zależności workflow, przekaż plik `affectedSpecifications` razem z plikami aktualizowanymi w danym wywołaniu.
15. Nie łącz automatycznie pobrania lokalnego pliku z publikacją do workflow bez osobnej zgody użytkownika.
16. Przed `prespec-start` pokaż użytkownikowi podgląd pytań i wykonaj komendę dopiero po jednoznacznym potwierdzeniu.
17. Po `prespec-context` interpretuj status zgodnie ze skillem wywołującym; helper nie podejmuje decyzji biznesowych ani nie generuje pytań.
18. Po `workflow-pull --with-affected` przejrzyj `affectedSpecifications.skipped`. Pozycje pominięte z powodu innego `projectSlug` wypisz w wyniku jako niesynchronizowane i wymagające osobnej synchronizacji w ich projekcie; nie przedstawiaj operacji jako pełnej synchronizacji wszystkich zależności.

## Zasady użycia

- `status` jest bezpieczny i może być uruchamiany bez dodatkowej zgody.
- `bootstrap-storage` wymaga `--confirm-upload`.
- `--expected-version` działa tylko razem z `--feature-slug`.
- `--specification-only` i `--include-stories` działają tylko razem z `--feature-slug`.
- `pull-storage` wymaga `--confirm-local-write`, jeśli ma nadpisać istniejący plik albo wejść w katalog wskazanego `--versioning-file`. Kanoniczny zapis jest dozwolony wyłącznie do `<sdd-root>/<featureSlug>/specification.md` albo `spec.md` zgodnego z `--path` i automatycznie aktualizuje rejestr; zapis tymczasowy nie zmienia `versioning.md`.
- `get` zawsze respektuje jawne `--output` i nigdy nie relokuje pliku na podstawie `Feature slug`. Wymaga `--confirm-local-write`, gdy wyznaczony cel już istnieje albo użytkownik sam wskazał kanoniczną ścieżkę `docs/sdd/**`; flaga jest opcjonalna przy zapisie nowego pliku do jawnie wskazanej, niekanonicznej ścieżki tymczasowej.
- `workflow-pull` wymaga `--confirm-local-write`, gdy co najmniej jeden wynik ma nadpisać istniejący plik albo zostać zapisany w kanonicznej ścieżce `docs/sdd/**`. Dotyczy to domyślnego zapisu bez `--output-dir` po rozpoznaniu `featureSlug` oraz plików aktualizowanych przez `--with-affected`. Flaga jest opcjonalna wyłącznie wtedy, gdy wszystkie pliki trafią jako nowe do jawnie wskazanego, niekanonicznego `--output-dir` i nie nastąpi kanoniczny zapis zależności.
- `publish` wymaga `--confirm-publish`.
- `update` wymaga `--confirm-update`.
- `prespec-start` wymaga `--confirm-start`.
- `prespec-context` nie modyfikuje stanu i nie wymaga potwierdzenia.
- `publish` i `update` odrzucają każdy przekazany plik bez `# WERSJA`, zarówno `--specification-file`, jak i `--story-file`.
- `affectedSpecifications` przekazuj tylko jako poprawny JSON array bez `expectedVersion`.
- Nie loguj sekretów ani pełnych wartości auth.

## Autoryzacja

Skrypt obsługuje trzy tryby:

- brak auth, jeśli endpoint jest publiczny,
- bearer token przez `--bearer-token` albo `PLEO_SPEC_WORKFLOW_BEARER_TOKEN`,
- basic auth przez `--basic-user` i `--basic-password` albo env `PLEO_SPEC_WORKFLOW_BASIC_USER` / `PLEO_SPEC_WORKFLOW_BASIC_PASSWORD`.

Bazowy URL zawsze pochodzi z `libraryBaseUrl` w `.agent-library.yaml`.

## Zasoby

- `scripts/run.py`
- `agents/openai.yaml`
- `agents/claude.yaml`
- `agents/gemini.yaml`
- `docs/codex-spec-authoring-publish-contract.md`

## Kontrola jakości

- `status` czyta `docs/sdd/versioning.md` i waliduje format `featureSlug: version`.
- `status` nie traktuje wpisu w `versioning.md` jako dowodu obecności specyfikacji: sprawdza fizyczny plik `<sdd-root>/<featureSlug>/specification.md` albo `spec.md`; brak pliku ustawia `localPresent=false` i, jeśli istnieje wersja zdalna, dodaje pozycję do `missingLocalSpecs` oraz `specsToPull` nawet przy zgodnej wersji w rejestrze.
- Przy aktualizacji projektu selekcja do pobrania wynika ze zdalnego repozytorium PleoAI dla `projectSlug`, a nie z samej lokalnej listy w `docs/sdd/versioning.md`.
- Jeśli zdalna specyfikacja istnieje dla projektu, a lokalnie brakuje katalogu lub wpisu w `versioning.md`, skill traktuje ją jako pozycję do pobrania.
- Po pobraniu lub aktualizacji lokalnych specek i `docs/sdd/versioning.md` dalsze decyzje muszą opierać się na ponownie odczytanej treści z dysku, a nie na starszym kontekście czatu.
- `bootstrap-storage` w trybie pełnym uploaduje `specification.md/spec.md` i wszystkie lokalne `story-*.md` dla feature’a.
- `bootstrap-storage --feature-slug` pozwala zarchiwizować jedną wybraną speckę bez tymczasowego `versioning.md`.
- `bootstrap-storage --feature-slug --expected-version` działa nawet wtedy, gdy wskazany `featureSlug` nie jest obecny w `versioning.md`.
- `bootstrap-storage --feature-slug` rozwiązuje pliki względem stałego `docs/sdd`, a nie względem lokalizacji `versioning.md`.
- `bootstrap-storage` pomija feature’y, których wersja w storage jest taka sama albo nowsza.
- `status` zwraca `latestRemotePath`, jeśli w storage istnieje nowsza wersja.
- `status` zwraca wszystkie zdalne pozycje w `remoteSpecs`, brakujące lokalnie w `missingLocalSpecs` oraz kompletną kolejkę aktualizacji w `specsToPull`.
- `pull-storage` pobiera dokładnie jeden plik ze storage i zwraca końcową ścieżkę lokalną; przy kanonicznym zapisie aktualizuje wpis `featureSlug: version` w `versioning.md`, a `versioningUpdated=true` potwierdza spójność pliku z rejestrem.
- `publish` wysyła `projectSlug`, jawne `documentType`, dokładnie jeden z `specificationFile` / `storyFile` i opcjonalnie `affectedSpecifications`.
- Przed `publish` typ workflow jest potwierdzony przez jawny tryb `story` / `specification` / `spec-update-from-story`, task `[SPEC]` albo odpowiedź użytkownika; dostępność lokalnych plików nie zastępuje tej decyzji.
- `update` wysyła `projectSlug`, jawne `documentType`, dokładnie jeden z `specificationFile` / `storyFile` oraz opcjonalnie `affectedSpecifications`.
- `get` pobiera aktualny plik workflow wskazany przez backend dla danego `jiraKey` dokładnie pod `--output`; `Feature slug` nie może zmienić ścieżki docelowej ani spowodować niejawnego zapisu do głównej specyfikacji.
- `workflow-pull` dla jawnego `documentType` pobiera tylko `currentFile`. Główne specki do kontekstu STORY pobiera osobno przez `--with-affected`; zakres i fallback legacy opisuje sekcja CLI 4.
- Dla nowego workflow `workflow-pull` kieruje się `documentType`: pobiera tylko currentFile, SPECIFICATION zapisuje jako główną speckę, a STORY w task/, także przy reviewerze TESTER. Pierwsze story nowego feature ma SPECIFICATION i wraca do głównej ścieżki specification.md. Dla starszego workflow bez typu zachowuje zgodność: workflow z TESTEREM nie wymaga `sourceFile`, nie wywołuje `source-spec` i mapuje `currentFile` na główną specyfikację feature’a zamiast do katalogu `task`; przy kolizji ścieżek w zwykłym workflow pierwszeństwo ma `current-spec`.
- `workflow-pull --with-affected` pozostawia zależności z innych projektów w `affectedSpecifications.skipped`; agent raportuje je jako pominięte i niesynchronizowane, nigdy jako część zakończonej synchronizacji.
- `publish` i `update` kończą się błędem bez odpowiedniego flag-confirm.
- Skrypt nie próbuje publikować bez jawnej decyzji użytkownika.

### Obecność lokalnej zależności

`workflow-pull --with-affected` pomija aktualną zależność tylko wtedy, gdy istnieje fizyczny
plik `specification.md` lub `spec.md` i wpis w `versioning.md` ma co najmniej wersję archiwalną.
Jeżeli pliku nie ma, pobiera najnowszą dostępną wersję archiwalną i zapisuje jej rzeczywisty numer
w rejestrze (również gdy poprzedni wpis wskazywał wyższą, nieobecną lokalnie wersję).
Zapis nadal wymaga `--confirm-local-write`; zależności innych projektów pozostają pominięte.

### Ponowienie archiwizacji zatwierdzonego workflow legacy

Po wdrożeniu backendu obsługującego retry APPROVED nie używaj `publish` do naprawy błędu
brakującego documentType. Odczytaj `workflow-info`, potwierdź status APPROVED, projekt i rolę
dokumentu z jego treści oraz kontekstu zadania. Nie zgaduj typu z nazwy pliku lub reviewerów.
Pobierz `get --jira-key <JIRA> --output <TEMP_FILE>` i zachowaj dokładne bajty pliku.
Następnie użyj `update --jira-key <JIRA> --project-slug <PROJECT> --document-type <TYPE>
--specification-file <TEMP_FILE> --confirm-update` (dla pliku story można użyć --story-file).
Nie podawaj affected-specifications-file. Ta operacja klasyfikuje nieznany dokument i ponawia
archiwizację; nie podmienia pliku, nie zmienia hasha ani akceptacji i nie tworzy nowego review.
Backend odrzuca zmienioną treść, projekt oraz zmianę już zapisanego typu. Konflikt historii
nadal blokuje zapis i wymaga osobnego wyjaśnienia. Po sukcesie sprawdź workflow-info i storage.
Jeśli istnieje aktywny workflow o tym samym kluczu, nie używaj tego sposobu do naprawy starszego
review — update wybiera aktywny workflow.
