"""Form Studio API.

Middleware between the React app and MySQL. Everything the builder and the
respondent view need lives here.
"""

import os

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import crud, models, schemas
from .database import get_db

app = FastAPI(
    title="Form Studio API",
    version="1.0.0",
    description="Processes, sections, questions and the responses they collect.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if o.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------
def load_process(db: Session, process_id: int) -> models.Process:
    process = crud.get_process(db, process_id)
    if process is None:
        raise HTTPException(404, "That process no longer exists.")
    return process


def require_unlocked(db: Session, process_id: int) -> None:
    """Block structural edits once answers have been recorded.

    Reordering or deleting questions under a stored response would leave the
    saved answers pointing at a form that no longer matches.
    """
    count = crud.count_responses(db, process_id)
    if count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This process has {count} recorded response(s), so its questions are locked. "
            "Duplicate it or clear the responses to keep editing.",
        )


def detail_for(db: Session, process: models.Process) -> schemas.ProcessDetail:
    count = crud.count_responses(db, process.id)
    detail = schemas.ProcessDetail.model_validate(process)
    detail.response_count = count
    detail.locked = count > 0
    return detail


def bad_request(message: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, message)


# --------------------------------------------------------------------
# Processes
# --------------------------------------------------------------------
@app.get("/api/processes", response_model=list[schemas.ProcessSummary], tags=["processes"])
def list_processes(db: Session = Depends(get_db)):
    return crud.list_processes(db)


@app.post(
    "/api/processes",
    response_model=schemas.ProcessDetail,
    status_code=201,
    tags=["processes"],
)
def create_process(payload: schemas.ProcessIn, db: Session = Depends(get_db)):
    process = models.Process(
        name=payload.name.strip(),
        description=payload.description,
        status=payload.status,
    )
    process.sections.append(models.Section(title="Section 1", position=0))
    db.add(process)
    db.commit()
    return detail_for(db, load_process(db, process.id))


@app.get(
    "/api/processes/{process_id}", response_model=schemas.ProcessDetail, tags=["processes"]
)
def read_process(process_id: int, db: Session = Depends(get_db)):
    return detail_for(db, load_process(db, process_id))


@app.put(
    "/api/processes/{process_id}", response_model=schemas.ProcessDetail, tags=["processes"]
)
def update_process(process_id: int, payload: schemas.ProcessIn, db: Session = Depends(get_db)):
    process = load_process(db, process_id)
    process.name = payload.name.strip()
    process.description = payload.description
    process.status = payload.status
    db.commit()
    return detail_for(db, load_process(db, process_id))


@app.delete("/api/processes/{process_id}", status_code=204, tags=["processes"])
def delete_process(process_id: int, db: Session = Depends(get_db)):
    process = load_process(db, process_id)
    require_unlocked(db, process_id)
    db.delete(process)
    db.commit()


@app.post(
    "/api/processes/{process_id}/duplicate",
    response_model=schemas.ProcessDetail,
    status_code=201,
    tags=["processes"],
)
def duplicate_process(process_id: int, db: Session = Depends(get_db)):
    """Copy the form without its responses, so a locked process can move on."""
    source = load_process(db, process_id)
    copy = models.Process(
        name=f"{source.name} (copy)",
        description=source.description,
        status=models.ProcessStatus.draft,
    )
    for section in source.sections:
        new_section = models.Section(
            title=section.title, description=section.description, position=section.position
        )
        for question in section.questions:
            new_section.questions.append(
                models.Question(
                    prompt=question.prompt,
                    help_text=question.help_text,
                    question_type=question.question_type,
                    is_mandatory=question.is_mandatory,
                    position=question.position,
                    max_length=question.max_length,
                    min_selections=question.min_selections,
                    max_selections=question.max_selections,
                    is_dropdown=question.is_dropdown,
                    min_value=question.min_value,
                    max_value=question.max_value,
                    min_rows=question.min_rows,
                    max_rows=question.max_rows,
                    options=[
                        models.QuestionOption(label=o.label, position=o.position)
                        for o in question.options
                    ],
                    columns=[
                        models.QuestionColumn(
                            label=c.label,
                            column_type=c.column_type,
                            is_required=c.is_required,
                            position=c.position,
                        )
                        for c in question.columns
                    ],
                )
            )
        copy.sections.append(new_section)
    db.add(copy)
    db.commit()
    return detail_for(db, load_process(db, copy.id))


