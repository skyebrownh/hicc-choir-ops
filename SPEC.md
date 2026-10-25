# HICC Choir Ops: spec

2026-10-20 · Skye Brown

## Problem statement

The choir director plans each week's songs and keeps track of about 35 choir members, mostly from memory, group texts and a plain-text member list her assistant keeps.

- **Planning sets is the biggest weekly effort.** Choosing songs for each service means remembering what was sung recently, who usually leads each song, and who is around. The only record of past sets is buried in group texts sent to the media team.
- **Nobody tracks attendance.** Section leaders (Soprano, Alto, Tenor, Bass) are meant to follow up with their people, but there is no shared list of who has missed rehearsals or services, so drift goes unnoticed.

## Overview

**In one line:** Roster, attendance and weekly song-set planning for the HICC choir, released in two steps: roster and attendance first (v1), then songs and sets (v2).

**Today:** The member list is plain text with the assistant. Attendance isn't taken. Sets are worked out by the director and sent out by group text. Song history exists only in those texts.

**Goal:** One mobile-friendly place where section leaders mark attendance and see who needs a follow-up (v1), and where the director plans sets with each song's history, leads and stats in front of her (v2).

**Success for v1:** For four weeks in a row, section leaders record attendance at every rehearsal and service. A week counts when every non-cancelled Saturday and Sunday event has marks for all sections.

**Success for v2:** For four weeks in a row, the director plans every set in the app instead of from memory and texts. A week counts when its Sunday set exists in the app before that Sunday.

## Users and roles

| Role | Who | How they get in | What they can do |
| --- | --- | --- | --- |
| Admin | The director (not a choir member), her assistant (a member), and Skye as maintainer (not a member). Comfortable with a phone; the director is not technical. | Email sign-in code, stays signed in for 90 days | Everything: roster, accounts, attendance for all events, the Django admin; and, from v2, songs, sets and stats |
| Section leader | One per section, except that the Tenor leader also covers Bass (3 people). All are choir members. | Email sign-in code, stays signed in for 90 days | See the members of their own sections, mark their attendance (except Wednesdays), see attendance rates and follow-up flags for them. No songs, sets or song stats. |

Other choir members don't sign in.

## Scope

### In v1

- Sign-in by emailed code, roles, and account management by admins
- Roster: members, sections, Praise Team, status history (Active / On Break / Inactive), one-time import of the existing list
- Attendance: weekly events created automatically, special events, marking per section, notes, rates by period, follow-up flags
- Hosting on Railway with daily backups from Skye's Mac

### In v2

v2 work can start while v1 is being measured. v2 adds no new roles or hosting.

- Song library: fields, links, default leads, search, a "Needs details" list, one-time import from the ProPresenter library
- Set planning: Sunday and Wednesday templates (special-event sets start empty), leads per slot, "Copy as text"
- Song stats by song, lead and artist, by period
- History: entering past sets, plus a one-time assisted import of about 12 months from the group texts

### Later

- Set recommendations from history, lead availability (Excused marks made ahead) and artist (v3)
- Sign-in by SMS code through Twilio Verify (about $2 a month)
- Lyrics, and searching them
- Rehearsal planning: which songs each rehearsal works on, beyond the Sunday set
- Follow-up notes: recording that a leader contacted a member about absences

### Non-goals

- **Song discovery and other ministries' songs.** A different kind of work, needing outside data; possibly a separate project.
- **A member-facing app.** Members don't sign in; the users are the director, assistant and section leaders.
- **Sending texts or emails to members.** It costs money and duplicates the group chat. Sets are copied into the chat by hand.
- **Charts, keys and band features.** This is a choir tool, and ProPresenter stays the source of truth for lyrics.

## Functional requirements

### Accounts and sign-in

