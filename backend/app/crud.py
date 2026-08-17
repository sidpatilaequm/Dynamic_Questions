"""Query helpers and the rules that decide whether a submission is complete."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import models, schemas
from .models import QuestionType


# --------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------
def get_process(db: Session, process_id: int) -> models.Process | None:
    stmt = (
        select(models.Process)
        .where(models.Process.id == process_id)
        .options(
            selectinload(models.Process.sections)
            .selectinload(models.Section.questions)
            .selectinload(models.Question.options)
        )
        # The session keeps objects alive after commit (expire_on_commit=False),
        # so ask the loader to overwrite what it already holds. Without this a
        # reorder would return the ordering the session cached earlier.
        .execution_options(populate_existing=True)
    )
    return db.execute(stmt).scalar_one_or_none()


def count_responses(db: Session, process_id: int) -> int:
    stmt = select(func.count(models.Response.id)).where(
        models.Response.process_id == process_id
    )
    return db.execute(stmt).scalar_one()


def list_processes(db: Session) -> list[schemas.ProcessSummary]:
    processes = (
        db.execute(select(models.Process).order_by(models.Process.updated_at.desc()))
        .scalars()
        .all()
    )

    section_counts = dict(
        db.execute(
            select(models.Section.process_id, func.count(models.Section.id)).group_by(
                models.Section.process_id
            )
        ).all()
    )
    question_counts = dict(
        db.execute(
            select(models.Section.process_id, func.count(models.Question.id))
            .join(models.Question, models.Question.section_id == models.Section.id)
            .group_by(models.Section.process_id)
        ).all()
    )
    response_counts = dict(
        db.execute(
            select(models.Response.process_id, func.count(models.Response.id)).group_by(
                models.Response.process_id
            )
        ).all()
    )

    return [
        schemas.ProcessSummary(
            id=p.id,
            name=p.name,
            description=p.description,
            status=p.status,
            created_at=p.created_at,
            updated_at=p.updated_at,
            section_count=section_counts.get(p.id, 0),
            question_count=question_counts.get(p.id, 0),
            response_count=response_counts.get(p.id, 0),
        )
        for p in processes
    ]


def next_position(db: Session, model, field, parent_id: int) -> int:
    stmt = select(func.coalesce(func.max(model.position), -1)).where(field == parent_id)
    return db.execute(stmt).scalar_one() + 1


# --------------------------------------------------------------------
# Writing questions
# --------------------------------------------------------------------
def apply_question_payload(question: models.Question, payload: schemas.QuestionIn) -> None:
    """Copy a validated payload onto a question, rebuilding its options."""
    question.prompt = payload.prompt.strip()
    question.help_text = payload.help_text
    question.question_type = payload.question_type
    question.is_mandatory = payload.is_mandatory

    if payload.question_type == QuestionType.short_text:
        question.max_length = payload.max_length
        question.min_selections = None
        question.max_selections = None
        question.options = []
        return

    question.max_length = None
    question.min_selections = (
        payload.min_selections if payload.question_type == QuestionType.multi_choice else None
    )
    question.max_selections = (
        payload.max_selections if payload.question_type == QuestionType.multi_choice else None
    )
    question.options = [
        models.QuestionOption(label=opt.label.strip(), position=i)
        for i, opt in enumerate(payload.options)
    ]


# --------------------------------------------------------------------
# Submissions
# --------------------------------------------------------------------
def validate_submission(
    process: models.Process, payload: schemas.ResponseIn
) -> dict[str, str]:
    """Return {question_id: message} for everything that needs fixing.

    An empty dict means the submission can be stored. Mandatory questions must
    be answered; optional ones are only checked when the respondent actually
    answered them.
    """
    questions = {q.id: q for s in process.sections for q in s.questions}
    errors: dict[str, str] = {}

    submitted: dict[int, schemas.AnswerIn] = {}
    for answer in payload.answers:
        if answer.question_id not in questions:
            errors["form"] = "This form has changed since you opened it. Reload and try again."
            continue
        submitted[answer.question_id] = answer

    if errors:
        return errors

    for qid, question in questions.items():
        answer = submitted.get(qid)
        key = str(qid)

        if question.question_type == QuestionType.short_text:
            text = (answer.text_value or "").strip() if answer else ""
            if not text:
                if question.is_mandatory:
                    errors[key] = "This question needs an answer."
                continue
            if question.max_length and len(text) > question.max_length:
                errors[key] = f"Keep this under {question.max_length} characters."
            continue

        valid_option_ids = {o.id for o in question.options}
        chosen = list(dict.fromkeys(answer.option_ids)) if answer else []

        if any(oid not in valid_option_ids for oid in chosen):
            errors[key] = "One of the choices is no longer on this form. Reload and try again."
            continue

        if not chosen:
            if question.is_mandatory:
                errors[key] = (
                    "Pick an option."
                    if question.question_type == QuestionType.single_choice
                    else "Pick at least one option."
                )
            continue

        if question.question_type == QuestionType.single_choice:
            if len(chosen) > 1:
                errors[key] = "Only one option can be picked here."
            continue

        lo = question.min_selections or (1 if question.is_mandatory else 0)
        if len(chosen) < lo:
            errors[key] = f"Pick at least {lo} option{'s' if lo > 1 else ''}."
        elif question.max_selections and len(chosen) > question.max_selections:
            errors[key] = f"Pick no more than {question.max_selections} options."

    return errors


def store_submission(
    db: Session, process: models.Process, payload: schemas.ResponseIn
) -> models.Response:
    questions = {q.id: q for s in process.sections for q in s.questions}

    response = models.Response(
        process_id=process.id,
        respondent_name=(payload.respondent_name or "").strip() or None,
        respondent_email=(payload.respondent_email or "").strip() or None,
    )

    for incoming in payload.answers:
        question = questions[incoming.question_id]
        text = (incoming.text_value or "").strip() or None
        chosen = list(dict.fromkeys(incoming.option_ids))

        if question.question_type == QuestionType.short_text:
            if text is None:
                continue
            response.answers.append(
                models.Answer(question_id=question.id, text_value=text)
            )
            continue

        if not chosen:
            continue
        answer = models.Answer(question_id=question.id)
        answer.selected_options = [
            models.AnswerOption(option_id=oid) for oid in chosen
        ]
        response.answers.append(answer)

    db.add(response)
    db.commit()
    db.refresh(response)
    return response


def serialize_response(
    db: Session, response: models.Response, process: models.Process
) -> schemas.ResponseOut:
    questions = {q.id: q for s in process.sections for q in s.questions}
    ordered_ids = [q.id for s in process.sections for q in s.questions]

    labels = {o.id: o.label for q in questions.values() for o in q.options}
    by_question = {a.question_id: a for a in response.answers}

    answers: list[schemas.AnswerOut] = []
    for qid in ordered_ids:
        question = questions[qid]
        answer = by_question.get(qid)
        answers.append(
            schemas.AnswerOut(
                question_id=qid,
                prompt=question.prompt,
                question_type=question.question_type,
                is_mandatory=question.is_mandatory,
                text_value=answer.text_value if answer else None,
                selected_labels=(
                    [labels.get(so.option_id, "(removed)") for so in answer.selected_options]
                    if answer
                    else []
                ),
            )
        )

    return schemas.ResponseOut(
        id=response.id,
        process_id=response.process_id,
        respondent_name=response.respondent_name,
        respondent_email=response.respondent_email,
        submitted_at=response.submitted_at,
        answers=answers,
    )
