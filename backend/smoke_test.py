"""End-to-end smoke test. Runs against a throwaway SQLite file.

    cd backend && DATABASE_URL=sqlite:///./smoke.db python smoke_test.py
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./smoke.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
client = TestClient(app)


def ok(label, condition, extra=""):
    print(f"{'PASS' if condition else 'FAIL'}  {label} {extra}")
    assert condition, label


# --- build a process -------------------------------------------------
r = client.post("/api/processes", json={"name": "Vendor onboarding"})
ok("create process", r.status_code == 201)
process = r.json()
pid = process["id"]
ok("starts with one section", len(process["sections"]) == 1)

s1 = process["sections"][0]["id"]
r = client.put(f"/api/sections/{s1}", json={"title": "Company details"})
ok("rename section", r.status_code == 200)

r = client.post(f"/api/processes/{pid}/sections", json={"title": "Compliance"})
ok("add second section", r.status_code == 201)
s2 = r.json()["sections"][1]["id"]

# --- questions of every type ----------------------------------------
r = client.post(
    f"/api/sections/{s1}/questions",
    json={
        "prompt": "Registered company name",
        "question_type": "short_text",
        "is_mandatory": True,
        "max_length": 120,
    },
)
ok("mandatory short answer", r.status_code == 201)

r = client.post(
    f"/api/sections/{s1}/questions",
    json={
        "prompt": "Primary country",
        "question_type": "single_choice",
        "is_mandatory": True,
        "options": [{"label": "India"}, {"label": "Singapore"}],
    },
)
ok("single choice", r.status_code == 201)

r = client.post(
    f"/api/sections/{s2}/questions",
    json={
        "prompt": "Certifications held",
        "question_type": "multi_choice",
        "is_mandatory": False,
        "max_selections": 2,
        "options": [{"label": "ISO 9001"}, {"label": "ISO 27001"}, {"label": "SOC 2"}],
    },
)
ok("optional multiple choice", r.status_code == 201)

r = client.post(
    f"/api/sections/{s2}/questions",
    json={"prompt": "Bad", "question_type": "single_choice", "options": [{"label": "Only one"}]},
)
ok("rejects choice question with one option", r.status_code == 400, r.json().get("detail", ""))

detail = client.get(f"/api/processes/{pid}").json()
q_name = detail["sections"][0]["questions"][0]["id"]
q_country = detail["sections"][0]["questions"][1]["id"]
q_certs = detail["sections"][1]["questions"][0]["id"]
country_opts = [o["id"] for o in detail["sections"][0]["questions"][1]["options"]]
cert_opts = [o["id"] for o in detail["sections"][1]["questions"][0]["options"]]

# --- reordering ------------------------------------------------------
r = client.put(
    f"/api/sections/{s1}/questions/order", json={"question_ids": [q_country, q_name]}
)
ok("reorder within a section", [q["id"] for q in r.json()["sections"][0]["questions"]] == [q_country, q_name])

r = client.put(
    f"/api/sections/{s2}/questions/order", json={"question_ids": [q_certs, q_name]}
)
moved = r.json()
ok(
    "move a question across sections",
    [q["id"] for q in moved["sections"][0]["questions"]] == [q_country]
    and [q["id"] for q in moved["sections"][1]["questions"]] == [q_certs, q_name],
)
ok("positions closed up", moved["sections"][0]["questions"][0]["position"] == 0)

# put it back so the form reads sensibly
client.put(f"/api/sections/{s1}/questions/order", json={"question_ids": [q_name, q_country]})

r = client.put(f"/api/processes/{pid}/sections/order", json={"section_ids": [s2, s1]})
ok("reorder sections", [s["id"] for s in r.json()["sections"]] == [s2, s1])
client.put(f"/api/processes/{pid}/sections/order", json={"section_ids": [s1, s2]})

# --- responses -------------------------------------------------------
submission = {"respondent_name": "Asha", "answers": [{"question_id": q_name, "text_value": "Acme Pvt Ltd"}]}
r = client.post(f"/api/processes/{pid}/responses", json=submission)
ok("draft process refuses responses", r.status_code == 400)

client.put(f"/api/processes/{pid}", json={"name": "Vendor onboarding", "status": "published"})

r = client.post(f"/api/processes/{pid}/responses", json=submission)
ok("mandatory single choice is enforced", r.status_code == 422)
ok("error is keyed by question", str(q_country) in r.json()["detail"]["errors"])

r = client.post(
    f"/api/processes/{pid}/responses",
    json={
        "answers": [
            {"question_id": q_name, "text_value": "   "},
            {"question_id": q_country, "option_ids": country_opts},
        ]
    },
)
errors = r.json()["detail"]["errors"]
ok("blank text fails a mandatory question", str(q_name) in errors)
ok("single choice rejects two picks", str(q_country) in errors)

r = client.post(
    f"/api/processes/{pid}/responses",
    json={
        "answers": [
            {"question_id": q_name, "text_value": "Acme"},
            {"question_id": q_country, "option_ids": [country_opts[0]]},
            {"question_id": q_certs, "option_ids": cert_opts},
        ]
    },
)
ok("max_selections is enforced", r.status_code == 422 and str(q_certs) in r.json()["detail"]["errors"])

r = client.post(
    f"/api/processes/{pid}/responses",
    json={
        "respondent_name": "Asha Rao",
        "respondent_email": "asha@example.com",
        "answers": [
            {"question_id": q_name, "text_value": "Acme Pvt Ltd"},
            {"question_id": q_country, "option_ids": [country_opts[0]]},
            {"question_id": q_certs, "option_ids": cert_opts[:2]},
        ],
    },
)
ok("valid submission stored", r.status_code == 201, r.text[:200])
stored = r.json()
ok("answers come back in form order", [a["question_id"] for a in stored["answers"]] == [q_name, q_country, q_certs])
ok("labels resolved", stored["answers"][2]["selected_labels"] == ["ISO 9001", "ISO 27001"])

# optional question left blank is fine
r = client.post(
    f"/api/processes/{pid}/responses",
    json={
        "answers": [
            {"question_id": q_name, "text_value": "Beta LLP"},
            {"question_id": q_country, "option_ids": [country_opts[1]]},
        ]
    },
)
ok("optional question may be skipped", r.status_code == 201)

r = client.get(f"/api/processes/{pid}/responses")
ok("list responses", r.status_code == 200 and len(r.json()) == 2)

# --- locking ---------------------------------------------------------
r = client.delete(f"/api/questions/{q_certs}")
ok("editing locks once responses exist", r.status_code == 409)

r = client.put(f"/api/processes/{pid}", json={"name": "Vendor onboarding 2026", "status": "closed"})
ok("renaming still allowed while locked", r.status_code == 200)

r = client.post(f"/api/processes/{pid}/duplicate")
ok("duplicate is unlocked", r.status_code == 201 and r.json()["locked"] is False)
ok("duplicate keeps the questions", sum(len(s["questions"]) for s in r.json()["sections"]) == 3)

summaries = client.get("/api/processes").json()
mine = next(s for s in summaries if s["id"] == pid)
ok("summary counts", mine["question_count"] == 3 and mine["response_count"] == 2)

print("\nAll checks passed.")