@app.patch(
    "/api/processes/{process_id}/activate",
    response_model=schemas.ProcessDetail,
    tags=["processes"],
)
def activate_process(process_id: int, key: str, db: Session = Depends(get_db)):
    """Mark this process as the live one for an integration key (e.g.
    "become_a_supplier"), clearing the key off whichever process held it
    before. Only one process can hold a given key at a time.
    """
    process = load_process(db, process_id)
    if process.status != models.ProcessStatus.published:
        raise bad_request("Publish this process before making it active.")

    previous = db.execute(
        select(models.Process).where(models.Process.external_key == key)
    ).scalar_one_or_none()
    if previous and previous.id != process.id:
        previous.external_key = None
        # Flushed on its own, ahead of the new holder's update below — otherwise SQLAlchemy
        # batches both UPDATEs into one round trip and MySQL can evaluate the unique constraint
        # on processes.external_key before this row's clear has actually landed, raising a
        # spurious duplicate-key error even though the end state is perfectly valid.
        db.flush()

    process.external_key = key
    db.commit()
    return detail_for(db, load_process(db, process_id))


# --------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------
@app.post(
    "/api/processes/{process_id}/sections",
    response_model=schemas.ProcessDetail,
    status_code=201,
    tags=["sections"],
)
def create_section(process_id: int, payload: schemas.SectionIn, db: Session = Depends(get_db)):
    # Adding a section is additive — nothing about it can misalign an already-stored answer,
    # so it stays allowed even once responses exist. Only edits that touch an *existing*
    # question/section (delete_section, update_question, delete_question) stay locked below.
    load_process(db, process_id)
    db.add(
        models.Section(
            process_id=process_id,
            title=payload.title.strip(),
            description=payload.description,
            position=crud.next_position(
                db, models.Section, models.Section.process_id, process_id
            ),
        )
    )
    db.commit()
    return detail_for(db, load_process(db, process_id))


@app.put(
    "/api/sections/{section_id}", response_model=schemas.ProcessDetail, tags=["sections"]
)
def update_section(section_id: int, payload: schemas.SectionIn, db: Session = Depends(get_db)):
    section = db.get(models.Section, section_id)
    if section is None:
        raise HTTPException(404, "That section no longer exists.")
    section.title = payload.title.strip()
    section.description = payload.description
    db.commit()
    return detail_for(db, load_process(db, section.process_id))


@app.delete(
    "/api/sections/{section_id}", response_model=schemas.ProcessDetail, tags=["sections"]
)
def delete_section(section_id: int, db: Session = Depends(get_db)):
    section = db.get(models.Section, section_id)
    if section is None:
        raise HTTPException(404, "That section no longer exists.")
    process_id = section.process_id
    require_unlocked(db, process_id)

    db.delete(section)
    db.flush()
    remaining = (
        db.execute(
            select(models.Section)
            .where(models.Section.process_id == process_id)
            .order_by(models.Section.position)
        )
        .scalars()
        .all()
    )
    for index, item in enumerate(remaining):
        item.position = index
    db.commit()
    return detail_for(db, load_process(db, process_id))


@app.put(
    "/api/processes/{process_id}/sections/order",
    response_model=schemas.ProcessDetail,
    tags=["sections"],
)
def reorder_sections(
    process_id: int, payload: schemas.SectionOrderIn, db: Session = Depends(get_db)
):
    process = load_process(db, process_id)
    # Reordering doesn't touch any question/option id, so it can't misalign a stored answer —
    # allowed even once responses exist, same reasoning as create_section above.

    known = {s.id: s for s in process.sections}
    if set(payload.section_ids) != set(known):
        raise bad_request("The new order must list every section in this process exactly once.")

    for index, section_id in enumerate(payload.section_ids):
        known[section_id].position = index
    db.commit()
    return detail_for(db, load_process(db, process_id))


