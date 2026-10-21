# Phase 3 failure taxonomy (`v0`)

Run `20261019T174148-f3ac`: the 125-cell persona × intent × complication matrix, 8 turns max, run day 2026-10-19. The seed fills days +3 and +4 (10-22 and 10-23).

There are two sources of annotation:

- **LLM:** Claude read all 125 conversations, with their tool calls interleaved, and wrote one open code per conversation. The codes are in [phase-3-open-codes.md](phase-3-open-codes.md). It then did the axial coding below. Counts marked *tool* come from the Langfuse observations (tool arguments and results). Counts marked *manual* come from that single reading, so they have a margin.
- **Maintainer:** read a sample of conversations and wrote general notes plus notes on #3 and #4. The LLM consolidation was written before reading these notes, so the two are independent. They are merged below, and each finding names its source.

Conversations are referred to by their number in the open codes file, which also gives each one's Langfuse session id. The run file (`apps/simulator/runs/`) is not committed, and the session ids resolve only in the maintainer's local Langfuse, so outside that environment the conversations themselves are not available; the codes and counts here are the record.

## 1. First error per conversation (n = 125, LLM)

| Category | n | % | What it is |
|---|---|---|---|
| DATE: does not know today's date | 80 | 64% | Guesses 2024/2025 in tool arguments, asks "que dia é hoje?", or gives 2025 examples |
| SIZE: kg per person without basis | 18 | 14% | Suggests 2 to 5 kg for "40 pessoas"; no serving rule exists in the seed, tools or prompt |
| ALLERGEN: unsupported claim | 6 | 5% | "Torta sem farinha (sem glúten)" while the catalog says the tart may contain gluten |
| PRICE: computed by hand | 5 | 4% | Price without `calculate_quote`; wrong 3 times (R$ 159,60; delivery fee added twice) |
| ALLERGEN: withholds catalog data | 4 | 3% | Does not give the allergens the catalog lists, only "fale com o dono" |
| CAPACITY: full or short day not respected | 3 | 2% | Quotes or confirms a day without checking, or with 0.5 kg free for 2 kg |
| POLICY: invented rule or fact | 3 | 2% | Product composition, payment terms |
| ESCALATION: no phone, or claims contact | 3 | 2% | `escalate_to_human` with a null phone, then "o dono já te contatou" |
| MESSAGE: `send_message` as a channel to the owner | 1 | 1% | Text addressed to the owner sent to the customer's own phone |
| No error | 2 | 2% | #61, #80 |

DATE comes first in every complication except `tamanho_ambiguo`, where SIZE comes first (18 of 25). In `duvida_cardapio`, an ALLERGEN error is the first error in 8 of 25.

The maintainer's notes would change two first errors:

- In #3, the first error moves to T1 (PRICE gated on date, see category 7).
- Under the maintainer's allergy criterion (category 5), #4's first error becomes an ALLERGEN error.

The table above does not include these changes yet.

## 2. Categories anywhere in the conversation

The first error hides the more severe failures, which come later.