| ID | Requirement |
| --- | --- |
| AC-1 | A user signs in by entering their email address and then a 6-digit code emailed to them. There are no passwords. |
| AC-2 | A code expires after 10 minutes, works once, and stops working after 5 wrong tries. |
| AC-3 | Entering an email that has no account shows a "no account for that email" message, and sends nothing. |
| AC-4 | A signed-in user stays signed in on that device for 90 days, and can sign out. |
| AC-5 | Admins can give a member an account as a section leader for one or more sections, or as an admin; change the role; or remove the account. |
| AC-6 | An admin account can exist without a member record (the director, Skye), so it never appears on attendance sheets. |
| AC-7 | At most 5 codes can be requested per email address per hour, and at most 20 per IP address per hour. Over the limit, the page shows "Too many requests. Please try again later." |
| AC-8 | Every page a signed-in user sees says who is signed in: their member's name, or their email if the account has no member. The Accounts list marks the user's own account "You", and the member dropdown on the account form marks their own member "(you)". |

### Roster

| ID | Requirement |
| --- | --- |
| RO-1 | A member has a name, phone, email, a section (Soprano, Alto, Tenor or Bass), a Praise Team yes/no (both kept with dated history; see RO-6), and notes. |
| RO-2 | A member's status is Active, On Break or Inactive. Each change is saved with its date (today or earlier), and a change must differ from the status in effect on its date and from the next later change. The member's page describes the last change in a sentence and links to the full history, and the Members list groups members by section, showing each one's status, with Active first, then On Break, then Inactive, and alphabetical within each. A new member starts Active unless an admin picks another status. |
| RO-3 | Admins can add and edit members and change their status. Section leaders can view only the members of their own sections (their current section) and cannot edit them. |
| RO-4 | The roster can be filtered by section, status and Praise Team. |
| RO-5 | A one-time import command loads members from a CSV file. It gives each member an Active status, their section and their Praise Team flag, all dated the import day. |
| RO-6 | A member's section and Praise Team changes are saved with their date, and the member's page shows the history. Their current section and Praise Team flag are the latest change of each. |

### Attendance

| ID | Requirement |
| --- | --- |
| AT-1 | Each week's events are created automatically: Wednesday service (Praise Team only), Saturday rehearsal (everyone) and Sunday (everyone; one event covering both services). Events are created for the current week and the next 4 weeks by a scheduled command that is safe to rerun. There is at most one Wednesday, Saturday and Sunday event per date. |
| AT-2 | Admins can add a special event or extra rehearsal with a date, a name, and who's expected: Everyone or Praise Team. Several events can share a date. |
| AT-3 | Admins can cancel an event (no rehearsal this week, for example), which removes it from sheets, rates and flags. |
| AT-4 | An event's sheet lists the members expected at it: Active on that date, listed under the section they were in on that date, and on the Praise Team on that date if the event is Praise Team only. A member with no status on the event's date isn't expected. |
| AT-5 | A section leader marks members of their own sections (by the member's section on the event's date) Present or Excused, before or after the event, and can undo a mark. Admins can mark anyone. Only admins can mark Wednesday services. There is no time limit on marking or undoing. |
| AT-6 | Each line on a sheet can have a free-text note (for example "2nd service only"), visible to admins and to the member's section leader. |
| AT-7 | Once an event's date has passed, an expected member with no mark counts as Absent. |
| AT-8 | Each member's attendance rate shows for a chosen period: last month, last 3 months, last 6 months, last year, or all time. |
| AT-9 | A member who is Absent from 2 expected events in a row is flagged for follow-up on their section leader's and the admins' views. An Excused mark ends the run, so the count starts over. |

### Songs

| ID | Requirement |
| --- | --- |
| SG-1 | A song has a title, original artist, type (Praise & Worship or Choir), tempo (fast, medium or slow), and free-form tags. |
| SG-2 | A song can have any number of links, each a URL with an optional label, shown as one-click buttons on the song and in sets. |
| SG-3 | A song has zero or more default leads. |
| SG-4 | Keyword search matches title, artist and tags, ignoring case, and can be filtered by type and tempo. |
| SG-5 | A "Needs details" list shows songs missing an artist, type or tempo. |
| SG-6 | Only admins can see or change songs. |
| SG-7 | A one-time import command loads song titles from a list (one per line), skipping titles already in the library. Titles match ignoring case. The song screen allows two songs with the same title. |