# --------------------------------------------------------------------
# Questions
# --------------------------------------------------------------------
def _validate_dependency(db: Session, payload: schemas.QuestionIn, process_id: int, question_id: int | None) -> None:
    """Cross-referential checks check_shape() can't do without a DB session: the dependency
    question exists, belongs to the same process, is a single_choice (the only type with a
    fixed, mutually-exclusive answer that "show if X" can key off), isn't this question itself,
    and the chosen option actually belongs to it."""
    if payload.depends_on_question_id is None:
        return
    dep = db.get(models.Question, payload.depends_on_question_id)
    if dep is None or dep.section.process_id != process_id:
        raise bad_request("The question this depends on doesn't exist in this process.")
    if question_id is not None and dep.id == question_id:
        raise bad_request("A question can't depend on itself.")
    if dep.question_type != models.QuestionType.single_choice:
        raise bad_request('Only a "single choice" question can be depended on — pick the Yes/No (or similar) question this should follow.')
    option = db.get(models.QuestionOption, payload.depends_on_option_id)
    if option is None or option.question_id != dep.id:
        raise bad_request("That option doesn't belong to the question this depends on.")


@app.post(
    "/api/sections/{section_id}/questions",
    response_model=schemas.ProcessDetail,
    status_code=201,
    tags=["questions"],
)
def create_question(
    section_id: int, payload: schemas.QuestionIn, db: Session = Depends(get_db)
):
    section = db.get(models.Section, section_id)
    if section is None:
        raise HTTPException(404, "That section no longer exists.")
    # A brand-new question is additive — safe to add even once responses exist, unlike editing
    # or deleting one. It just can't be *mandatory*: existing respondents were never shown it
    # and can't retroactively answer it, so requiring it would permanently strand their answers
    # as "incomplete" with no way to fix that.
    if payload.is_mandatory and crud.count_responses(db, section.process_id):
        raise bad_request(
            "This process already has recorded responses, so a brand-new question can't be "
            "marked mandatory — existing respondents were never shown it and can't retroactively "
            "answer it. Add it as optional, or duplicate the process if this must be required "
            "going forward."
        )

    try:
        payload.check_shape()
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
    _validate_dependency(db, payload, section.process_id, question_id=None)

    question = models.Question(
        section_id=section_id,
        question_type=payload.question_type,
        prompt=payload.prompt.strip(),
        position=crud.next_position(
            db, models.Question, models.Question.section_id, section_id
        ),
    )
    crud.apply_question_payload(question, payload)
    db.add(question)
    db.commit()
    return detail_for(db, load_process(db, section.process_id))


@app.put(
    "/api/questions/{question_id}",
    response_model=schemas.ProcessDetail,
    tags=["questions"],
)
def update_question(
    question_id: int, payload: schemas.QuestionIn, db: Session = Depends(get_db)
):
    question = db.get(models.Question, question_id)
    if question is None:
        raise HTTPException(404, "That question no longer exists.")
    process_id = question.section.process_id
    require_unlocked(db, process_id)

    try:
        payload.check_shape()
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
    _validate_dependency(db, payload, process_id, question_id=question.id)

    crud.apply_question_payload(question, payload)
    db.commit()
    return detail_for(db, load_process(db, process_id))


@app.delete(
    "/api/questions/{question_id}",
    response_model=schemas.ProcessDetail,
    tags=["questions"],
)
def delete_question(question_id: int, db: Session = Depends(get_db)):
    question = db.get(models.Question, question_id)
    if question is None:
        raise HTTPException(404, "That question no longer exists.")
    section_id = question.section_id
    process_id = question.section.process_id
    require_unlocked(db, process_id)

    db.delete(question)
    db.flush()
    remaining = (
        db.execute(
            select(models.Question)
            .where(models.Question.section_id == section_id)
            .order_by(models.Question.position)
        )
        .scalars()
        .all()
    )
    for index, item in enumerate(remaining):
        item.position = index
    db.commit()
    return detail_for(db, load_process(db, process_id))


