# Source Audit

## Source used

TEDUH, Jabatan Perumahan Negara, Kementerian Perumahan dan Kerajaan Tempatan:

- Project search: <https://teduh.kpkt.gov.my/semakan-status-kemajuan>
- Search request: `GET /api/projek-swasta`
- Project detail: `GET /api/projek-swasta/{kod_projek}`
- Unit detail: `GET /api/unit-projek-swasta/{kod_projek}`
- Robots instructions: <https://teduh.kpkt.gov.my/robots.txt>

## Access method

The TEDUH web application makes unauthenticated public `GET` requests and receives JSON. The project uses the same public read-only request structure sequentially, with caching and at least 1.1 seconds between requests by default. Live responses inspected on 2026-08-16 advertised a limit of 60 requests per minute. The client also backs off explicitly after HTTP 429 responses. It does not bypass authentication, CAPTCHA, or access controls.

The site's robots file was inspected on 2026-08-16 and contained no disallowed paths. This is not a data licence. No explicit TEDUH data-reuse licence was located during discovery, so this proof is local and does not claim redistribution rights.

## Official provenance and displayed date

TEDUH states that private developer and project information originates from the Housing Integrated Management System (HIMS). The current frontend generates the displayed “updated through” date as the browser's previous calendar day. The detail JSON does not return an authoritative `updated_until` field.

Accordingly:

- `snapshot_date` is the local observation/retrieval date.
- `source_dataset_as_of` records the date TEDUH's frontend would display.
- `retrieved_at` records the actual local retrieval time.
- The displayed HIMS date must not be interpreted as a guaranteed transaction timestamp for every row.

## HIMS unit-data eligibility cutoff

TEDUH states on its public unit pages that its unit information is based on developer updates in HIMS beginning on 1 January 2022. Projects predating that boundary can remain visible in today's status snapshot while lacking a complete and comparable HIMS unit history.

The processed dataset therefore excludes legacy projects using this deterministic rule:

1. Use `pjb.tarikhPjbPertama` (the first PJB/SPA date) when it is available.
2. Otherwise use `projek.permitMula` as the fallback, which retains new/not-started projects that do not yet have a first SPA.
3. Include the project only when that reference date is on or after `2022-01-01`.
4. Exclude a project when neither date is available.

The first SPA date takes precedence over the permit date so that an old project is not made eligible merely because its advertising permit was renewed after 2022.

## Public request structure

The search request uses these parameters:

- `page`
- `search_type=projek`
- `state` (the configured TEDUH state ID for the selected region)
- `statusProjek` (`0`, `1`, `2`, `3`, `5`, or `7`)

TEDUH currently performs pagination on the server and returns `current_page`, `last_page`, `per_page`, and `total`. The server currently returns 20 rows per page.

## Available data

Project details include the project and developer identifiers, names, permit, permit dates, state, district, unit summary, PJB information, overall project status, construction/type rows, price ranges, CCC/CFO values, and VP values.

Unit responses include unit number, development-component identifier, property group, availability status, sales status, quota fields, listed price, and SPA price.

## Known limitations

- Unit information is maintained by developers in HIMS and may be incomplete or delayed.
- The TEDUH page advises the public to confirm unit sales information with the developer.
- Listed prices have TEDUH applicability warnings for projects that have obtained CCC.
- SPA prices are frequently missing.
- District labels are incomplete and geographically inconsistent.
- A live endpoint is not a historical archive. History begins when this application records a project and cannot reconstruct earlier TEDUH states.
- The HIMS cutoff is a comparability rule for this proof, not a claim that older project permits, CCC/CFO records, or other historical facts are invalid.
- Public response schemas may change without notice.
- Some endpoints may return no unit records even when a project-level total is reported.
