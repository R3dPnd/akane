# Akane — Job Hunt & Resume Tailoring Design

**Date:** 2026-11-04
**Status:** Draft for review (revised 2026-11-05 to build on pnd-job-search)
**Extends:** `2026-10-26-akane-design.md`. It replaces that spec's §6.8
("Job applications") and moves its Phase 3b ahead of the rest of Phase 3.

## 1. Why

The user asked typed-chat Akane (qwen3:8b plus a single `web_search` tool) to
find part-time SWE work. In practice:

- **She talked instead of acting.** "Would you like me to look up…?" The user
  had to ask three times ("yes please", "link them here", "I want you to run the
  search") before any search ran.
- **She doesn't know the user.** She has no resume, so she can't match jobs to
  experience. She asked where the user lives right after being told, and
  invented a "Bremerton" search.
- **She gave advice, not results.** The one search returned "try LinkedIn or
  Indeed" and no actual postings or links.

A small local model and a one-shot search can't do a real job hunt. Claude has
to do the heavy work in the background, with the user's resume and constraints
in hand. Akane's job is to kick it off, deliver the results, and act on
follow-ups.

## 2. What the user wants

Each morning, Akane has already searched overnight. When the user first starts
or talks to her, she says something like "Morning. 6 new leads overnight; the
best three are…", and the full list, with links, is on screen. The user then
says "tailor my resume for 2", "dismiss 4" or "I applied to 1". Tailored Word
documents appear in a folder for that job, and tomorrow's report holds only new
leads plus any follow-ups that are due.

## 3. Goals

1. **An overnight job hunt.** Real postings with working links, matched to the
   user's resume and constraints (§4), run unattended.
2. **A morning report.** Spoken once a day as a short summary; the full report
   shows in the chat; it can be pulled up again on request.
3. **No repeats.** Akane keeps a record of every lead she has shown. A lead that
   has been shown, dismissed or applied to never comes back as new.
4. **Follow-ups by number:** tailor, dismiss, mark as applied.
5. **Resume and cover-letter tailoring**, as already agreed in the main spec
   §6.8 (Word in, Word out, PDF on request, nothing invented), now triggered by
   lead number as well as by a copied posting.
6. **Act, don't offer.** Asking for any of this starts it right away; Akane
   never answers with "would you like me to…?"

## 4. The user's criteria (user decisions)

| Criterion | Value |
|---|---|
| Work type | Part-time SWE roles **and** async gig work: AI code evaluation and training (e.g. DataAnnotation, Outlier), freelance fixes and builds, paid code review, bounties |
| Shape | Async first. Doable in short bursts, including while waiting on AI responses and in transit (laptop or phone) |
| When | Early mornings are best. **Mon–Thu: commutes Tacoma → Seattle**, so no fixed daytime commitments those days. **Fridays are flexible**, so in-person or scheduled Friday work is OK |
| Where | Remote first; otherwise Tacoma or Seattle |
| Pay floor | **$25/hour** (or the equivalent per task, when a platform states it) |
| Automatic no (designer's guess) | Fixed Mon–Thu daytime hours, on-call, in-office Mon–Thu, full-time disguised as part-time |

These are personal, so they live in the gitignored `config.local.yaml` under a
`job_hunt:` block, alongside `user.location`. *My call* on the shape:

```yaml
job_hunt:
  pay_floor_hourly: 25
  locations: [Remote, "Tacoma, WA", "Seattle, WA"]
  kinds: [part-time SWE, AI code evaluation/training, freelance, code review, bounties]
  schedule: >
    Async first, in short bursts (waiting on AI, in transit). Early mornings best.
    Mon-Thu commuting Tacoma->Seattle: no fixed daytime commitments those days.
    Fridays flexible: in-person or scheduled work OK.
  exclude: [fixed Mon-Thu daytime hours, on-call, in-office Mon-Thu, full-time]
  max_leads: 8
  run_at: "04:00"
```

## 5. Non-goals

- Akane never submits applications, fills in web forms or logs into job sites.
  The user applies themselves.
- No scraping behind logins (LinkedIn's signed-in pages, etc.). Postings come
  from JSearch, plus Claude's public web search for gig platforms (§7.3).
- No email or phone delivery of the report in this build.

## 6. Anti-goals (a failure even if it "works")

- **Made-up leads or dead links.** Every lead's URL is checked during the hunt
  (§7.3): dead links are dropped, and bot-blocked ones are flagged.
- Tailored documents that invent employers, dates, metrics or skills (carried
  over from the main spec §6.8).
- Showing dismissed or applied-to leads again, or reading the same report aloud
  more than once a day.
- Akane offering instead of acting ("would you like me to search?") when asked
  to hunt, tailor, dismiss or mark as applied.
- Claude usage on a billed API key; it goes through the `claude` CLI bridge only.

## 7. Design: Akane on top of pnd-job-search

The user already built **pnd-job-search** (`~/Git/r3dpnd/pnd-job-search`, a Go
backend with a React UI and PostgreSQL). It already has:

- **job search** through the JSearch API, with postings stored in
  `job_postings` (upserted, dismissable, trackable);
- **an application tracker** with stages, notes and history;
- **resumes** (upload, versions, active resume) and fit scoring;
- **a tailoring pipeline** that runs in the background and survives restarts:
  fit and track analysis, then clarifying questions, then targeted edits
  (`awaiting_review`);
- **in-place Word editing** that keeps formatting (`DocxService.ApplyEdits`)
  and saves a new resume version;
- **cover letters and interview prep**;
- **Claude through the `claude` CLI** (subscription), not the SDK.

**User decisions (2026-11-05):**
- Akane reuses this app as the engine instead of rebuilding it.
- PostgreSQL comes from **Homebrew**, not Docker.
- The user gets a **JSearch (RapidAPI) key**.
- The **current base resume** (`~/Downloads/Resume.docx`) is used as-is for
  now; the user will update it later by uploading a new version.

### 7.1 Who does what

| | pnd-job-search (engine) | Akane (voice, schedule, delivery) |
|---|---|---|
| Postings | JSearch search, `job_postings` store, dismiss/track | builds the queries from `job_hunt:` criteria; overnight `akane hunt` |
| Screening | — | one Claude call ranks the new postings against criteria and resume and writes "why it fits" + a suggestion |
| Report | — | `~/.akane/applications/reports/YYYY-MM-DD.md`, spoken summary, "Morning report" chat stream |
| Applications | tracker, stages | "I applied to 1" → track the posting as an application; status updates by voice |
| Tailoring | pipeline: analysis → clarifying questions → edits → new resume version (Word, formatting kept); cover letter | starts it, relays clarifying questions in chat, accepts the edits, saves the Word files, announces |
| UI | full review/editing UI (`localhost:5173`) for heavy edits | everyday use by voice and text |

Akane talks to the app only through its REST API (`http://localhost:8080/api/v1`),
via a new Akane tool server, `job_search_server` (in the **akane** repo under
`integrations/servers/`, since it's specific to this app, not generic runtime).

### 7.2 Running the app on this Mac (J0)

- PostgreSQL 16 from Homebrew (`brew install postgresql@16`,
  `brew services start postgresql@16`), with database `job_search`. Migrations
  run with the app's `migrate` command.
- The backend is built for macOS (`go build`). The committed Windows `.exe`
  files are not used.
- `pnd-job-search/.env`: `DATABASE_URL`, `JOBS_API_KEY` (the user's JSearch
  key), `JOBS_API_HOST`, `PORT=8080`, `UPLOADS_DIR`. It's gitignored, and the
  key never goes into akane.
- The backend runs as a **launchd agent** (always on, restarts on failure), so
  the overnight hunt and Akane can reach it without the user starting it.
  Managed by `akane jobs-app install|uninstall|status`. *My call.*
- **Billing guard (anti-goal):** the app's `AIService.complete` runs `claude`
  with `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` removed from its environment,
  the same rule as pnd-mcp's `claude_env()`. This is a small change in
  pnd-job-search.
- The base resume is uploaded once and activated (`POST /resumes`,
  `/activate`).
- Akane's preflight warns, without blocking, if the app's `/health` doesn't
  answer.

### 7.3 The hunt (`akane hunt`, run nightly by launchd at `job_hunt.run_at`)

1. Build queries from `job_hunt:`. Each `kinds` entry is combined with each
   location (Remote uses `remote_jobs_only`), up to a cap (default 6 queries,
   which stays inside JSearch's free tier when run nightly). The queries run
   through the app's `GET /job-postings/search`; the app stores and dedupes the
   postings.
2. New postings are those not yet in Akane's leads index
   (`~/.akane/applications/leads.json`: app posting id → status, number, date).
2b. **Gig platforms, a second source (my call).** JSearch mostly indexes
   LinkedIn, Indeed and Glassdoor, so it finds little async gig work (AI
   code-evaluation and training platforms, paid code review, bounties), which
   is the user's top priority. One extra `claude` CLI call with WebSearch
   allowed asks for currently open gig opportunities matching §4, as strict
   JSON with a URL each. These leads have no app posting id. They're keyed by
   URL in `leads.json`, run through the same screening and link checks, and are
   marked "gig" in the report. If tailored or marked applied, Akane creates the
   application in the app directly (`POST /applications`) instead of tracking
   a posting.
3. **One `claude` CLI call** (shared bridge) screens all new postings at once.
   It gets their title, company, pay and a trimmed description, plus the
   resume text (from the app's active resume) and the criteria (§4). It
   returns strict JSON per posting: `keep`, `score` 0–100, `fit` (one sentence
   tying the posting to the resume and schedule), and `suggestion` (one
   sentence: what to emphasize, or a caveat such as "on-site Tue; only works if
   …").
4. Rule checks in code, not left to the model: drop postings whose stated pay
   is below the floor (unknown pay is kept and marked "pay not listed"). Drop
   links that are dead (404/410 or unreachable), and flag bot-blocked links
   "couldn't verify".
5. Keep the top `max_leads` by score, number them, write the report, and
   record them in `leads.json` as `new`.
6. Failures (app down, JSearch quota used up, Claude not signed in) are
   written into the report, so the morning summary mentions them instead of
   silently being empty.

### 7.4 The morning report

- **Contents:** for each lead, its number, title, company, pay,
  remote/location, score, the "fit" line, the suggestion and the link. Then a
  "Follow-ups" section listing tracked applications still at "applied" 7, 14,
  21… days after their last stage change.
- **Spoken version (my call):** about 3 sentences, no links. "Morning. 6 new
  leads overnight. The best three: …. They're in the chat."
- **On screen:** posted as an assistant message into a work stream named
  "Morning report".
- **When it's delivered (user decision):** once a day, the first time Akane is
  ready in `--voice` or `--speak` mode. If Akane was already running when the
  report was written, at the first wake word or typed message after that.
  Delivery is recorded (front matter `delivered_at`), so it happens once across
  restarts. In silent `akane dev` the report is posted in the chat, not
  spoken, and still counts as delivered.
- **On request:** "read my morning report", "show me the leads", "what was
  number 3?".

### 7.5 Leads and numbering

- Each lead is `new`, then `shown` once its report is delivered, then
  `dismissed` (also dismissed in the app), `applied` (the app tracks the
  posting as an application) or `tailoring`/`tailored`. A lead never returns
  to `new`.
- Numbers belong to the **latest report**, whose header names its date.
- A mid-day hunt appends to today's report, continuing the numbers.
- Older leads can be referred to by company name.

### 7.6 Tools (`job_search_server`)

| Tool | Does |
|---|---|
| `get_morning_report()` | latest report text |
| `get_lead(n)` | one lead, with its fit and suggestion |
| `dismiss_lead(n)` | dismiss here and in the app |
| `mark_applied(n)` | track the posting as an application in the app; the lead becomes `applied` |
| `update_application(company, status)` | applied → stage "Applied"; interviewing → the next interview stage after the current one (Phone Screen → Technical Interview → Final Round); offer → stage "Offer" and status `offer`; rejected → stage "Rejected" and status `rejected`; closed → status `archived` (stage unchanged). Stages are found by name in the application's own stage list. *My call.* |
| `list_applications()` | the app's applications and their stages |
| `start_hunt()` | run `akane hunt` detached now; returns "On it"; announced when done |
| `start_tailoring(n)` | track the lead as an application if it isn't already, start the app's pipeline with the active resume; returns "On it"; Akane follows it (§7.7) |
| `answer_tailoring(n, answers)` | send the user's answers to the pipeline's clarifying questions |
| `tailoring_status(n?)` | where tailoring stands ("is my resume done yet?") |

Background work runs as detached `akane` commands (`hunt`, `tailor-watch`),
recorded in `~/.akane/jobs.json`, so it survives `akane stop`. When a run
finishes it POSTs `/api/v1/announce` to Akane's API. The orchestrator speaks
it when idle (reusing the typed-reply speech queue) and posts it into the
"Morning report" stream. If Akane is down, the announcement waits in
`jobs.json` and is delivered once at the next start.

### 7.7 Tailoring through the app's pipeline

1. `start_tailoring(n)`: the posting is tracked as an application, and the
   pipeline job is started (`POST /pipeline/jobs` with the application and the
   active resume).
2. A detached `akane tailor-watch <job>` follows the job (polling
   `/pipeline/jobs/{id}`, or using its SSE events).
   - **`awaiting_clarification`** (the app's pipeline always stops here): the
     questions are posted into the "Morning report" chat and announced ("I
     have 2 quick questions about the Acme resume"). The user answers in chat
     or by voice; `answer_tailoring` submits the answers. "Skip the questions"
     submits none and carries on. *My call:* there's no automatic timeout. The
     job stays waiting, survives restarts (the watcher is re-spawned from
     `jobs.json` when Akane starts), and each morning report lists any
     tailoring that's waiting on answers.
   - **`awaiting_review`** (*my call*): Akane accepts the suggested edits.
     She saves a new resume version with them (the app's in-place Word edit,
     formatting kept) and generates a cover letter. Both files go to
     `~/.akane/applications/<company>-<role>/`, along with `changes.md`
     listing every edit. The job is marked complete and announced.
   - The user can still open the app's UI to review, tweak or regenerate.
   - **failed:** announced with the reason; the user can say "try again".
3. **Nothing invented:** the app's edit prompts already work from the resume
   text. Akane adds the check from main spec §6.8: every employer and date in
   the tailored text must exist in the base resume, or the documents are
   withheld and the reason announced.
4. "Make PDFs of those": export through Word (main spec §6.8).

### 7.8 Routing: act, don't offer

- **Agents:** `jobs` (report, lead, dismiss, applied, status, hunt) and
  `apply` (tailoring tools), enabled.
- **Prompt rule:** "When the user asks to find jobs, tailor a resume, dismiss
  or mark a lead, call the tool immediately. Never ask 'would you like me
  to…?' for these."
- The runtime's promise nudge is the backstop.
- The always-on tool count stays at or under 22, checked by test.

## 8. Phasing

| Step | Delivers | Done when |
|---|---|---|
| J0 | pnd-job-search on this Mac: Homebrew Postgres, migrations, macOS build, `.env` with the user's JSearch key, billing guard, launchd agent (`akane jobs-app`), base resume uploaded and active, preflight warning | the app's `/health` answers after a reboot; `GET /job-postings/search?query=…` returns real postings; its UI shows the resume |
| J1 | `job_hunt:` config, `akane hunt` (queries → screen → rules → report), `leads.json` | `akane hunt` writes a ranked report of real postings with fit lines, suggestions and links; a second run shows no repeats |
| J2 | `job_search_server` report/lead/dismiss/applied/status tools, morning-report delivery, `/announce` | the morning after a hunt, starting `akane dev --speak` speaks the summary once and shows the full report; "dismiss 2" and "I applied to 1" work and show up in the app |
| J3 | tailoring: `start_tailoring`, `tailor-watch`, clarifying questions in chat, accept edits, Word resume and cover letter in the job's folder, invented-fact check | "tailor my resume for 3" → "On it" → any questions asked in chat → announced → Word files with the original formatting, nothing invented |
| J4 | `akane schedule install` (nightly hunt), `start_hunt` on demand | the hunt runs unattended overnight; "find me jobs" mid-day starts one and announces the results |

This moves ahead of the main spec's notebook work (Phase 3). The
announcement pathway it builds is reused by Phase 3 later.

## 9. Left to the builder

- Module and function names; how the hunt prompt is worded; JSON-repair
  tactics.
- Exact launchd plist details and how missed runs are handled (launchd runs a
  missed `StartCalendarInterval` on wake; that's acceptable).
- How the "Morning report" stream is identified across restarts.
- Test strategy, following the repos' conventions. Integration tests never call
  the real Claude CLI or hit real job sites; they fake the CLI's output and the
  link checks.

## 10. Calls made by the designer (check these)

- pnd-job-search is the engine. Akane reaches it only through its REST API, via an akane-repo tool server.
- The app's backend runs as an always-on launchd agent (`akane jobs-app install`); Postgres runs via `brew services`.
- The app's `claude` calls get the API-key-stripping billing guard (small pnd-job-search change).
- Criteria live in `config.local.yaml` (`job_hunt:`), not `config.yaml`, because they're personal.
- A nightly launchd job runs `akane hunt` at 04:00. JSearch queries are capped at 6 per hunt (free tier).
- One Claude call per hunt screens and ranks all new postings.
- Pay below $25/h is dropped only when the posting states it; dead links are dropped; bot-blocked links are flagged.
- The spoken report is ~3 sentences with no links; the full report goes into a "Morning report" chat stream.
- Numbers belong to the latest report; a mid-day hunt appends to it.
- For tailoring, Akane accepts the pipeline's suggested edits automatically and saves the Word files; the app's UI stays available for review.
- Clarifying questions from the pipeline are asked in the "Morning report" chat.
- Background work runs as detached `akane` commands recorded in `jobs.json`; announcements wait for the next start if Akane is down.
- Gig platforms come from a second source: one Claude web-search call per hunt, keyed by URL. Excluded via `job_hunt.kinds` if unwanted.
- Status words map onto the app's stages and status field as in §7.6.
- Clarifying questions never time out; "skip the questions" proceeds without answers; waiting jobs appear in each morning report.
- Smaller items: the search parameter is `remote=true`; `changes.md` verifies each edit against the new text; the cover-letter Word file is built by Akane from the app's text; the launchd agent sets the working directory (for `../.env` and `./uploads`) and PATH (for `claude`); `job_search_server` lives in pnd-mcp's `integrations/servers/` (servers resolve inside `runtime/`), generic over a configurable base URL; announcement and stream changes are pnd-mcp commits plus a submodule bump.
