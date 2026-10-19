# Prompt Model Triage — EXTENDED (Full Mode)

# WERSJA 2.7.8 — zsynchronizowana z SKILL.md 2.7.8

**Ładuj ten plik TYLKO gdy routing wymaga Full Mode** (co najmniej jeden warunek pre-checku z SKILL.md nie jest spełniony). Nie ładuj go dla Lightweight Mode.

---

## Szybki Workflow — Full Mode

1. Rozpoznaj runtime i providera (reguły w SKILL.md CORE).
2. Wczytaj odpowiedni plik provider-specific z `references/`.
3. Zastosuj Freshness Policy (reguły w SKILL.md CORE).
4. Odrzuć modele i reasoning levels niedostępne w runtime.
5. **Oceń prompt w czterech osiach** (sekcja niżej).
6. Ustaw domyślnie `execution_gate: continue`; pozostaw tę wartość dla niejednoznaczności `low`. **Jeśli niejednoznaczność ≥ `medium`:** uruchom Prompt Quality Check i nadpisz bramkę jego wynikiem.
7. Wybierz najniższy sensowny tier modelu.
8. Dobierz najniższy sensowny poziom reasoning.
9. Określ `billing_surface`: `api-metered`, `subscription`, `credits` albo `unknown`.
10. Wygeneruj realistyczny Cost Estimate odpowiedni do billing surface.
11. Oceń pewność rekomendacji.
12. Zasygnalizuj decyzję blokiem routingu (format niżej); routing można pokazać także przy `execution_gate: blocked`.
13. Wskaż kolejny skill albo decyzję o kontynuacji bez dodatkowego skilla.
14. Jeśli `execution_gate: blocked`, zadaj jedno zwięzłe pytanie o minimalny zestaw brakujących decyzji i zatrzymaj się przed skillem docelowym, wykonawczymi tool callami oraz edycjami.
15. Jeśli `execution_gate: read_only_discovery`, wykonaj wyłącznie ograniczony odczyt zasobów już wskazanych przez użytkownika; po nim przelicz bramkę.
16. Jeśli bramka ma wartość `continue` albo `continue_with_assumptions` i reasoning to `medium` albo niżej, kontynuuj workflow bez pytania o potwierdzenie.
17. Jeśli bramka ma wartość `continue` albo `continue_with_assumptions`, ale reasoning jest wyższy niż `medium`, zatrzymaj się po routingu i czekaj na jasne potwierdzenie użytkownika, np. `ok`, `tak`, `go`, `start`, `zatwierdzam`.
18. Powiąż oczekiwane potwierdzenie z jednym konkretnym zadaniem i routingiem. Jasne potwierdzenie bez nowych wymagań zużyj jednorazowo: nie uruchamiaj ponownie preflightu ani routingu, tylko wznów oczekujące zadanie. Jeśli wiadomość zmienia scope lub jest niejednoznaczna, potraktuj ją jako nową merytoryczną turę.
19. Jeśli runtime wymaga ręcznej zmiany modelu/reasoningu, połącz prośbę o zmianę z tą samą bramką potwierdzenia.

---

## Cztery Osie Oceny Promptu

Oceń prompt w czterech osiach. Każda ma twarde kryteria graniczne — nie oceniaj intuicyjnie.

### 1. Złożoność

Mierzy ile kroków rozumowania, zależności i dziedzin wiedzy angażuje zadanie.

| Poziom   | Kryteria                                                                                                            |
| -------- | ------------------------------------------------------------------------------------------------------------------- |
| `low`    | Jedno pytanie, jedna odpowiedź, zero zależności kontekstowych. Przykład: tłumaczenie zdania, formatowanie kodu.     |
| `medium` | 2–4 kroki logiczne lub zależności między modułami/plikami. Przykład: dodanie feature do istniejącego serwisu.       |
| `high`   | 5+ kroków, wiele plików, cross-domain (np. backend + infra + security), brak jednej oczywistej ścieżki rozwiązania. |

### 2. Koszt Pomyłki

Mierzy konsekwencje błędnej odpowiedzi agenta.

| Poziom   | Kryteria                                                                                                                                 |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `low`    | Środowisko lokalne, brak danych produkcyjnych, łatwy rollback, zero wpływu na innych użytkowników.                                       |
| `medium` | Staging, dane testowe z prawdziwą strukturą, błąd wymaga review ale nie powoduje incydentu.                                              |
| `high`   | Produkcja, dane wrażliwe / PII, brak automatycznego rollbacku, błąd może spowodować downtime, utratę danych lub incydent bezpieczeństwa. |