### Sets

| ID | Requirement |
| --- | --- |
| ST-1 | A set belongs to a date and a kind: Sunday, Wednesday or a named special event. There is at most one Sunday set and one Wednesday set per date. |
| ST-2 | A new Sunday set starts with the slots P&W 1, P&W 2, Choir and Offering. P&W 2 is marked as 2nd service only. |
| ST-3 | A new Wednesday set starts with the slots P&W 1 and P&W 2. A special-event set starts empty, and slots are added freely. |
| ST-4 | Each slot shows a hint (P&W 1: usually fast; P&W 2: usually slow; Offering: usually fast or medium). Hints never block a choice. |
| ST-5 | Choosing a song for a slot fills in the song's default leads. Leads can then be changed for that slot only, and a "Make this the new default" option updates the song too. |
| ST-6 | A slot's leads can be zero or more Active or On Break members, or free-text guest names. A default lead who is Inactive isn't filled in; the slot says so instead. |
| ST-7 | A slot can have a note (for example "2nd service sings X instead"). |
| ST-8 | "Copy as text" copies the set as a plain message (date, then each slot with song and leads) to paste into the group chat. |
| ST-9 | Sets can be created for past dates. |
| ST-10 | Only admins can see or change sets. |

### Stats

| ID | Requirement |
| --- | --- |
| SS-1 | By song: times sung and the date last sung, for a chosen period (same periods as AT-8). |
| SS-2 | A "not sung lately" list: songs not sung in the last N weeks, oldest first. N defaults to 8 weeks and can be changed. |
| SS-3 | By lead: the songs each person has led, and how often, for a chosen period. |
| SS-4 | By artist: each artist's songs, and how often each was sung, for a chosen period. |
| SS-5 | Only admins can see song stats. |

### History import

| ID | Requirement |
| --- | --- |
| HI-1 | A one-time import command loads past sets from a CSV file (date, set kind, slot, song title, leads). Songs it doesn't recognise are created and land on "Needs details". |
| HI-2 | Imported sets can have missing slots, and a slot's leads can be marked "unknown", which is kept separate from "no lead". |
| HI-3 | A lead name that matches no member is imported as a guest name. |

## Key user flows

### Sign in

1. Open the app on a phone and enter an email address.
2. Get an email with a 6-digit code, and enter it.
3. Land on the home page for the role: section leaders see their attendance, admins see the week ahead. (The exact pages are defined in the first sign-in issue.)

### Mark attendance at rehearsal

1. A section leader opens this week's Saturday rehearsal.
2. They see their sections' expected members, with any Excused marks already made.
3. They tap each person who is Present, or mark Excused, adding a note if needed.
4. After the event, anyone still unmarked counts as Absent, and members who are Absent from 2 events in a row show the follow-up flag.

### Follow up

1. A section leader opens their members list.
2. Flagged members appear first, with their rate for the chosen period and their recent marks and notes.
3. They contact the member outside the app (by phone or text).

### Plan a Sunday set

1. The director opens next Sunday and creates its set, which starts with P&W 1, P&W 2, Choir and Offering.
2. For each slot she searches the library (with type, tempo and "last sung" shown), picks a song, and the default leads fill in.
3. She adjusts leads if needed, and ticks "Make this the new default" if the change should stick.
4. She taps "Copy as text" and pastes it into the media team's group chat.

### Bring in a member who's coming back

1. An admin finds the member, who is On Break, and sets them to Active, which is saved with today's date.
2. The member appears on sheets from then on. Their rate never counted the break.

## Business rules

