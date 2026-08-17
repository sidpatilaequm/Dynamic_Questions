# Form Studio

Build a **process**, give it **sections**, arrange **questions** inside them, mark which ones
are mandatory, publish it, and collect responses.

- **Frontend** — React 18 + Vite (no router or UI library)
- **Middleware** — FastAPI + SQLAlchemy 2.0
- **Database** — MySQL 8

Three question types are supported:

| Type | Stored as | Respondent sees |
| --- | --- | --- |
| `short_text` | `answers.text_value` | A text field, optionally length-capped |
| `single_choice` | one row in `answer_options` | Radio buttons |
| `multi_choice` | N rows in `answer_options` | Checkboxes, optional min/max picks |

Any question can be flagged mandatory. Optional questions are only validated when the
respondent actually answers them.

---

## Running it

### 1. Database

This app shares its database with the rest of the platform (`multimedia_governance`) rather
than owning a standalone one — `backend_java` reads/writes these same tables directly via JPA
for the seller-facing side of the vendor-registration integration.

```bash
mysql -u root -p multimedia_governance < db/schema.sql
```

This creates all seven tables (if they don't already exist) and one seeded sample process so
there is something to open on first load. `schema.sql` is the source of truth — the
SQLAlchemy models mirror it rather than the other way round.

### 2. API

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set DB_PASSWORD
uvicorn app.main:app --reload
```

Runs on `http://localhost:8000`. Interactive docs at `/docs`.

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env          # VITE_API_URL, defaults to http://localhost:8000
npm run dev
```

Runs on `http://localhost:5173`.

### Smoke test

`backend/smoke_test.py` exercises the whole API against a throwaway SQLite file — no MySQL
needed:

```bash
cd backend
pip install httpx
DATABASE_URL=sqlite:///./smoke.db python smoke_test.py
```

It covers all three question types, reordering within and across sections, mandatory
enforcement, selection limits, the edit lock, and duplication.

---

## Data model

```
processes
└── sections            (position = order within the process)
    └── questions       (position = order within the section)
        └── question_options

responses
└── answers             (one per answered question)
    └── answer_options  (which choices were ticked)
```

Ordering is a plain `position` integer. Rearranging questions is a position rewrite, and
moving a question to a different section is a `section_id` + `position` update — which is
why one endpoint handles both.

Choice answers all flow through `answer_options`, so single and multiple choice share a
storage path. A single-choice answer simply has exactly one row there.

---

## The edit lock

Once a process has stored responses, structural edits return **409**. Reordering or deleting
questions underneath saved answers would leave those answers describing a form that no longer
exists.

Locked: adding, editing, deleting or reordering sections and questions.
Still allowed: renaming the process, editing its description, changing its status.

To keep editing, `POST /api/processes/{id}/duplicate` copies the form without its responses.
The UI surfaces this as a banner with a **Duplicate process** button.

---

## API reference

All routes are under `/api`.

### Processes
| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/processes` | List with section/question/response counts |
| `POST` | `/processes` | Creates with one empty section |
| `GET` | `/processes/{id}` | Full nested form + `locked` flag |
| `PUT` | `/processes/{id}` | Name, description, status |
| `DELETE` | `/processes/{id}` | Cascades to responses |
| `POST` | `/processes/{id}/duplicate` | Copies the form, not the responses |

### Sections
| Method | Path |
| --- | --- |
| `POST` | `/processes/{id}/sections` |
| `PUT` | `/sections/{id}` |
| `DELETE` | `/sections/{id}` |
| `PUT` | `/processes/{id}/sections/order` — body `{ "section_ids": [...] }` |

### Questions
| Method | Path |
| --- | --- |
| `POST` | `/sections/{id}/questions` |
| `PUT` | `/questions/{id}` |
| `DELETE` | `/questions/{id}` |
| `PUT` | `/sections/{id}/questions/order` — body `{ "question_ids": [...] }` |

The order endpoint sets the exact contents of a section. Ids currently belonging to another
section of the same process are moved in, and the gaps they leave behind are closed up.

### Responses
| Method | Path |
| --- | --- |
| `POST` | `/processes/{id}/responses` |
| `GET` | `/processes/{id}/responses` |
| `DELETE` | `/responses/{id}` |

Every mutating endpoint returns the full updated process, so the frontend replaces its state
from one payload instead of refetching.

---

## Validation

**Question definitions** (`schemas.py::check_shape`, enforced on create and update):
choice questions need at least two distinct options; short-answer questions cannot carry
options; multi-choice min/max must be consistent with each other and with the option count.

**Submissions** (`crud.py::validate_submission`): mandatory questions must be answered
(whitespace-only text does not count); single choice accepts exactly one option; multi-choice
respects min/max; option ids must belong to the question. Failures return **422** with

```json
{ "detail": { "message": "...", "errors": { "12": "Pick an option." } } }
```

keyed by question id, so the UI highlights individual fields. The React form applies the same
rules client-side first, so most problems never reach the network.

Draft and closed processes reject submissions outright.

---

## Notes

- `Base.metadata.create_all()` only works if `app.models` has been imported first. Irrelevant
  for MySQL (use `schema.sql`), but it will bite if you bootstrap tables from Python.
- CORS origins are read from the `CORS_ORIGINS` env var, comma-separated.
- The Responses tab exports a CSV with one column per question.
- There is no authentication. Put this behind your own auth before exposing it.

---

## File map

```
db/schema.sql                          MySQL DDL + sample data

backend/
  app/database.py                      Engine, session, DATABASE_URL
  app/models.py                        ORM models
  app/schemas.py                       Pydantic schemas + question-shape rules
  app/crud.py                          Queries, submission validation, serialisation
  app/main.py                          Routes
  smoke_test.py                        End-to-end API test
  requirements.txt / .env.example

frontend/
  src/api.js                           API client, ApiError, question-type table
  src/App.jsx                          Shell + routing state
  src/pages/ProcessList.jsx            Create, open, duplicate, delete
  src/pages/Workspace.jsx              Header, status, tabs
  src/pages/Builder.jsx                Sections, ordering, add/edit/delete
  src/pages/FillForm.jsx               Respondent view + validation
  src/pages/ResponsesView.jsx          Stored submissions + CSV export
  src/components/QuestionCard.jsx      Read-only question with move controls
  src/components/QuestionEditor.jsx    Create/edit form for all three types
  src/styles.css                       Design tokens and layout
```