### 3. Niejednoznaczność Promptu

Mierzy ile założeń agent musi przyjąć bez jawnej informacji od użytkownika.

| Poziom   | Kryteria                                                                                       |
| -------- | ---------------------------------------------------------------------------------------------- |
| `low`    | Wszystkie parametry podane: scope, oczekiwany output, kontekst, środowisko. Zero domysłów.     |
| `medium` | 1–2 brakujące parametry, ale dają się rozsądnie wnioskować z kontekstu lub konwencji projektu. |
| `high`   | 3+ brakujące parametry lub sprzeczne wymagania albo cel zadania nie jest jednoznaczny.         |

**Jeśli niejednoznaczność = `high`:** Przed routingiem wygeneruj listę brakujących informacji (patrz: Prompt Quality Check), ustaw `execution_gate: blocked` i zasugeruj jak poprawić prompt.

### 4. Zakres Pracy

Mierzy jakie operacje musi wykonać agent.

| Poziom            | Kryteria                                                                 |
| ----------------- | ------------------------------------------------------------------------ |
| `answer-only`     | Tylko odpowiedź tekstowa, zero operacji na plikach i narzędziach.        |
| `tools-read`      | Odczyt plików, search, lookup — brak zapisu ani zmian.                   |
| `multi-file-edit` | Zapis lub modyfikacja 1+ plików, możliwe uruchomienie testów.            |
| `research`        | Wymaga browse, zewnętrznych źródeł albo agregacji danych z wielu miejsc. |

---

## Prompt Quality Check

Uruchom gdy niejednoznaczność = `medium` lub `high`.

**Sprawdź, czy prompt zawiera:**

- [ ] Jasny cel (co ma być efektem końcowym?)
- [ ] Scope (jakie pliki / moduły / systemy?)
- [ ] Środowisko (local / staging / prod?)
- [ ] Oczekiwany format output (kod / opis / plan?)
- [ ] Ograniczenia (co jest poza scope?)

**Dla każdego brakującego elementu** wygeneruj krótką sugestię.

Następnie sklasyfikuj braki według wpływu na wykonanie:

- `non_blocking` — preferencja z jednym bezpiecznym, odwracalnym defaultem; agent może ją jawnie założyć.
- `resolvable_read_only` — brak można rozstrzygnąć ograniczonym odczytem zasobów już wskazanych przez użytkownika.
- `blocking` — brak może zmienić target/scope, środowisko, oczekiwany rezultat lub typ operacji, uprawnienia, bezpieczeństwo, koszt albo nieodwracalny skutek.

Ustaw bramkę:

- niejednoznaczność `low`, bez uruchamiania Prompt Quality Check → zachowaj domyślne `continue`,
- wyłącznie `non_blocking` → `continue_with_assumptions`,
- co najmniej jeden `resolvable_read_only`, ale zero `blocking` → `read_only_discovery`,
- co najmniej jeden `blocking` albo niejednoznaczność `high` → `blocked`.

Brak scope/modułu, środowiska, oczekiwanego outputu lub zgody na zapis/akcję zewnętrzną uznaj za `blocking`, jeśli istnieje więcej niż jedna istotnie różna interpretacja. Nie obniżaj tej klasyfikacji tylko dlatego, że reasoning wynosi `medium` albo niżej.

**Format (tylko gdy niejednoznaczność ≥ `medium`):**

```
⚠️ Prompt quality: medium/high ambiguity

Brakuje:
- [element 1] — wpływ: <non_blocking|resolvable_read_only|blocking> — sugestia: "..."
- [element 2] — wpływ: <non_blocking|resolvable_read_only|blocking> — sugestia: "..."

Execution gate: <continue_with_assumptions|read_only_discovery|blocked>
Założenia: <lista albo "brak">
```

Nie blokuj wyświetlenia routingu. Przy `execution_gate: blocked` zablokuj wykonanie i poproś o minimalne rozstrzygnięcie.

---

## Realistyczny Cost Estimate

### Składniki kosztu

| Warstwa              | Co obejmuje                                                        | Dlaczego ważna                                                                                               |
| -------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| **Input tokens**     | System prompt, kontekst konwersacji, pliki w kontekście, narzędzia | Zwykle 40–70% całkowitego kosztu. Rośnie z tool use i dłuższą konwersacją.                                   |
| **Reasoning tokens** | Wewnętrzne myślenie modelu (extended thinking, chain-of-thought)   | Przy `high`/`xhigh`/`max` może stanowić 50–80% tokenów output. Nie widać ich w odpowiedzi, ale są naliczane. |
| **Output tokens**    | Faktyczna odpowiedź widoczna dla użytkownika                       | Zwykle najdroższa stawka za token, ale najniższy wolumen.                                                    |

