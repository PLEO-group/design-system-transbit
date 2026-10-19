# JetBrains AI Chat — Adapter Runtime

- `doc_date`: `2026-07-22`
- `stale_after_days`: `14`
- `source_scope`: oficjalna dokumentacja JetBrains AI Assistant 2026.2

Czytaj ten plik, gdy użytkownik pracuje w IntelliJ, WebStorm, PyCharm, GoLand albo innym IDE z JetBrains AI Assistant.

## Rola Tego Pliku

To adapter runtime, nie źródło capability ani cen modeli. Capability i stawki bierz z provider-specific reference, ale dostępność oraz exact display name z aktualnego pickera JetBrains.

## Hierarchia Źródeł

1. Aktualny picker modelu i reasoningu w IDE użytkownika.
2. Screenshot albo lista przepisana przez użytkownika.
3. Oficjalna strona JetBrains `Supported models` dla właściwej wersji IDE.
4. Oficjalne docs providera o capability i publicznym pricingu API.

## Twarde Reguły

- Nie rekomenduj modelu ani reasoningu, którego nie ma w aktualnym pickerze.
- Zachowuj exact display name i casing z UI, np. `GPT 5.6 Terra`, nawet gdy API ID to `gpt-5.6-terra`.
- Nie zakładaj, że JetBrains AI Service, BYOK i lokalny provider pokazują ten sam katalog.
- Ikona reasoning w tabeli `Supported models` oznacza kategorię capability, nie gwarantuje konkretnej listy effortów w pickerze.
- JetBrains AI Service jest rozliczany planem/kredytami; cenę vendora oznaczaj wyłącznie jako `API-equivalent`, chyba że użytkownik potwierdzi BYOK z naliczaniem per token.

## Snapshot Oficjalnego Katalogu

Oficjalna dokumentacja JetBrains 2026.2 wymienia między innymi:

- OpenAI: `GPT 5.6 Luna`, `GPT 5.6 Sol`, `GPT 5.6 Terra`, `GPT-5.5`, `GPT-5.4 mini`, `GPT-5.4 nano`, `GPT-5.4`, starsze linie Codex i GPT.
- Anthropic: `Claude Fable 5`, `Claude Sonnet 5`, `Claude 4.8 Opus`, `Claude 4.7 Opus`, `Claude 4.6 Opus`, `Claude 4.6 Sonnet`, starsze 4.x.
- Google: `Gemini 3.5 Flash`, `Gemini 3.1 Pro`, `Gemini 3.1 Flash Lite`, `Gemini 3 Flash`, modele 2.5.

Brak modelu na tej liście nie wyklucza BYOK ani późniejszego rolloutu. Przykład: oficjalne docs Google mają już `gemini-3.6-flash`, ale snapshot JetBrains 2026.2 z 2026-07-09 go nie wymienia — bez aktualnego pickera nie rekomenduj go w JetBrains.

## Przykład Decyzji

Jeśli picker pokazuje tylko:

- `GPT 5.6 Luna`
- `GPT 5.6 Terra`
- `GPT 5.6 Sol`

oraz reasoning:

- `low`
- `medium`
- `high`
- `xhigh`

to mapuj `cheap` → Luna, `balanced` → Terra, `deep|max` → Sol i nie rekomenduj `none`, `max`, `pro` ani `ultra`, mimo że inne powierzchnie mogą je wspierać.

## Źródła

- https://www.jetbrains.com/help/ai-assistant/supported-llms.html
- https://www.jetbrains.com/help/ai-assistant/configure-project-rules.html