- **Permissions are enforced on the server.** Every page and action checks the role. A section leader asking directly for a song, set, stat or another section's member gets "not found".
- **Attendance is per event, and Sunday is one event.** Two Sunday services make one attendance record; partial attendance goes in the note.
- **Who's expected is fixed when the event happens.** An event's expected list comes from each member's status, section and Praise Team membership on the event's date. All three keep dated history, so later changes never rewrite past rates.
- **Absent is derived, not stored.** A past, expected, unmarked member is Absent. Marking them later (Present or Excused) replaces that.
- **Rates count only events the member was expected at while Active.** A break never lowers a rate, and Wednesdays count only for members on the Praise Team that day.
- **Follow-up flag:** the member's two most recent past expected events are both Absent. An Excused event ends the run, so the count starts over.
- **A song counts once per set.** A Sunday song sung at both services is "sung once" that date.
- **Defaults are copied, not linked.** A slot keeps the leads it was given. Changing a song's default leads never changes past sets.
- **Unknown is not none.** A history slot with "leads unknown" is left out of lead stats; a slot with no lead (the full choir) counts as sung with no lead.
- **Personal data never goes into git.** Member lists, text exports and history CSVs live in a git-ignored folder, and backups stay on Skye's Mac.

## Data model

### Member

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| name | text | |
| phone | text | Optional; used for SMS sign-in later |
| email | text | Optional for members; an account's sign-in email |
| section | choice | Soprano, Alto, Tenor, Bass. Current section: the latest Section change |
| praise_team | yes/no | Current value: the latest Praise Team change |
| notes | text | Optional |

### Status change

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| member | → Member | |
| status | choice | Active, On Break, Inactive |
| effective_on | date | The member's current status is their latest change |

### Section change

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| member | → Member | |
| section | choice | Soprano, Alto, Tenor, Bass |
| effective_on | date | A member's section on a date is their latest change on or before it |

### Praise Team change

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| member | → Member | |
| praise_team | yes/no | |
| effective_on | date | A member's Praise Team flag on a date is their latest change on or before it |