Reasoning/thinking jest zwykle rozliczany stawką output. W estymacji możesz rozdzielić hidden reasoning i widoczny output, ale muszą to być części rozłączne. Jeśli provider raportuje reasoning wewnątrz `output_tokens`, nie dodawaj ponownie całego `output_tokens`.

### Billing Surface

| Surface        | Jak raportować koszt                                                                 |
| -------------- | ------------------------------------------------------------------------------------ |
| `api-metered`  | Bezpośredni koszt w centach na podstawie publicznego cennika API.                    |
| `subscription` | Poziom kosztu/zużycia; centy tylko jako jawnie nazwany `API-equivalent`.             |
| `credits`      | Poziom kosztu i wpływ na kredyty; nie przeliczaj na centy bez cennika runtime.       |
| `unknown`      | Poziom jakościowy i niższa pewność; nie zgaduj bezpośredniego kosztu użytkownika.    |

### Format Dla `api-metered`

```
💰 Cost estimate:
   Billing:   api-metered
   Input:     ~<zakres> tok. (<zakres>¢)
   Reasoning: ~<zakres> tok. (<zakres>¢)    [tylko jeśli reasoning > low]
   Output:    ~<zakres> tok. (<zakres>¢)
   TOTAL:     ~<zakres>¢ – <zakres>¢  (±50%)
   Token budget: <XS|S|M|L|XL>
```

### Format Dla Pozostałych Surface

```
💰 Cost estimate:
   Billing: <subscription|credits|unknown>
   Poziom zużycia: <niski|średni|wysoki>
   API-equivalent: ~<zakres>¢ (opcjonalnie, nie jest kosztem tej sesji)
   Token budget: <XS|S|M|L|XL>
```

### Skala Token Budget

| Symbol | Przybliżony TOTAL (input+reasoning+output) | Kiedy                                                  |
| ------ | ------------------------------------------ | ------------------------------------------------------ |
| `XS`   | ~500–2 000 tok.                            | Krótka odpowiedź, tłumaczenie, klasyfikacja            |
| `S`    | ~2 000–8 000 tok.                          | Jeden plik, dodanie funkcji, krótki test               |
| `M`    | ~8 000–25 000 tok.                         | Kilka plików, review, refaktor modułu                  |
| `L`    | ~25 000–80 000 tok.                        | Wiele plików, migracja, architektura                   |
| `XL`   | ~80 000+ tok.                              | Pełna analiza systemu, root cause z logami, multi-tool |

### Orientacyjne stawki providerów

Używaj tych stawek jako przybliżenia. Dokładniejsze ceny w plikach provider-specific z `references/`.

| Provider  | Model                    | Input $/1M | Output $/1M | Reasoning/thinking |
| --------- | ------------------------ | ---------- | ----------- | ------------------ |
| OpenAI    | gpt-5.6-sol              | $4.00      | $20.00      | stawka output      |
| OpenAI    | gpt-5.6-terra            | $2.00      | $12.00      | stawka output      |
| OpenAI    | gpt-5.6-luna             | $0.20      | $1.20       | stawka output      |
| Anthropic | claude-fable-5           | $10.00     | $50.00      | stawka output      |
| Anthropic | claude-opus-5            | $5.00      | $25.00      | stawka output      |
| Anthropic | claude-sonnet-5          | $2.00      | $10.00      | stawka output      |
| Anthropic | claude-haiku-4-5         | $1.00      | $5.00       | stawka output      |
| Google    | gemini-3.7-flash*        | $0.75      | $3.75       | zawarte w output   |
| Google    | gemini-3.5-flash-lite    | $0.30      | $2.50       | zawarte w output   |
| Google    | gemini-3.1-pro-preview <=200k** | $2.00 | $12.00 | zawarte w output |
| Google    | gemini-3.1-pro-preview >200k**  | $4.00 | $18.00 | zawarte w output |

`*` Cena promocyjna Gemini 3.7 Flash obowiązuje do 2026-12-31; od 2027-01-01 wynosi $1.50/$7.50. `**` Cena Gemini 3.1 Pro Preview dotyczy promptów do 200k; powyżej: $4/$18. Cena Sonnet 5 $2/$10 jest standardowa — zapowiadana podwyżka została anulowana.

