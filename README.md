<img width="1774" height="887" alt="ChatGPT Image Jul 13, 2026, 06_28_13 PM" src="https://github.com/user-attachments/assets/6ebfd737-358e-4deb-9b3b-77124c390e7e" />

# Listen

This app is part of the AIBE Programme. Presented by Akheel Khan (Founder, An Architect, Co-founder Institute of Building Design) Submission by Dirk Cilliers to solve a particular problem using first principle thinking. The app is a pre alpha and still needs major testing.
It Is an offline Windows desktop app that records and transcribes speech (English,
Afrikaans and 90+ other languages), separates speakers, recognises voices it
has heard before, extracts action items and key issues per discussion type,
flags recurring issues across sessions, translates speech to English, and
exports to PDF, Word or Excel.

Everything runs locally on your PC — no cloud account, no API keys, and your
recordings never leave your machine (unless you choose to push sessions to
your own central server on the local network).

## Features

- **Record** from the laptop/desktop microphone, optionally mixed with
  **system audio** (everything the PC plays) — see the Teams/Meet section below.
- **Import** existing audio files (wav, mp3, m4a, mp4, flac, ogg, and more).
- **Transcription** with OpenAI Whisper (via `faster-whisper`), model size
  selectable in Settings (tiny → large-v3). Language auto-detected or fixed.
- **Speaker separation**: voices are clustered automatically and labelled
  Speaker 1, 2, 3… in order of first appearance.
- **Name deduction**: self-introductions ("Hi, I'm John…") are used to name
  speakers automatically where possible.
- **Speaker database**: when you name a speaker you can tick *Remember voice*.
  Their voice profile is stored, and in future recordings they are recognised
  and named automatically.
- **Naming after transcription**: a dialog lets you rename Speaker 1/2/3 to
  real names (with a ▶ button to hear each voice). Speakers stay editable
  afterwards: double-click a Speaker cell for a dropdown of the session's
  speakers (or type a new name), or right-click any transcript line for
  *Rename everywhere* and *Assign this line to*.
- **Re-evaluation**: transcript text and speaker assignments are editable.
  *Save changes* stores your corrections and re-runs the analysis.
- **Discussion types** — Meeting, Brief, General discussion, Interview — each
  formats the summary with its own sections (action items, decisions, key
  issues, key points).
- **Recurring issues**: issues similar to ones raised in earlier sessions are
  flagged in red with the date they were first raised.
- **Filters**: filter the transcript by speaker and the summary by item type
  (tasks/action items, key issues, decisions, key points). Filters combine —
  e.g. show only Sarah's action items — and exports follow the active filter,
  so you can export one person's task list as its own PDF/Word/Excel file.
  *Clear* resets both filters.
- **Export** to **PDF**, **Word (.docx)** or **Excel (.xlsx)** (Excel includes
  Summary, Transcript and Speakers sheets).
