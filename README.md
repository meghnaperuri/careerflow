# CareerFlow — Full-stack job application tracker

An MVP built with React + TypeScript, FastAPI, PostgreSQL, and Docker Compose.

## Run locally

Prerequisite: Docker Desktop with Docker Compose.

```bash
docker compose up --build
```

Open http://localhost:5173. API docs: http://localhost:8000/docs.

## Architecture

```text
React / Vite (:5173) --> FastAPI (:8000) --> PostgreSQL (internal)
```

## Current features
- Add an application (company, role, optional job link)
- View applications grouped by status
- Change status using a dropdown
- Delete applications
- Persist records in PostgreSQL

## Next milestones
1. Add Alembic migrations, API tests, and GitHub Actions.
2. Add authentication and per-user data isolation **before deploying publicly**.
3. Add drag-and-drop, search/filter, analytics, and interview dates.
4. Add production deployment and observability via CloudForge.

## Security note
The credentials in docker-compose.yml are **local development defaults only**. The API has no authentication yet. Do not expose it to the public internet or use real sensitive application details until authentication, authorization, and secret management are added.

## Import applications from your Google Sheet

In your Google Sheet, open the `Sheet1` tab and choose **File → Download → Comma Separated Values (.csv)**. Open CareerFlow at http://localhost:5173 and upload the CSV under **Import your Google Sheet**.

The importer maps columns C/D/K to company/role/status, preserves other tracked fields in `imported_applications.details` and supports safe re-imports keyed by original CSV row number. Blank-company rows are ignored. Original statuses not matching a board stage are preserved in details and shown as `saved` on the board. For best results, don't reorder sheet rows between imports. The source Sheet is never modified.

**Privacy:** the imported records contain recruiter contact details and personal job-search notes. Do not commit the CSV or database dumps to a public repository or deploy the app publicly without authentication.

## Spreadsheet-column editing
The spreadsheet view displays all 16 named headers plus the second CLAUDE LINK column, and the CONTACT-adjacent PHONE NUMBER and MUTUAL columns. The original source also has two blank header cells, which are intentionally omitted. The application editor lets you update all displayed fields, while a separate CareerFlow stage powers the Kanban board. Imported sheet statuses remain preserved as `STATUS (sheet)`.

After replacing starter files, run `docker compose up --build`. Existing imports retain their saved details. To populate the newly supported second CLAUDE LINK column, reimport the original CSV. Do not commit personal CSV files or database exports to GitHub.


## Integration API (local development)

Generate an API key once, in the project directory:

```bash
python3 -c "import secrets; print('CAREERFLOW_API_KEY=' + secrets.token_urlsafe(48))" > .env
docker compose up --build
```

The new authenticated endpoints are `GET /api/applications`, `GET /api/applications/{id}`, `POST /api/applications`, and `PATCH /api/applications/{id}`. Use `Authorization: Bearer <CAREERFLOW_API_KEY>` for each call. All 18 spreadsheet fields are represented through top-level company/role and the `details` object. Duplicate POST requests return HTTP 409 rather than silently inserting a second record. PATCH merges supplied details without clearing other fields.

Example (replace YOUR_KEY with the value in `.env`):

```bash
curl -X POST http://localhost:8000/api/applications \
  -H 'Authorization: Bearer YOUR_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"company":"Example Corp","role":"Software Engineer","status":"applied","details":{"role_id":"EX-123","date":"11/19/2026","location":"Remote"}}'
```

**Important:** The integration API is authenticated, but the existing browser endpoints are not. Docker ports are bound to `127.0.0.1` to keep this build local-only. Do **not** deploy this unchanged to a public server. Cloud access and direct ChatGPT integration are **not** included; they require deployment, HTTPS, authentication for all endpoints, and a supported connection method. Existing database volumes are retained if you run this in the same Compose project directory; renaming the project directory can create a separate volume. Back up your database before replacing files.
