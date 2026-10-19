# Claude / Anthropic — Provider Reference

- `doc_date`: `2026-08-24`
- `stale_after_days`: `14`
- `source_scope`: oficjalne dokumenty Anthropic

Czytaj ten plik, gdy użytkownik korzysta z Claude API, Claude Code, Claude Desktop, JetBrains AI Chat albo innego runtime z modelami Anthropic.

## Aktualny Katalog Do Routingu

- `claude-fable-5` — status `GA`; najbardziej zdolny szeroko dostępny model Anthropic do najtrudniejszego reasoning i długich zadań agentowych.
- `claude-opus-5` — status `GA`; rekomendowany start dla złożonego agentowego codingu i pracy enterprise.
- `claude-sonnet-5` — status `GA`; najlepszy balans szybkości i inteligencji.
- `claude-haiku-4-5` — status `GA`; najszybszy, najtańszy model do high-volume i lekkich subtasków.

`claude-mythos-5` ma status `restricted`: capability i ceny Fable 5, ale jest dostępny tylko dla zatwierdzonych klientów Project Glasswing. Nie rekomenduj go bez potwierdzonego dostępu.

## Ważne Reguły

- Nie rekomenduj modelu ani effortu, którego nie pokazuje runtime użytkownika.
- `claude-fable-5`, `claude-opus-5` i `claude-sonnet-5` używają dateless, pinned model IDs — nie są evergreen aliasami.
- Dla abonamentu Claude, Claude Code albo IDE nie przedstawiaj stawek API jako bezpośredniego kosztu sesji.
- Fable 5 może zwrócić `stop_reason: "refusal"` jako HTTP 200; to kontrakt runtime, nie sygnał słabszego modelu.

## Rozsądny Ladder

- `cheap`
  - `claude-haiku-4-5` dla prostych, krótkich zadań
  - `claude-sonnet-5` + `low`, jeśli wymagane jest jawne sterowanie effort
- `balanced`
  - `claude-sonnet-5` + `medium`
- `deep`
  - `claude-sonnet-5` + `high` lub `xhigh`
  - `claude-opus-5` + `xhigh` dla trudnego codingu i pracy agentowej
- `max`
  - `claude-fable-5` + `max`, gdy priorytetem jest najwyższa ogólna capability
  - `claude-opus-5` + `max`, gdy zadanie jest coding-first

## Effort i Thinking

Publiczne poziomy `effort` to `low`, `medium`, `high`, `xhigh` i `max`; ich dostępność zależy od modelu.

- `low` — prosty chat, lookupy, high-volume i subagenci.
- `medium` — balans jakości, szybkości i kosztu.
- `high` — domyślny effort dla obecnych modeli; complex reasoning i trudny coding.
- `xhigh` — długie coding/agentic workflows; wspierają Fable 5, Opus 5 i Sonnet 5.
- `max` — najwyższa capability bez ograniczeń token spend; wspierają Fable 5, Opus 5 i Sonnet 5.

Fable 5 ma adaptive thinking zawsze włączone. Opus 5 i Sonnet 5 korzystają z adaptive thinking; manualne `budget_tokens` nie jest właściwym sterowaniem dla tych modeli. Haiku 4.5 wspiera extended thinking, ale nie jest wymieniony jako model z parametrem `effort` — nie przypisuj mu effortu bez potwierdzenia runtime.

## Publiczne Stawki API

| Model               | Input $/1M tok. | Output $/1M tok. | Reasoning w kosztorysie |
| ------------------- | --------------- | ---------------- | ----------------------- |
| claude-fable-5      | $10.00          | $50.00           | stawka output           |
| claude-opus-5       | $5.00           | $25.00           | stawka output           |
| claude-sonnet-5     | $2.00           | $10.00           | stawka output           |
| claude-haiku-4-5    | $1.00           | $5.00            | stawka output           |

Zapowiadana podwyżka ceny Sonnet 5 do $3/$15 została anulowana; $2/$10 jest ceną standardową.

Thinking tokens są naliczane jako output. Rozdzielając koszt na thinking i widoczny tekst, nie sumuj drugi raz pełnego providerowego `output_tokens`.

## Szybkie Reguły

- Rewrite i klasyfikacja: `claude-haiku-4-5`.
- Typowy coding task: `claude-sonnet-5` + `medium`.
- Trudny debugging i review: `claude-sonnet-5` + `high` albo `xhigh`.
- Długi agentowy coding: `claude-opus-5` + `xhigh`.
- Najwyższa ogólna stawka: `claude-fable-5` + `max`.

## Źródła

- https://platform.claude.com/docs/en/about-claude/models/overview
- https://platform.claude.com/docs/en/about-claude/models/choosing-a-model
- https://platform.claude.com/docs/en/build-with-claude/effort
- https://platform.claude.com/docs/en/about-claude/models/whats-new-opus-5
- https://platform.claude.com/docs/en/about-claude/models/whats-new-sonnet-5
- https://platform.claude.com/docs/en/about-claude/pricing
- https://platform.claude.com/docs/en/about-claude/models/introducing-claude-fable-5-and-claude-mythos-5