Dla GPT-5.6 prompt powyżej 272k input tokens ma mnożnik `2×` input i `1.5×` output dla całej prośby.

**⚠️ Stawki są publicznymi cenami API na stan `doc_date` pliku referencyjnego.** Nie są kosztem abonamentu ani sesji IDE. Przy aktualizacji modeli zaktualizuj też ceny, daty promocji i YAML-e agentów.

### Zasady szacowania

- **Input tokens:** System prompt ~1000–3000 tok. + kontekst + ~500–2000 tok. per plik przy tool use.
- **Reasoning tokens:** `low` → ~0–500 tok. | `medium` → ~500–3000 tok. | `high` → ~3000–10000 tok. | `xhigh`/`max` → ~10000–30000+ tok.
- **Output tokens:** Na podstawie oczekiwanej długości odpowiedzi.
- **Centy:** Tokeny × stawka. Zakres (min–max), nie jedna liczba.
- **Margines błędu:** Modele LLM mogą popełniać błędy arytmetyczne. Każdy szacunek centowy to przybliżenie **±50%**. Przy kwotach > $1 zaznacz to jawnie.
- Jeśli reasoning = `xhigh`/`max`: dopisz `(długi reasoning — spodziewaj się górnej granicy)`

---

## Pewność Rekomendacji

| Poziom   | Kryteria                                                                                                                                                           |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `high`   | WSZYSTKIE spełnione: (1) model i reasoning oczywiste, (2) znany runtime z potwierdzonym pickerem, (3) niejednoznaczność = `low`, (4) referencja świeża (< 14 dni), (5) billing surface znany, jeśli podajesz kwotę. |
| `medium` | CO NAJMNIEJ JEDNO: (1) 2+ sensownych opcji — wybrano najtańszą, (2) niejednoznaczność = `medium`, (3) runtime znany ale picker niepotwierdzony.                    |
| `low`    | CO NAJMNIEJ JEDNO: (1) nieznany model w runtime, (2) referencja > 14 dni, (3) niejednoznaczność = `high`, (4) brak info o modelach, (5) nieznany billing przy kwocie. |

---

## Format Odpowiedzi — Full Mode

```
[opcjonalnie — gdy niejednoznaczność ≥ medium]
⚠️ Prompt quality: <level> ambiguity
Brakuje:
- [element] — wpływ: <non_blocking|resolvable_read_only|blocking> — sugestia: "..."
Execution gate: <continue_with_assumptions|read_only_discovery|blocked>
Założenia: <lista albo "brak">

[obowiązkowo]
Routing: <model> | reasoning <level> | tier <cheap|balanced|deep|max> | koszt pomyłki <low|medium|high> | pewność <low|medium|high>
Powód: <1–2 zdania>

💰 Cost estimate:
   Billing: <api-metered|subscription|credits|unknown>
   <użyj odpowiedniego formatu z sekcji Billing Surface; nie pokazuj centów jako kosztu sesji poza api-metered>

[opcjonalnie — warunek eskalacji]
Escalate if: <krótki opis>

[obowiązkowo]
Następny krok: <skill docelowy albo "kontynuuj bez dodatkowego skilla">

[obowiązkowo przy execution_gate: blocked]
Pytanie blokujące: <jedno zwięzłe pytanie obejmujące minimalny zestaw decyzji>

[obowiązkowo tylko gdy execution_gate = continue|continue_with_assumptions i reasoning > medium]
Wymagane potwierdzenie: reasoning <level> jest powyżej `medium`. Odpisz `ok` albo innym jasnym potwierdzeniem, żebym kontynuował.

[opcjonalnie — referencja > 10 dni]
💡 Jeśli masz do wyboru inne modele/reasoningi niż zaproponowane, wpisz `sprawdź najnowsze modele i zaktualizuj skilla` — zaktualizuję referencje.
```

---

## Przykłady — Full Mode

### Przykład 1 — Średnia złożoność, niska niejednoznaczność

**Runtime:** Claude API (`api-metered`)

**Prompt:** `"Dopisz testy do tego Angular service i uruchom najwęższy sensowny zakres"`

```
Routing: claude-sonnet-5 | reasoning medium | tier balanced | koszt pomyłki medium | pewność high
Powód: Wymaga analizy serwisu, napisania testów i uruchomienia — kilka plików, ale jasny cel.

💰 Cost estimate:
   Billing:   api-metered
   Input:     ~4 000 tok. (0.8¢)
   Reasoning: ~2 000 tok. (2.0¢)
   Output:    ~1 500 tok. (1.5¢)
   TOTAL:     ~4¢ – 7¢  (±50%)
   Token budget: M

Następny krok: `angular-unit-testing`, potem najwęższy sensowny zakres testów.
```

