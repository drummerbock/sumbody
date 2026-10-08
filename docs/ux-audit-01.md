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

## Audit 02 — interaction reliability, accessibility, and truthfulness (2026-10-08)
This section is an additional code inspection, not a live browser or automated test result.

### Critical: recorder resilience
- `templates/base.html` does not persist a draft to sessionStorage/localStorage or another recoverable location. The earlier roadmap's assumption that draft persistence was preserved is **not verified** and is contradicted by the inspected inline script. A page reload or navigation may lose unsent text. Design explicit recoverability with privacy considerations (avoid silently retaining sensitive personal journal text indefinitely).
- The quick composer is JavaScript-dependent for its intended opening interaction. `templates/add.html` says the composer should open automatically, but the only observed auto-focus occurs when the path is `/add`. Validate no-JS and slow-network fallbacks.
- The submit handler intercepts POST and fetches JSON. It disables the send button and reports network errors; this is positive. Test double submission, loss of connectivity, and what happens after a successful save followed by a navigation.

### High: accessible controls and user choice
- `templates/areas.html` has a drag handle, pointer drag, and touch drag, but does not render keyboard move controls, despite a server-side `/areas/<id>/move/<direction>` route existing. Expose Up/Down buttons with meaningful labels and announcements.
- `static/style.css` contains transitions but no `prefers-reduced-motion` rule in the inspected file. Add a reduced-motion override, and test visible keyboard focus, contrast, and touch target sizes.
- `templates/base.html` offers two Accent actions. The post-save action updates state, but the toggle's label reverts to 'Accent saved Beat' in one code path. Standardize labels and test keyboard/assistive-technology feedback.
- Mobile bottom navigation uses short labels while desktop labels include both plain-English and musical terms. Make labels coherent without crowding small screens.

### High: privacy and evidence
- `app.py` scopes Beat and Life Area queries to `current_user.id` in inspected routes; this is a positive security baseline, not a full security audit.
- Signup currently seeds five Life Areas. Keep these suggestions editable, and do not automatically treat an unchosen area as a statement about personal priorities.
- Audify's 'Shared with someone' percentage uses only entries where communication is known; its denominator should be visible. A recorded shared action does not establish how another person perceived it.
- Current `SumEntry` includes a `communicated` flag, not evidence of another person's perception. Do not claim Audify measures what others feel or infer resonance from this flag alone.

### High: onboarding continuity
- Signup creates default Life Areas, then redirects to onboarding. Onboarding can record a Beat via the shared composer, but completing onboarding still requires a separate POST action. Test first-save return flow and whether a user can bypass the instructional steps without confusion.
- Existing users who have no active Life Areas face a blocked composer; handle this state gracefully when implementing unclassified capture.

### Decision record
1. **Approve for design:** unclassified capture, with reversible and well-tested data changes in a separate PR.
2. **Approve for design:** recoverable drafts and clear network feedback; define privacy-sensitive retention.
3. **Approve for design:** keyboard-operable ordering and reduced-motion support.
4. **Hold:** automated classification, AI personality inferences, streaks, motivational scores, or new engagement mechanics.
5. **Hold merge:** PR #27 is still draft; no automated or live interaction tests were run during this audit.

### Next test matrix
- First-time signup → first Beat → revisit onboarding → return to Today.
- Existing account with zero active Life Areas → record Beat.
- iOS/Android narrow viewport → open composer → type → change Life Area → save.
- Draft interrupted by accidental navigation, refresh, and network loss.
- Accent draft, then accent saved Beat; confirm independent controls and consistent status.
- Keyboard-only Life Area reordering and screen-reader announcements.
- Thirty days of no activity → return without guilt or inferred silence.
- Audify with zero Beats, archived Beats, unknown communication flags, and mixed Life Areas.

## Audit 03 — Visual-first, minimal-reading experience (2026-10-08)
Product-owner direction: SILK recorder must feel frictionless; prefer icons and useful imagery to prose, without requiring users to learn a novel.

### Design requirement: show, don't lecture
- **First screen:** one dominant action: record a Beat. Use a short question, not a multi-paragraph framework.
- **Capture:** description first; save available immediately. Secondary controls (Accent, Life Area, date, communication) disclosed only on demand. Optional classification requires the separate data-contract review already documented.
- **Navigation:** recognizable icons plus concise labels, especially for app-specific concepts. Avoid icon-only navigation until comprehension is tested; always provide accessible names and selected states.
- **Onboarding:** replace multi-step prose with one working example and immediate practice; keep the musical glossary discoverable, not compulsory.
- **Audify:** use a small number of honest, legible visualizations with plain-language captions and explicit scope ('from your recorded Beats'). No inferred emotions, values, or interpersonal impact.
- **Rhythmos / Life Areas:** represent structure visually through grouping and spatial hierarchy rather than large explanations. Avoid category icons that imply universal meanings.
- **Silence:** use whitespace and neutral states; do not fill an empty day with calls to action or presume intentional rest.
- **Imagery:** only when it explains a real concept or helps orientation. Avoid decorative images, dashboard clutter, and inaccessible image-only information.

### Copy budget and visual accessibility
- One primary message and one primary action per screen or major panel.
- Use short, concrete labels; place longer definitions behind optional 'Learn more' affordances.
- Pair unfamiliar symbols with text; icons must have accessible names and adequate touch targets.
- Do not rely on color, icon shape, animation, or imagery alone to convey meaning.
- Validate mobile scanning, keyboard navigation, screen-reader order, zoom/reflow, contrast, and reduced-motion settings.

### SILK recorder acceptance criteria
1. User can type and save a Beat without selecting a Life Area or reading an explanation (after the separately scoped schema/validation change).
2. The primary capture path has one obvious field and one obvious save action.
3. Accent, category, date and communication choices remain optional and discoverable.
4. Clear save-in-progress, success, failure, and draft-recovery states.
5. No silent data loss on interruption; retention behavior is privacy-conscious and understandable.
6. Accessible labels and feedback for both icons and text controls.
7. Visual simplification does not conceal important actions or weaken informed choice.

### Implementation guardrail
Do not redesign all screens or introduce an icon library blindly in PR #27. Establish a small consistent icon vocabulary and screen-by-screen visual hierarchy, then implement in bounded follow-up PRs with usability checks.
