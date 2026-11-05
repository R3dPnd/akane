# Akane — Job Hunt & Resume Tailoring Design

**Date:** 2026-11-04
**Status:** Draft for review
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
- No scraping behind logins (LinkedIn's signed-in pages, etc.); public pages
  only, through Claude's web search and fetch.
- No email or phone delivery of the report in this build.

## 6. Anti-goals (a failure even if it "works")

- **Made-up leads or dead links.** Every lead must have a URL that was fetched
  and loaded during the hunt (§7.2).
- Tailored documents that invent employers, dates, metrics or skills (carried
  over from the main spec §6.8).
- Showing dismissed or applied-to leads again, or reading the same report aloud
  more than once a day.
- Akane offering instead of acting ("would you like me to search?") when asked
  to hunt, tailor, dismiss or mark as applied.
- Claude usage on a billed API key; it goes through the `claude` CLI bridge only.

## 7. Design

### 7.1 Where things live

- **pnd-mcp (generic, persona-agnostic):**
  - `applications_server`: MCP tools (§7.5).
  - The hunt, report and tailoring logic in a service module the server and the
    CLI share.
  - An `announce` event the voice orchestrator speaks when idle, reusing the
    typed-reply speech queue (`_speak_queued`).
- **akane:**
  - An `akane hunt` launcher command that runs one hunt now.
  - `akane schedule install` / `uninstall`, which manage a launchd agent for
    `job_hunt.run_at`; `setup.sh` offers to install it.
  - Config: the agents and server entries, and the `job_hunt:` example in
    `config.local.example.yaml`.
- **Data** under `<data_dir>/applications/`:

```
master/Resume.docx            the master resume (copied from ~/Downloads/Resume.docx, then updated)
leads.json                    every lead ever found, with its status
reports/YYYY-MM-DD.md         each morning report as Markdown
<company>-<role>/             per-application folder (main spec §6.8)
applications.json             application tracker (main spec §6.8)
```

### 7.2 The hunt (`akane hunt`, also run by launchd)

1. Read the master resume as text (python-docx), the `job_hunt:` criteria,
   `user.location`, and the URLs of all known leads.
2. Make **one** `claude` CLI call through the shared bridge, with WebSearch and
   WebFetch allowed and a generous timeout (default 15 min, configurable). The
   prompt asks for up to `max_leads` postings that fit the criteria and the
   resume. They must be real, currently open, and not in the known-URL list.
   Each lead is strict JSON: `{title, org, url, pay, schedule, remote,
   location, kind, fit}`, where `fit` is one sentence tying the lead to the
   resume and schedule.
3. Validate in code, not by trusting the model:
   - parse the JSON, dropping malformed entries;
   - drop any URL already known;
   - **check each URL** (HTTP GET, short timeout, normal browser user agent):
     - drop it on 404/410, a DNS failure or a connection failure (invented or
       dead links);
     - keep and show it on 2xx/3xx;
     - keep it but mark it "couldn't verify, site blocks bots" on 401/403/429
       or a bot challenge, so leads from the big boards (Indeed, LinkedIn,
       Cloudflare-fronted sites) aren't silently dropped;
   - drop leads whose stated pay is clearly below the floor.
4. Append the survivors to `leads.json` with `status: new`, a `found_at` date
   and a daily number (1…n). Write `reports/<today>.md`.
5. Exit 0 even when nothing is found: an empty report says so. A failure (e.g.
   Claude not signed in) is written into the report so the user hears about it
   in the morning instead of silently getting nothing.

*My call:* one CLI call per hunt, not a multi-step agent, matching the main
spec §6.6 rule "one CLI call per job".

### 7.3 The morning report

- **Contents:** a header line, then for each new lead its number, title,
  company or platform, pay, schedule, remote/location, the "fit" line and the
  link. After that, a "Follow-ups" section listing tracked applications still at
  `applied` 7, 14, 21… days after the last status change. So each one comes up
  once a week until the user updates it ("I heard back from Acme", "Acme
  rejected me") or it's `closed`.
- **Spoken version (my call):** about 3 sentences. "Morning. 6 new leads
  overnight. The best three: a remote AI code evaluation contract at about
  forty an hour, …. They're in the chat." Links are never read aloud.
- **On screen:** the full report is posted as an assistant message into a
  work stream named "Morning report" (created if missing). That way it appears
  in the chat, where the user can reply to it, and the numbers work there.
- **When it's delivered (user decision):**
  - automatically, once per day, the first time Akane is ready (orchestrator
    start in `--voice` or `--speak` mode) if today's report hasn't been
    delivered yet;
  - if Akane was already running when the report was written, at the first
    wake word or typed message after that.
  - Delivery is recorded (`reports/<today>.md` front matter, `delivered_at`) so
    it happens once, across restarts. In silent `akane dev` the report is
    posted in the chat but not spoken, and still counts as delivered.
- **On request:** "read my morning report", "show me the leads", "what was
  number 3?" (`get_morning_report`, `get_lead`).

### 7.4 Leads lifecycle

`new` → `shown` once a delivered report included it. From there it becomes
`dismissed` ("dismiss 4"), `applied` ("I applied to 1"; also creates or updates
a tracker entry), or `tailored` (when tailoring finishes). A lead never returns
to `new`.

**Numbering:**
- Numbers belong to the **latest report**, whose header names its date ("Leads
  for Wed Nov 5"). "Number 3" always means number 3 in the latest report. If
  the overnight hunt didn't run, that's the previous report, and its header
  says so.
- A mid-day hunt **appends to today's report**, continuing the numbering (7,
  8, …). Its leads become `shown` when its announcement is delivered.
- Leads from older reports can be referred to by company name.

### 7.5 Tools (`applications_server`)

| Tool | Does |
|---|---|
| `get_morning_report()` | today's report text (or the latest, if none today) |
| `get_lead(n)` | one lead from today's report |
| `list_leads(status?)` | leads by status |
| `dismiss_lead(n)` | mark as dismissed |
| `mark_applied(n)` | mark as applied and record in the tracker |
| `start_hunt()` | run a hunt now, in the background; returns "On it" at once and announces when done |
| `start_tailoring(n?)` | tailor the resume and cover letter for lead n, or the copied posting if no n (main spec §6.8); background; announced when done |
| `make_pdfs(n)` | export that application's documents to PDF through Word |
| `list_applications()` | the tracker |
| `update_application(n_or_company, status)` | set `applied` / `interviewing` / `rejected` / `offer` / `closed` (main spec §6.8) |
| `list_jobs()` | background hunts and tailoring runs: running, done or failed ("is my resume done yet?") |

Background tools (`start_hunt`, `start_tailoring`) **start a detached process**
(`akane hunt`, `akane tailor <lead-or-clipboard>`, the same commands launchd
and the user can run) and return within a second. Because the work is a
separate process, it survives `akane stop` and restarts. Each run records
itself in `<data_dir>/jobs.json` (id, kind, started, status, result path,
error), the start of main spec §6.6's job runner that Phase 3 will extend. When
a run finishes, it POSTs an announcement to the API. The API publishes
`announce`, the orchestrator speaks it when idle, and it's posted into the
"Morning report" stream. If Akane isn't running at that moment, the
announcement waits in `jobs.json` and is delivered (once) the next time she
starts, the same way the morning report is.

### 7.6 Routing: act, don't offer

- **Agents:** `jobs` (`get_morning_report`, `get_lead`, `list_leads`,
  `dismiss_lead`, `mark_applied`, `start_hunt`) and `apply` (`start_tailoring`,
  `make_pdfs`, `list_applications`), enabled.
- **Prompt rule:** "When the user asks to find jobs, tailor a resume, dismiss
  or mark a lead, call the tool immediately. Never ask 'would you like me
  to…?' for these."
- The runtime's promise nudge (shipped earlier) is the backstop.
- Total always-on tool count stays at or under 22, checked by test, so the 8B
  router isn't swamped.

### 7.7 Tailoring

Unchanged from the main spec §6.8: structured edits applied to a copy of the
.docx, nothing invented (checked against the master), a cover letter, a
`changes.md`, and PDF through Word on request. New: the posting can come from a
lead (its URL is fetched by Claude inside the tailoring call) as well as from
the clipboard.

## 8. Phasing

| Step | Delivers | Done when |
|---|---|---|
| J1 | master resume set up (with the user: Starbucks role and UW Tacoma enrollment added), `job_hunt:` config, `akane hunt`, the leads store, link validation, report file | `akane hunt` writes a report of real, loading links that fit §4, and a second run finds no repeats |
| J2 | `applications_server` read and follow-up tools, morning-report delivery (spoken once a day plus the "Morning report" chat stream), `announce` event | starting `akane dev --speak` the morning after a hunt speaks the summary once and shows the full report; "dismiss 2" and "I applied to 1" work by voice and text |
| J3 | `start_tailoring` and `make_pdfs`, background with announcement | "tailor my resume for 3" says "On it", later announces, and leaves a Word resume and cover letter that keep the original formatting and invent nothing |
| J4 | `akane schedule install` (launchd), `start_hunt` on demand | the hunt runs unattended overnight; "find me jobs" mid-day starts one and announces the results |

This moves ahead of the main spec's notebook work (Phase 3), which it doesn't
depend on. It does build Phase 3's announcement pathway (§7.5), which the
notebook jobs can reuse later.

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

- Criteria live in `config.local.yaml` (`job_hunt:`), not `config.yaml`, because they're personal.
- A launchd agent at 04:00 runs the hunt independently of Akane.
- One Claude CLI call per hunt; links are verified by fetching them before they're shown.
- The spoken report is ~3 sentences with no links; the full report goes in a "Morning report" chat stream.
- Lead numbers are per day.
- Pay below $25/h is dropped only when the posting *states* a lower rate; unknown pay is kept and marked "pay not listed".
- Background tools run in threads in the MCP server and announce through a new `announce` API event.
- Gig platforms count as leads (the user didn't object; easy to exclude with `job_hunt.kinds`).
- Background runs are detached processes recorded in `jobs.json`. They survive restarts, and announcements wait for the next start if Akane is down.
- The link check drops 404/410 and unreachable links, and keeps bot-blocked ones flagged "couldn't verify". Closed postings that still return 200 aren't detected in this build.
- Numbers belong to the latest report; a mid-day hunt appends to it.
- `update_application` added; follow-ups repeat weekly until the status changes.