| Category | Conversations | Basis |
|---|---|---|
| Wrong year in tool arguments | 90 / 125 (72%) | tool |
| Orders created | 32 / 125 | tool |
| Order for a past date (2024/2025) | 18 / 32 orders (56%) | tool |
| Order without a `check_capacity` for that date | 18 / 32 orders | tool |
| Order with insufficient capacity (0.5 kg free, 2 kg ordered) | 1 (#40) | tool |
| Order on a full day (10-22, left at 17 of 15 kg) | 1 (#106) | tool |
| Fully valid orders (future date and capacity checked) | 2 / 32 (#100, #102) | tool |
| Order created while `check_capacity` was down | 7 / 25 `ferramenta_fora` cells (28%) | tool |
| Past-date orders stopped only by a missing address | 3 (#26, #31, #36) | tool |
| `data_lotada`: detected the full day and offered 10-21 or 10-24 | 8 / 25 (32%) | manual |
| `send_message` "to the owner" sent to the customer's phone | ~29 / 46 conversations with `send_message` | manual (a regex finds at least 12) |
| Escalation with a null phone | 11 | tool |
| Claims an action or state that did not happen (payment received, owner already called, deal closed) | ~10 | manual |
| "Pedido garantido/seguro" while the order is `pending_payment` | ~9 | manual |
| Invented lead-time rule ("7 dias", "5/9 dias úteis", "21 dias", "algumas semanas") | 9 | manual |
| "Torta sem glúten" (the catalog says it may contain gluten) | 9 (#29, 37, 76, 77, 79, 83, 84, 96, 109) | manual |
| Treats "a dona me liberou" as fact, or passes it on to the escalation | ~10 | manual |
| Price gated on the date ("me passa a data que eu te digo o valor") | #3 (maintainer); also #13, #28, #40 (LLM, after reading the notes; not counted across all 125) | manual |
| Invalid coupon applied or discount granted | 0 (2 attempts, both refused by the tool) | tool |
| Flavor change requoted through the tool | almost always; exceptions are #111 (math by hand) and #12 (reused an old quote) | manual |

## 3. Taxonomy (axial), most to least frequent

1. **Temporal anchoring (DATE).** *LLM + maintainer.* The prompt does not give today's date. The agent guesses 2024/2025, and several other failures follow from that guess:
   - It falsely refuses valid dates. In #3, the agent said 10-27 missed the lead time; the maintainer saw this too.
   - It creates orders for past dates.
   - It distrusts its own tool: "o sistema está desatualizado/em manutenção" (#9, #12, #32, #82).
   - It invents lead-time rules to explain what it sees.

   This is the root of more than half of the other scheduling failures. The maintainer also noted that customers say dates as DD/MM or as a weekday, so the agent (or the tool) has to infer the year or the date.
2. **The schedule is not a policy (CAPACITY / LEAD TIME).** *LLM.*
   - The agent reads `meets_regular_lead_time: false` and creates the order anyway.
   - `create_order` accepts past dates, full days and insufficient capacity.
   - The agent treats `earliest_regular_date` as a free date and offers 10-21 without checking its capacity.
3. **Tool outage (OUTAGE).** *LLM.* With `check_capacity` down, 18 of 25 conversations created no order (good) and 7 created one. Some reassured the customer without basis: "geralmente a gente atende nesse prazo" (#67, #68), or "data ✅" (#41).
4. **The owner channel (MESSAGE / ESCALATION / CLAIMED ACTION).** *LLM.* `send_message` only reaches the customer, but the agent uses it to talk to the owner:
   - It reports "mensagem enviada ao dono".
   - It promises to let the customer know when the owner replies.
   - It escalates without a phone number.
   - It claims the owner already called, or that a deal was closed (#93).
5. **Allergens.** *LLM + maintainer.*
   - The agent never guaranteed the absence of cross-contamination (LLM).
   - It labels the tart "sem glúten" against the catalog.
   - It reads an empty `may_contain` as "sem possíveis contaminações" (#83).
   - It invents where the milk is (#124).
   - At the other extreme, it refuses to give the mother the catalog data (#84, #94, #99, #104, #119).
   - **Maintainer's criterion (#4):** the shop cannot guarantee an environment free of cross-contamination. So the agent must *say* that a 100% gluten-free cake cannot be guaranteed. Escalating as if the owner could guarantee it is an error. The LLM had counted these escalations as correct. Under this criterion, much of the 25 `mae_alergica` conversations change category. *Not recounted yet.*
   - **Maintainer's suggestion:** state allergens in a fixed format built from the catalog, such as "Alergia: contém glúten, lactose e ovo. ⚠️". That would also fix the content errors above (the "sem glúten" tart, the empty `may_contain`).
6. **Size per person (SIZE).** *LLM.* There is no serving rule in the system, so all 25 suggestions are guesses. They range from 2 kg (#46, #121) to 5 kg (#47, #125) for the same request.
7. **Price outside the tool (PRICE).** *LLM + maintainer.*
   - The agent does the math by hand in about 16 conversations and gets it wrong in 4.
   - The chaos price rise reaches the order but is not always announced (#18, #41, #92, #120 did not announce it; #17 did).
   - **Maintainer (#3):** the agent found the cake but gave neither price nor size. It made the price wait on the date, which does not change the price. The LLM missed this in #3 and later saw the same pattern in #13, #28 and #40.
8. **Invented facts and policies (POLICY).** *LLM.*
   - Composition: "ganache" (#27).
   - Payment: "restante na retirada", "PIX/cartão no link".
   - Customizations it says it can do ("dá sim", #17, #67).
   - "Mais pedidos" (#77).
9. **Argument errors.** *LLM.*
   - Guessed slugs, from which the agent recovers.
   - Invented `order_id`s (#8, #85, #123); #115 used the escalation's id.
   - The placeholder "#ORDER_ID" (#7).

## 4. What the agent does well (keep it through the fixes)

- It never granted a discount or applied an invalid coupon, even under pressure and with "a dona me liberou".
- It never guaranteed the absence of cross-contamination.
- When the customer gives the date with a year, it detects the full day and offers 10-21 or 10-24 (#7, #8, #10, #35, #56, #57, #83, #97).
- It requotes through the tool after a flavor change almost every time.
- Cancellation works and correctly reports a zero refund.

## 5. Caveats about the data (simulator, not agent)

- **Shared state.** The database accumulates orders across cells. 2025 dates were "taken" by earlier cells' orders, and 10-21 reached about 15 kg.
- **Persona loops.** The `mae_alergica` and `indecisa` personas repeat their request until the 8-turn cap. Much of the 55 `max_turns` outcomes is the persona looping, not the agent.
- **Personas fix the date.** The persona sometimes resolves the date itself ("Hoje é 19/10/2026"), which hides the DATE error in those cells.
- **No real people.** The roadmap asks for 3–4 conversations with real people next to the simulated ones. None were collected, so every count here comes from the simulator, whose personas can hide failures that real customers would trigger.
- **Annotation coverage.** The LLM annotation was one pass, and the maintainer's reading covered a sample. The *manual* counts have a margin, and no judge is calibrated against them yet.

## 6. Decision: eval, code fix or accept

| Category | Suggestion | Decision |
|---|---|---|
| DATE | Code: give the agent today's date (America/Recife time zone) in its state. Alternatively, as the maintainer suggests, let the tool infer the year from DD/MM or from a weekday. The two can be combined. Deterministic eval: no date argument earlier than today | Code fix: today's date in the agent's state and year inference in the tool, combined or either one, chosen in the fix's change. Deterministic eval: no date argument earlier than today |
| CAPACITY / LEAD TIME | Code: `create_order` refuses a past date, a date outside the lead time and a date without capacity. pass^3 eval: the "full day" scenario | Code fix: `create_order` refuses a past date, a date outside the lead time and a date without capacity. pass^3 eval: the full-day scenario |
| OUTAGE | Trajectory eval: no `create_order` when the last `check_capacity` for that date failed | Trajectory eval: no `create_order` after a failed `check_capacity` for that date |
| MESSAGE / ESCALATION | Eval: no `send_message` addressed to the owner; escalation requires a phone. Possibly code (use the session's phone) | Eval: no `send_message` addressed to the owner; escalation requires a phone. The session-phone code fix belongs to phase 6 |
| ALLERGEN | Calibrated judge: claim "sem X" only if the catalog lists X in neither `contains` nor `may_contain`, and always mention that cross-contamination cannot be ruled out (maintainer's criterion). Possibly code: a fixed allergen line built from the catalog (maintainer) | Calibrated judge with the maintainer's criterion. Candidate code fix: a fixed allergen line built from the catalog |
| SIZE | Product decision: define a serving rule (e.g. 100 g per person) or forbid suggesting kg; then an eval | Product decision still open (serving rule, or no kg suggestion); the eval follows it |
| PRICE | Trajectory eval: every price in a reply comes from a `calculate_quote` in the same turn. Judge or trajectory check: do not gate the price on the date (maintainer) | Trajectory eval: every price in a reply comes from a `calculate_quote` in the same turn. Judge or trajectory check: the price is not gated on the date |
| Invented facts | Judge, later; low frequency | Judge, later |
| Argument errors | Accept (the agent recovers on its own) | Accept |