### Account

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key (Django's user) |
| email | text | Unique; where sign-in codes go |
| role | choice | Admin, Section leader |
| member | → Member | Optional: empty for the director and Skye |
| sections | list of sections | Section leaders only; one or more |

### Sign-in code

| Field | Type | Notes |
| --- | --- | --- |
| account | → Account | |
| code | hashed text | Stored hashed, never in plain text |
| expires_at | date-time | 10 minutes after sending |
| attempts | integer | Fails after 5 |

### Event

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| date | date | US Eastern |
| kind | choice | Wednesday service, Saturday rehearsal, Sunday, Special event, Extra rehearsal |
| name | text | Special events and extra rehearsals |
| expected | choice | Everyone, Praise Team |
| cancelled | yes/no | |

### Attendance mark

| Field | Type | Notes |
| --- | --- | --- |
| event | → Event | |
| member | → Member | One per event and member |
| status | choice | Present, Excused, or empty (a note with no mark yet) |
| note | text | Optional |

### Song

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| title | text | |
| artist | text | Optional until filled in |
| type | choice | Praise & Worship, Choir; optional until filled in |
| tempo | choice | Fast, Medium, Slow; optional until filled in |
| tags | list of text | |
| default_leads | → Members | Zero or more |

### Song link

| Field | Type | Notes |
| --- | --- | --- |
| song | → Song | |
| url | URL | |
| label | text | Optional, e.g. "Spotify" |

### Set

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| date | date | |
| kind | choice | Sunday, Wednesday, Special |
| name | text | Special sets |

A special set isn't linked to an Event; its name is typed separately.

### Slot

| Field | Type | Notes |
| --- | --- | --- |
| set | → Set | |
| position | integer | Order in the set |
| kind | choice | P&W 1, P&W 2, Choir, Offering, Other |
| song | → Song | |
| second_service_only | yes/no | True for a Sunday's P&W 2 |
| leads_unknown | yes/no | History only |
| note | text | Optional |

### Slot lead

| Field | Type | Notes |
| --- | --- | --- |
| slot | → Slot | |
| member | → Member | Empty for a guest |
| guest_name | text | When there's no member |

Leaves room for later: lyrics on Song, a rehearsal-plan link from Event to songs, follow-up notes against members, and an SMS sign-in path alongside email codes (the phone is already on Member).

## Non-functional requirements

- **Mobile first.** Designed at 375 px wide first, and tested on iPhone Safari and Android Chrome. 16 px text at every width (this also stops iPhone Safari zooming into inputs), with tap targets at least 44 px. Contrast meets WCAG AA.
- **Plain language.** Labels read like a person talking, with no jargon.
- **Accessible.** Every input has a label, and attendance marking works with a keyboard and screen reader.
- **Fast.** Pages load in under 2 seconds on mobile data, and the app never sleeps or wakes slowly.
- **Secure enough.** HTTPS everywhere; the server checks roles on every request; codes are hashed; there's a sign-in rate limit (AC-7); there are no secrets in code. Personal data never goes into git or logs.
- **Time zone.** Dates and "this week" use US Eastern.
- **Cost.** Under $10 a month above Skye's existing Railway Hobby plan, ideally a few dollars. Check the real usage in Railway's dashboard after the first week. Plus about $11–13 a year for the domain.
- **Backups.** Daily database backups from Skye's Mac, matching heritage-media-availability's setup, with catch-up when the Mac was off and an alert on failure. (Heritage backs up weekly; daily here because attendance changes several times a week.)

## Technical approach

One Django app with server-rendered pages and Postgres on Railway, matching heritage-media-availability so both run, deploy and back up the same way. Heritage is `github.com/skyebrownh/heritage-media-availability` (local: `~/Developer/heritage-media-availability`).

| Layer | Choice | Why |
| --- | --- | --- |
| Backend | Django (Python), managed with uv | Skye's preferred language. Permission rules are readable Python, and Django brings sessions, an ORM, migrations, a test runner and management commands for imports. |
| Admin | Django admin styled with django-unfold | Lets admins (mostly Skye) fix data directly, matching heritage |
| Pages | Django templates + pre-built Tailwind CSS | Server-rendered HTML is fast on phones and has no separate frontend |
| Interactivity | Small vanilla JavaScript, where needed (slot picking, copy to clipboard) | Not enough here to need a framework |
| Database | Postgres on Railway | Matches Skye's other apps |
| Hosting | Railway Hobby (existing plan), served by gunicorn, static files by WhiteNoise | Already paid for and known. Never sleeps. |
| Sign-in email | Resend's HTTPS API, from a shared sending subdomain of a domain Skye buys before the sign-in issue (registrar: Porkbun recommended) | Railway Hobby blocks SMTP. Resend's free plan is 100 emails a day. |
| Sign-in codes | Our own small module, using Django's password hashing and sessions | Avoids a dependency for about 100 lines |
| Backups | A launchd job on Skye's Mac running `pg_dump` through the Railway CLI | Railway Hobby has no backups |

The app is split into three modules: **accounts** (sign-in, roles), **roster** (members, status, events, attendance, rates) and **songs** (songs, sets, stats, history import). Songs depend on roster for leads; roster never depends on songs.

**Alternative:** Supabase (hosted Postgres with built-in sign-in) and a JavaScript frontend, at $0. It lost because all its security sits in database policies, which are harder to get right and test; its free tier pauses after 7 days idle and has no backups; and it can't enforce a 90-day session without the $25 plan.

## Testing approach

- **Good tests:** test behaviour through public paths. Use Django's test client, signed in as a specific role, asking for pages and posting forms, and check what comes back and what's stored. Don't test private helpers or framework behaviour.
- **What gets tested:** every requirement ID has at least one test that names it. Every business rule is tested on the server. Every page has a permission test for each role, especially that section leaders get "not found" for songs, sets, stats and other sections. Rate and flag rules are tested with fixed dates, including breaks, cancelled events, Praise Team–only Wednesdays, and members who changed section or Praise Team. Import commands are tested with small sample files.
- **Not tested automatically:** look and feel, and phone layout (checked by hand on an iPhone); real email delivery through Resend (checked by hand once deployed); the backup script (checked by hand, like heritage's), including a deliberately failed run to prove the alert arrives (channel named when the backup issue is planned); speed (one Lighthouse mobile run per milestone against the 2-second target); accessibility (a keyboard pass and a VoiceOver pass on the attendance sheet); contrast (a WCAG AA check with a browser tool on each page); cost (a look at Railway's dashboard after the first week).
- **Test data:** a `seed <scenario>` command resets a local database to a known state with fake members, as in heritage.
- **Examples to follow:** filled in once the first tests exist.

## Timeline and open questions

| Milestone | Dates | Focus |
| --- | --- | --- |
| v1 Roster & attendance | Oct 21 – Nov 6, 2026 | Deploy, sign-in, roster and import, attendance, rates and flags, backups. Measured for 4 weeks after launch. |
| v2 Songs, sets & history | Nov 9 – Dec 4, 2026 (tentative) | Song library and import, set planning, stats, history import. Starts while v1 is measured; dates are revisited once v1 is live. |
| v3 Recommendations | No date | Set recommendations |

### Open questions

- **Domain:** Skye picks and buys one (Porkbun, one umbrella domain) before the sign-in issue.

## Decisions

- 2026-10-20: Build rather than buy. Planning Center is in use at the church but Skye has no access to it, and no other tool fits.
- 2026-10-20: One project with roster and songs modules over one database, since song leads are members. Discovery and other ministries may become a separate project.
- 2026-10-20: Roster first (v1), even though set planning is the director's biggest pain, because sets need leads from the roster.
- 2026-10-20: Attendance is per date (Sunday is one event), with notes for partial attendance; the director's policy is to attend both services.
- 2026-10-20: Email sign-in codes for v1; SMS through Twilio Verify later.
- 2026-10-20: Railway Hobby and Postgres, to match Skye's other apps. Backups from Skye's Mac.
- 2026-10-20: One umbrella domain with a shared sending subdomain for all of Skye's apps, so Resend's 3-domain free limit covers them all.
- 2026-10-20: Imports (members, songs, history) are one-time commands, not screens, and their data files never go into git.
- 2026-10-20: Status, section and Praise Team each keep dated history, so a past event's expected list and rates never change when a member moves. Skipping history for Praise Team would have rewritten past Wednesdays.
- 2026-10-21: An Excused mark ends a run of absences, so the follow-up flag count starts over (the director's decision). Before, the spec skipped Excused events.
- 2026-10-22: No staging copy on Railway for v1. The app has a handful of users and Skye tests changes locally against a seeded database; a second service and database would add cost and upkeep for little protection. Revisit if a bad deploy ever reaches the choir.
- 2026-10-22: The sign-in page says when an email has no account (AC-3), and the over-the-limit page says "too many requests" (AC-7). The earlier rule of showing the same "check your email" message for everything is dropped: the choir is small and the friendlier message matters more than hiding which emails have accounts.
- 2026-10-23: The IP limit (20 an hour) is higher than the email limit (5 an hour) because the whole choir may share one church wifi address (AC-7).
- 2026-10-23: The director's and her assistant's routine work (members, status, events, attendance, sets, stats) gets our own mobile-first pages, not the Django admin, even though the admin could do some of it for less build effort. Two different looks and vocabularies would be a jarring, error-prone experience for non-technical users, and ease of use for them outranks build efficiency. The Unfold admin stays Skye's tool for maintenance and manual data fixes, and the fallback when something goes wrong.
- 2026-10-24: A status change must actually change the status, compared with the status in effect on its date and with the next later change, so the history never holds pointless rows. The member page shows the last change as a sentence with a link to the full history, because members go on break often and the list would grow. The Members list groups by section and shows status as a badge, rather than grouping by status as well, which would repeat it. The Django admin reaches status changes only through a member, never as a list of everyone's.
- 2026-10-24: v1 is roster and attendance only; songs, sets, stats and history import become v2 (milestones renamed M1/M2/M3 to v1/v2/v3). Roster and attendance stand on their own, and the old v1 success measure couldn't be checked until about January. v2 work starts while v1 is being measured. This changes release order only: still one project, three modules and one database.
- 2026-10-25: The page header says who is signed in (AC-8), and the Accounts pages mark "you", because admins manage accounts (including their own, which they may not demote or remove) and need to see which one is theirs.