- **Central database**: push finished sessions to a shared server on your
  local network so several PCs can collect their transcripts in one place —
  see [Central server](#central-server-shared-database-on-your-network).
- **Afrikaans understood and translated** — transcription, summaries, name
  deduction and English translation all work for Afrikaans; see the
  [Afrikaans support](#afrikaans-support) section below.

## Recording Teams / Google Meet calls

A meeting "bot" that joins a call by invitation requires cloud infrastructure
(an Azure-registered Teams bot or the Google Meet API plus servers), which a
local desktop app cannot provide. Listen uses the standard desktop
approach instead: it captures **your microphone and the system audio** (what
your speakers/headphones play) at the same time. Join the Teams or Meet call
on this PC, press Record in Listen, and both you and all remote
participants are recorded and transcribed — no bot, no plugins, works with any
meeting software. (If you later want a true invite-a-bot participant, services
such as Recall.ai or Fireflies provide that as a cloud API.)

> Always tell participants they are being recorded — this is a legal
> requirement in many jurisdictions.

## Afrikaans support

Listen understands Afrikaans end to end:

- **Transcription** — the Whisper speech engine supports Afrikaans natively.
  Leave **Language** on `auto` in Settings and it is detected automatically,
  or set it to `af` for the best accuracy in mixed or noisy audio.
- **Summaries** — action items ("ek sal die verslag teen Vrydag stuur"),
  key issues ("die grootste probleem is…", "kwessie", "risiko"), decisions
  ("ons het ooreengekom", "besluit", "goedgekeur") and key points
  ("belangrik", "prioriteit", "sperdatum") are recognised in Afrikaans just
  like in English, so an Afrikaans meeting still gets a proper structured
  summary.
- **Recurring issues** — an issue raised in Afrikaans in one meeting and
  worded differently in the next is still matched and flagged.
- **Name deduction** — Afrikaans introductions such as "my naam is Johan" or
  "ek is Johan" name the speaker automatically.
- **Translation to English** — tick **Translate speech to English** in the
  Record/Import dialog to get an English transcript of Afrikaans speech
  directly, or select an existing Afrikaans session and click **Translate to
  English** in the toolbar to re-process its audio into a new
  English-transcript session. (Translation is one-directional: any language →
  English. English → Afrikaans is not supported by the engine.) You can also
  make translation the default in Settings.
- **Model choice matters** — use the `small` Whisper model (the default) or
  larger for Afrikaans; `tiny` and `base` are noticeably weaker in it, and
  `medium` gives the best Afrikaans accuracy if you can accept slower
  processing.

Mixed English/Afrikaans meetings work too: with Language on `auto` Whisper
follows the dominant language, and the summary keywords are recognised in
both languages at once.

## Central server (shared database on your network)

Listen can push finished sessions — transcript, speakers, and the analysed
summary — to a central database hosted on a machine on your local network,
so transcripts from several PCs end up in one place.

**On the host machine** (any PC/server with Python 3, no packages needed —
copy just the one file if you like):

```powershell
python server\central_server.py                    # port 8765, listen_central.db
python server\central_server.py --port 9000 --db D:\data\central.db
python server\central_server.py --api-key mysecret # require a key from clients
```

All pushed sessions are stored in a single SQLite file
(`listen_central.db` by default) next to the script.

**On each desktop PC**: open **Settings → Central server** and enter the
server's URL, e.g. `http://192.168.1.10:8765` (plus the API key if the server
uses one). Then select any session and click **Push to server** in the
toolbar. Pushing the same session again after edits **updates** the central
copy rather than duplicating it, and the local session remembers when it was
last pushed.

The server also answers simple read requests, so other tools can consume the
central data:

```
GET /health              server alive check
GET /api/sessions        list of all stored sessions
GET /api/sessions/<id>   one full session incl. transcript and summary items
```

> The server is meant for a trusted local network. If you need it reachable
> beyond that, put it behind a proper reverse proxy with HTTPS and use
> `--api-key`.

## Setup

### Option A — Installer (recommended for most users)

Download **`Listen-Setup-<version>.exe`** from the
[Releases](https://github.com/dee4dog/listen/releases) page and run it. The
installer bundles Python and every dependency, so **no Python install and no
`pip` is required** — just install and launch Listen from the Start Menu (or
the desktop icon, if you ticked that during setup). Uninstall via
*Settings → Apps* like any other Windows program.

Requirements: Windows 10/11 (64-bit), ~4 GB free disk space for the app and
downloaded models.

### Option B — Run from source (for development)

Requirements: Windows 10/11, Python 3.10+ (`py` launcher), ~4 GB free disk
space for dependencies and models.

```powershell
.\scripts\setup.ps1     # one-time: creates .venv and installs dependencies
.\scripts\run.ps1       # starts the app
```

### Notes

- The first transcription downloads the Whisper model (~500 MB for "small")
  and the speaker-embedding model (~80 MB). Later runs are fully offline.
  This applies to both setup options.
- Everything (database, recordings, models, exports) is stored under
  `%LOCALAPPDATA%\Listen`. Your data lives here regardless of how you
  installed, and it survives uninstalling/reinstalling the app.

### Building the installer yourself

To produce the `Listen-Setup-<version>.exe` from source you need
[Inno Setup 6](https://jrsoftware.org/isdl.php)
(`winget install JRSoftware.InnoSetup`). Then, after running
`.\scripts\setup.ps1` once:

```powershell
.\scripts\build_installer.ps1
```

This freezes the app with PyInstaller and compiles the installer into
`dist_installer\`. Bump `AppVersion` in `scripts\installer.iss` per release.

## Usage

1. **Record** (choose title, discussion type, whether to capture system
   audio, and optionally *Translate speech to English*) or **Import audio…**
   for an existing file.
2. Wait for processing — progress shows in the status bar.
3. The **Name the speakers** dialog opens: type real names over Speaker 1/2/3
   and tick *Remember voice* to store them in the speaker database.
4. Review the transcript (edit text or speaker cells as needed) and the
   summary panel below it; recurring issues are flagged in red.
5. **Save changes** to persist edits and re-run the analysis.
6. **Export PDF / Word / Excel**, and/or **Push to server** to send the
   session to your central database.

## Settings

- **Whisper model** — bigger models are more accurate but slower on CPU
  (`small` is a good balance; try `medium` for difficult audio).
- **Language** — a code like `en`, `af` (Afrikaans), `nl`, or `auto` to
  detect automatically.
- **Translate to English by default** — every new recording/import produces
  an English transcript regardless of the spoken language.
- **Split sensitivity** — lower detects more speakers, higher merges them.
- **Known-voice match threshold** — how confident a match must be before a
  saved speaker name is applied automatically.
- **Central server URL / API key** — where *Push to server* sends sessions.
- **Capture system audio by default** and **default discussion type**.

## Troubleshooting

- **No system audio captured** — make sure sound is playing through the
  default output device; the loopback follows the default speaker.
- **Speakers merged or split wrongly** — adjust *Split sensitivity* and
  re-import the recording, or fix assignments by editing the Speaker column
  and using *Name speakers…*.
- **Slow transcription** — pick a smaller model (`base` or `tiny`) in
  Settings.
- **Poor Afrikaans accuracy** — set Language to `af` explicitly and use the
  `small` model or larger (`medium` is best).
- **Push to server fails** — check the server is running (`GET /health` in a
  browser), the URL includes `http://` and the right port, Windows Firewall
  allows the port on the host, and the API key matches.
- **Antivirus/SmartScreen warnings during setup** — the PyTorch download is
  large; allow it to finish.