@app.put(
    "/api/sections/{section_id}/questions/order",
    response_model=schemas.ProcessDetail,
    tags=["questions"],
)
def reorder_questions(
    section_id: int, payload: schemas.QuestionOrderIn, db: Session = Depends(get_db)
):
    """Set the exact contents and order of a section.

    Ids belonging to another section of the same process are moved in, which is
    how a question is dragged from one section to another.
    """
    section = db.get(models.Section, section_id)
    if section is None:
        raise HTTPException(404, "That section no longer exists.")
    process_id = section.process_id
    # Reordering/moving a question between sections never touches its id, options, or column
    # ids — nothing a stored answer references changes — so it stays allowed even once responses
    # exist, same reasoning as the other structural moves above.

    process = load_process(db, process_id)
    in_process = {q.id: q for s in process.sections for q in s.questions}

    unknown = [qid for qid in payload.question_ids if qid not in in_process]
    if unknown:
        raise bad_request("Those questions do not belong to this process.")
    if len(set(payload.question_ids)) != len(payload.question_ids):
        raise bad_request("The new order repeats a question.")

    moved_from = {
        in_process[qid].section_id
        for qid in payload.question_ids
        if in_process[qid].section_id != section_id
    }

    for index, question_id in enumerate(payload.question_ids):
        question = in_process[question_id]
        question.section_id = section_id
        question.position = index

    # Close the gaps left behind in any section a question was moved out of.
    db.flush()
    for source_id in moved_from:
        rest = (
            db.execute(
                select(models.Question)
                .where(models.Question.section_id == source_id)
                .order_by(models.Question.position)
            )
            .scalars()
            .all()
        )
        for index, item in enumerate(rest):
            item.position = index

    db.commit()
    return detail_for(db, load_process(db, process_id))


# --------------------------------------------------------------------
# Responses
# --------------------------------------------------------------------
@app.post(
    "/api/processes/{process_id}/responses",
    response_model=schemas.ResponseOut,
    status_code=201,
    tags=["responses"],
)
def submit_response(
    process_id: int, payload: schemas.ResponseIn, db: Session = Depends(get_db)
):
    process = load_process(db, process_id)

    if process.status == models.ProcessStatus.closed:
        raise bad_request("This process is closed and is no longer taking responses.")
    if process.status == models.ProcessStatus.draft:
        raise bad_request("Publish this process before collecting responses.")
    if not any(s.questions for s in process.sections):
        raise bad_request("This process has no questions yet.")

    errors = crud.validate_submission(process, payload)
    if errors:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"message": "Some answers still need attention.", "errors": errors},
        )

    response = crud.store_submission(db, process, payload)
    return crud.serialize_response(db, response, process)


@app.get(
    "/api/processes/{process_id}/responses",
    response_model=list[schemas.ResponseOut],
    tags=["responses"],
)
def list_responses(process_id: int, db: Session = Depends(get_db)):
    process = load_process(db, process_id)
    responses = (
        db.execute(
            select(models.Response)
            .where(models.Response.process_id == process_id)
            .order_by(models.Response.submitted_at.desc(), models.Response.id.desc())
            .options(
                selectinload(models.Response.answers).selectinload(
                    models.Answer.selected_options
                )
            )
        )
        .scalars()
        .all()
    )
    return [crud.serialize_response(db, r, process) for r in responses]


@app.delete("/api/responses/{response_id}", status_code=204, tags=["responses"])
def delete_response(response_id: int, db: Session = Depends(get_db)):
    response = db.get(models.Response, response_id)
    if response is None:
        raise HTTPException(404, "That response no longer exists.")
    db.delete(response)
    db.commit()


@app.get("/api/health", tags=["meta"])
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok"}
