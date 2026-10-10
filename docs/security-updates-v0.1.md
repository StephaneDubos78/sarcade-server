# Updates and security — v0.1 (server)

Spec: « Mises à jour et sécurité » (Obsidian vault), validated on 10 Oct 2026.

## Code components (GitHub)

| What | Where |
|---|---|
| Dependabot: Python (uv.lock), Docker base image, GitHub Actions; security fixes at once, the rest grouped weekly | `.github/dependabot.yml` |
| Automatic merge of minor and patch updates when the CI is green; major versions wait for a review | `.github/workflows/dependabot-automerge.yml` |
| Known vulnerabilities in dependencies (pip-audit) | job `audit` of `ci.yml` |
| Python code analysis (CodeQL) | `.github/workflows/codeql.yml` |
| Pinned dependencies checked against their hashes | `uv.lock`, `Dockerfile` |
| Image: weekly rebuild without cache, Trivy scan (a critical fixed flaw blocks the publication), ghcr.io, Sigstore signature, SBOM (SPDX) attested and attached to releases | `.github/workflows/image.yml` |

To set in the repository (owner): Dependabot alerts and security updates,
secret scanning with push protection, « Allow auto-merge », and a protection
of `main` requiring the checks `test`, `audit` and `demo-integration` —
without required checks GitHub would merge a Dependabot PR without waiting.

## Security journal (Core, free)

Table `security_events`, distinct from the logbook. Each entry is sealed
with the previous one (SHA-256 over the canonical JSON): a modification or a
deletion afterwards breaks the chain (`GET /admin/security-journal/verify`).
Never the content of messages, photos or positions.

Journaled today: refused administration accesses, administration actions
(event creation and settings including the low-bandwidth mode, event closing,
APRS groups, base maps, reference imports, GPX exports, settings of the
administration tool, client packages), writes refused in listen-only or
archived groups, server updates (new version, « Installer maintenant »,
reports of the updater), client versions (invitation, deferred obligation,
refusal, update), bursts of requests or of refused accesses from one address,
retention purges. Accounts, MFA and device enrolment events arrive with
ADR-002 and ADR-003.

Kept **one year** by default (`journal_retention_days`, 30 to 3650), purged
daily; the purge is journaled and the first remaining entry anchors the chain.

## Administration tool

Bearer token `SARCADE_ADMIN_TOKEN` (placed by the operator in `.env`). Without
token the tool is open like the rest of the v0.1 API, until accounts arrive.

- `GET /admin/security-journal?category=&since=&before_seq=&limit=`
- `GET/PATCH /admin/settings`: maintenance windows
  (`{"timezone": "Europe/Paris", "windows": [{"days": [1], "start": "03:00", "end": "05:00"}], "auto_updates_suspended": false}`,
  days 0 = Monday, a window ending before it starts runs over midnight),
  `journal_retention_days`, `clients.min_version`.
- `GET /admin/updates`: installed and available versions, active events,
  current or next window, decision, history.
- `POST /admin/updates/check`, `POST /admin/updates/install-now` (409 during
  an active event).
- `GET /admin/status`: version, Pro modules, SIEM forwarding state.

## Server update

The server checks every day the latest release (`SARCADE_RELEASES_URL`,
GitHub by default; `SARCADE_UPDATE_CHECK=0` to disable). The installation is
done by `docker/updater.sh` on the host, every 5 minutes:

1. `GET /admin/updates/plan` — install only if a newer version exists, **no
   active event**, and in a maintenance window not suspended, or after
   « Installer maintenant ».
2. Sigstore signature of the image checked (workflow `image.yml` of this
   repository) — refused otherwise.
3. Database backup (`pg_dump`) before the migrations.
4. New image, health check; otherwise previous image and database restored.
5. Each step reported (`POST /admin/updates/report`) and journaled.

Server without Internet: `docker/updater.sh --offline sarcade-server-X.Y.Z.tar`
(package made with `cosign save`, checked offline).

**Active event**: not closed, with a device contact (or its creation) in the
last 24 hours. An event left open and forgotten does not block the updates
forever (decision of the owner, 10 Oct 2026).

## Minimal client version

`clients.min_version` set by the administrator. A client sends its version
with `POST /clients/check` (at start, before joining an event) and with each
heartbeat (`client_update` in the answer):

- `invited`: older than the minimum, 2 hours to update (`deadline`);
- `deferred`: 2 hours passed but the device takes part in an active event:
  the obligation waits for the end of the event;
- `required`: the client must update before reconnecting;
- `ok`.

Client packages (Windows, AppImage, APK) can be distributed by the local
server on a network without Internet: `PUT /admin/clients/{platform}/package`,
`GET /clients/latest`, `GET /clients/{platform}/package` (SHA-256 given; the
client checks the platform signature before installing).

## SIEM (SARCADE Pro, module « siem »)

Enabled by `SARCADE_PRO_MODULES=siem` (signed licence later). Formats syslog
RFC 5424 (`SARCADE_SIEM_FORMAT=syslog`, facility « log audit ») or JSON
(`json`). Transports:

- TCP with TLS (RFC 5425, octet counting): `SARCADE_SIEM_HOST`,
  `SARCADE_SIEM_PORT` (6514), `SARCADE_SIEM_CA`; `SARCADE_SIEM_TLS=0` only on a
  trusted local network;
- journal file collected by the SIEM agent: `SARCADE_SIEM_FILE` (may hold a
  few duplicates after an interruption; `seq` identifies them).

Entries stay in the local journal while the SIEM is unreachable and are sent
when it comes back (cursor), without loss.

**Wazuh** (reference): JSON file collected by the Wazuh agent
(`docs/wazuh/ossec-agent-localfile.xml`, encrypted agent link) and rules
`docs/wazuh/sarcade_rules.xml`.

## To check

- Updater, signature and rollback on a real installation with a real signed
  release; offline package.
- Wazuh rules on a real manager.
- Private Enterprise Number of the structured syslog data (32473 is the number
  reserved for documentation).
- Thresholds of suspicious behaviour (50 refused accesses or 1200 requests per
  minute from one address).