---

### Przykład 2 — Wysoka niejednoznaczność z Quality Check

**Runtime:** nieznany

**Prompt:** `"Popraw performance"`

```
⚠️ Prompt quality: high ambiguity
Brakuje:
- Scope — wpływ: blocking — sugestia: "jakiego modułu / serwisu / endpointu dotyczy?"
- Środowisko — wpływ: blocking — sugestia: "local profile, staging, produkcja?"
- Metryki — wpływ: blocking — sugestia: "co mierzyć? czas odpowiedzi, zużycie CPU, memory?"
- Oczekiwany output — wpływ: blocking — sugestia: "patch / plan działania / raport?"
Execution gate: blocked
Założenia: brak

Routing: tier deep | reasoning high | koszt pomyłki high | pewność low
Powód: Bez runtime, scope i metryk zadanie jest otwarte; rekomendacja pozostaje na poziomie tieru, a uzupełnienie promptu zmniejszy koszt i ryzyko.

💰 Cost estimate:
   Billing: unknown
   Poziom zużycia: wysoki
   Token budget: L

Escalate if: analiza wyjdzie poza wskazany moduł lub wymagane będzie profilowanie produkcji.

Następny krok: poczekaj na rozstrzygnięcie scope, środowiska, metryki i rodzaju rezultatu; nie uruchamiaj skilla docelowego ani odczytu repo.
Pytanie blokujące: Który moduł i środowisko mam analizować, jaką metrykę poprawić oraz czy oczekujesz patcha, planu czy raportu?
```

---

### Przykład 3 — Root cause, wysoki koszt pomyłki

**Runtime:** Claude API (`api-metered`)

**Środowisko:** produkcja

**Prompt:** `"Znajdź root cause memory leaku po migracji i zaproponuj bezpieczny plan naprawczy"`

```
Routing: claude-fable-5 | reasoning max | tier max | koszt pomyłki high | pewność high
Powód: Root cause analysis + plan naprawczy na produkcji = najwyższy koszt pomyłki, wymagany max reasoning.

💰 Cost estimate:
   Billing:   api-metered
   Input:     ~10 000 tok. (10.0¢)
   Reasoning: ~25 000 tok. (125.0¢)
   Output:    ~5 000 tok. (25.0¢)
   TOTAL:     ~160¢ – 240¢ / $1.60 – $2.40  (±50%)
   Token budget: XL
   (długi reasoning — spodziewaj się górnej granicy)

Escalate if: analiza wymaga logów produkcyjnych lub zewnętrznego profilowania.

Następny krok: po potwierdzeniu odczyt repo/logów wskazanych przez użytkownika i plan diagnostyczny.
Wymagane potwierdzenie: reasoning `max` jest powyżej `medium`. Odpisz `ok` albo innym jasnym potwierdzeniem, żebym kontynuował.
```

Jeśli następna wiadomość użytkownika brzmi wyłącznie `ok`, nie generuj nowego routingu ani kolejnej prośby o potwierdzenie. Zużyj potwierdzenie i rozpocznij oczekującą analizę root cause. Wiadomość `ok, ale zrób też deploy na produkcję` zmienia scope i wymaga nowego routingu oraz osobnej oceny uprawnień.

---

### Przykład 4 — Nieznany runtime

**Prompt:** (w nieznanym środowisku) `"Zrefaktoruj ten moduł auth na strategy pattern"`

```
Routing: tier deep | reasoning high | koszt pomyłki medium | pewność low
Powód: Refaktor wymaga analizy kilku plików i zmiany architektury. Nie znam Twojego runtime — dobierz model z tieru deep (np. gpt-5.6-sol, claude-sonnet-5 + high, gemini-3.7-flash + high).

💰 Cost estimate:
   Billing: unknown
   Poziom zużycia: średni-wysoki
   API-equivalent: ~20¢ – 80¢ (zależnie od providera; nie jest kosztem tej sesji)
   Token budget: M

Następny krok: po potwierdzeniu kontynuuj z tierem deep, jeśli runtime nie pozwala wskazać konkretnego aliasu.
Wymagane potwierdzenie: reasoning `high` jest powyżej `medium`. Odpisz `ok` albo innym jasnym potwierdzeniem, żebym kontynuował.
```
