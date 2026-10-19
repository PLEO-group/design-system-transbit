# OpenAI / Codex — Provider Reference

- `doc_date`: `2026-08-24`
- `stale_after_days`: `14`
- `source_scope`: oficjalne dokumenty OpenAI

Czytaj ten plik, gdy użytkownik korzysta z modeli OpenAI w API, Codex, ChatGPT, JetBrains AI Chat albo innym runtime.

## Aktualny Katalog Do Routingu

Oficjalny domyślny wybór to rodzina GPT-5.6:

- `gpt-5.6-sol` — status `GA`; frontier capability do złożonego reasoning i codingu; oficjalny alias `gpt-5.6` wskazuje ten model.
- `gpt-5.6-terra` — status `GA`; balans jakości i kosztu.
- `gpt-5.6-luna` — status `GA`; kosztowo czułe zadania o dużym wolumenie.

Wszystkie trzy warianty obsługują `none`, `low`, `medium`, `high`, `xhigh` i `max` w Responses API. OpenAI dokumentuje też `reasoning.mode: "pro"` jako niezależny tryb wykonania, a nie osobny model ani reasoning effort.

## Ważne Reguły

- Nie rekomenduj modelu ani effortu, którego nie pokazuje runtime użytkownika.
- Zachowuj alias z powierzchni użytkownika: API może pokazywać `gpt-5.6-sol`, a IDE `GPT 5.6 Sol`.
- Nie zamieniaj runtime'owego `ultra` na API `max`. Codex `ultra` może obejmować dodatkową orkiestrację; traktuj go zgodnie z opisem aktualnego runtime.
- Dla subskrypcji Codex/ChatGPT i planów IDE nie przedstawiaj cen API jako bezpośredniego kosztu sesji.
- Starsze modele (`gpt-5.5`, `gpt-5.4`, linie Codex 5.3/5.2/5.1) traktuj jako fallback tylko wtedy, gdy są dostępne w pickerze albo użytkownik wymaga kompatybilności.

## Rozsądny Ladder

To mapowanie jest inferencją opartą o oficjalne pozycjonowanie capability i ceny:

- `cheap`
  - `gpt-5.6-luna` + `none` lub `low`
- `balanced`
  - `gpt-5.6-terra` + `low` albo `medium`
- `deep`
  - `gpt-5.6-sol` / `gpt-5.6` + `high` albo `xhigh`
- `max`
  - `gpt-5.6-sol` / `gpt-5.6` + `max`
  - opcjonalnie `reasoning.mode: "pro"` tylko w API i tylko gdy jakość ma większą wartość niż latencja i koszt

## Reasoning i Tryby Wykonania

- `none` — latency baseline bez reasoning; tylko gdy runtime udostępnia.
- `low` — proste, dobrze określone zmiany i lookupy.
- `medium` — rekomendowany punkt startowy dla codziennej pracy developerskiej.
- `high` — trudny debugging, review i większy refaktor.
- `xhigh` — złożone zadania agentowe i analiza wymagająca szerokiej eksploracji.
- `max` — najtrudniejsze workloady quality-first; zawsze porównaj z `xhigh` na evalach.
- `pro` — tryb dodatkowej pracy modelu, niezależny od effortu; nie używaj do rutynowych zadań.

## Publiczne Stawki API

| Model            | Input $/1M tok. | Output $/1M tok. | Reasoning w kosztorysie |
| ---------------- | --------------- | ---------------- | ----------------------- |
| gpt-5.6-sol      | $4.00           | $20.00           | stawka output           |
| gpt-5.6-terra    | $2.00           | $12.00           | stawka output           |
| gpt-5.6-luna     | $0.20           | $1.20            | stawka output           |

Reasoning tokens są częścią płatnego outputu. Przy rozbiciu kosztu na reasoning i widoczny output używaj rozłącznych estymacji, żeby nie naliczyć outputu dwukrotnie. Pro mode agreguje dodatkowe użycie i rozlicza je standardowymi stawkami wybranego modelu.

Dla promptów przekraczających 272k input tokens cała prośba GPT-5.6 ma mnożnik `2×` dla inputu i `1.5×` dla outputu. Uwzględnij go przed podaniem kosztu długiego kontekstu.

## Szybkie Reguły

- Rewrite, klasyfikacja i prosty lookup: `gpt-5.6-luna` + najniższy dostępny effort.
- Typowy coding task: `gpt-5.6-terra` + `medium`.
- Większy refaktor albo review wielu plików: `gpt-5.6-sol` + `high`.
- Root cause, architektura i decyzje wysokiej stawki: `gpt-5.6-sol` + `xhigh` lub `max`.
- Pro mode: dopiero gdy istnieje mierzalna korzyść jakościowa i runtime go udostępnia.

## Źródła

- https://developers.openai.com/api/docs/guides/latest-model
- https://developers.openai.com/api/docs/models
- https://developers.openai.com/api/docs/models/gpt-5.6-sol
- https://developers.openai.com/api/docs/models/gpt-5.6-terra
- https://developers.openai.com/api/docs/models/gpt-5.6-luna
