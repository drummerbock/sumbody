# Becoming the Heartbeat — UX Audit 01
Status: code-based review of PR #27 draft, 2026-10-08. Not a substitute for browser/user testing.

## Five non-negotiable product rules
1. No musical knowledge required to participate.
2. Recorded activity is never equated with personal worth.
3. Participation is never an obligation.
4. More recorded moments enable more evidence-based insights, but silence and restraint are meaningful; absence of data cannot be interpreted as intentional silence.
5. Structure should emerge from participation, not be a prerequisite for it.

## Evidence and priority
| Priority | Principle | Code evidence | Finding | Recommended intervention |
|---|---|---|---|---|
| P0 | Discoverability, constraints | `templates/base.html` requires a selected `life_area_id`; `app.py:add_sum` rejects a missing area; `SumEntry.life_area_id` is non-null | Users must classify before capturing | Design optional classification with a safe, reversible migration; audit every display, filter, and import path before implementation |
| P0 | Conceptual model | `templates/onboarding.html` starts with capture but still presents six sequential steps and a completion form | First use still looks like a curriculum | Treat recording as the primary path; collapse detailed framework behind optional exploration; ensure onboarding does not block return visits |
| P1 | Feedback | `templates/base.html` composer has rapid-save status and two different Accent actions | Useful confirmation, but accent-on-draft and accent-on-saved need explicit distinction | Label controls distinctly; test on touch, keyboard and screen readers |
| P1 | Conceptual model, mapping | `templates/base.html` primary and mobile nav differ; Life Areas sits within Rhythmos while account menu holds learning | Information architecture has competing mental models | Define three user questions: What mattered? What patterns can I see? What do I want to return to? Preserve existing deep links |
| P1 | Feedback, emotional design | `templates/home.html` still displays yesterday's Beat count next to today's | A nonjudgmental message competes with an implied daily comparison | De-emphasize yesterday by default; keep comparison available only when intentionally requested |
| P1 | Conceptual model, truthfulness | `templates/history.html` prominently shows totals, most-recorded days and shares | Observations can be mistaken for assessments of life quality or interpersonal impact | Make denominators, limitations, and recorded-only scope clear; avoid inferred motives or relationships |
| P2 | Affordances, signifiers | `templates/areas.html` supports drag handles and touch rearrangement | Discoverable sorting is not necessarily accessible to keyboard users | Audit keyboard reorder and status feedback; retain existing ordering |
| P2 | Constraints | `app.py:signup` seeds Family/Friends/Myself/Work/Other | Good low-friction defaults, but they may impose a worldview | Treat defaults as editable suggestions, never an authoritative map of the user's life |
| P2 | Discoverability | `templates/musical_language.html` offers a glossary | Good reference, but learning must remain optional | Link terms contextually, without repeated prompts |

## Don Norman's seven principles
- Discoverability: first Beat CTA exists, but required category obstructs action.
- Feedback: rapid composer provides confirmation; validate distinct Accent states.
- Conceptual model: Beats / Rhythmos / Audify need a simple user-facing relationship.
- Affordances: capture and category chips exist; validate obvious interaction.
- Signifiers: plain-language nav is improved but still mixed.
- Mapping: categorization precedes recording, contrary to the user's immediate intent.
- Constraints: required Life Area prevents unclassified capture; preserve privacy and account scoping.

## Experience / IoDIP lens
- Entry: user should experience value before studying vocabulary.
- Continuity: Today, Discover, and intentions should tell one story.
- Emotional tone: invite awareness, not achievement pressure.
- Restraint: no streak shame, forced check-ins, invented conclusions from absence.
- Meaningful reveal: insights should explain the recorded evidence and invite interpretation.

## Proposed implementation sequence
1. Finish and test PR #27's low-risk copy/navigation improvements. Do not merge before mobile and accessibility smoke tests.
2. Design the unclassified Beat data contract and migration in a separate focused PR: nullable area reference vs dedicated unclassified representation, handling templates, queries, importer, filters, and existing records. Avoid assigning a false Life Area merely to satisfy storage.
3. Redesign onboarding around immediate capture; move framework to optional learning.
4. Refactor Audify around recorded observations and caveats; make comparisons opt-in.
5. Test with first-time non-musician users and a returning user after a long absence.

## Acceptance scenarios
- New user records a Beat with description only, with no forced Life Area, Accent or Rhythmos.
- Existing user retains Life Areas, ordering, Beats, Accents, and links.
- No entries for 30 days yields no shame, streak-loss or assumption of mindful rest.
- An intentional pause can be recorded as a Beat if the user chooses.
- Audify never says recorded counts equal time spent, importance, virtue, or effect on others.
- Keyboard and mobile interactions work without lost drafts.
- The musical glossary is available but not a prerequisite.
