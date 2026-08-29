"""Query helpers and the rules that decide whether a submission is complete."""

import datetime as _datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import models, schemas
from .models import ColumnType, QuestionType


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _question_is_visible(question: "models.Question", submitted: dict[int, "schemas.AnswerIn"]) -> bool:
    """A question with no depends_on_* is always visible. Otherwise it's only visible when the
    respondent picked depends_on_option_id on depends_on_question_id — same rule the frontends
    use to decide whether to render it at all, checked again here since the API can't trust the
    client to have actually hidden it."""
    if question.depends_on_question_id is None:
        return True
    dep_answer = submitted.get(question.depends_on_question_id)
    if dep_answer is None:
        return False
    return question.depends_on_option_id in dep_answer.option_ids


def _cell_is_valid(column: "models.QuestionColumn", value: str) -> bool:
    value = value.strip()
    if column.column_type == ColumnType.number:
        try:
            float(value)
            return True
        except ValueError:
            return False
    if column.column_type == ColumnType.date:
        try:
            _datetime.date.fromisoformat(value)
            return True
        except ValueError:
            return False
    if column.column_type == ColumnType.dropdown:
        return value in {opt.label for opt in column.options}
    return True


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
            .selectinload(models.Question.options),
            selectinload(models.Process.sections)
            .selectinload(models.Section.questions)
            .selectinload(models.Question.columns),
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
            external_key=p.external_key,
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
    question.depends_on_question_id = payload.depends_on_question_id
    question.depends_on_option_id = payload.depends_on_option_id

    if payload.question_type == QuestionType.short_text:
        question.max_length = payload.max_length
        question.min_selections = None
        question.max_selections = None
        question.is_dropdown = False
        question.min_value = None
        question.max_value = None
        question.min_rows = None
        question.max_rows = None
        question.options = []
        question.columns = []
        return

    if payload.question_type == QuestionType.file_upload:
        question.max_length = None
        question.min_selections = None
        question.max_selections = None
        question.is_dropdown = False
        question.min_value = None
        question.max_value = None
        question.min_rows = None
        question.max_rows = None
        question.options = []
        question.columns = []
        return

    if payload.question_type == QuestionType.counter:
        question.max_length = None
        question.min_selections = None
        question.max_selections = None
        question.is_dropdown = False
        question.min_value = payload.min_value
        question.max_value = payload.max_value
        question.min_rows = None
        question.max_rows = None
        question.options = []
        question.columns = []
        return

    if payload.question_type == QuestionType.table:
        question.max_length = None
        question.min_selections = None
        question.max_selections = None
        question.is_dropdown = False
        question.min_value = None
        question.max_value = None
        question.min_rows = payload.min_rows
        question.max_rows = payload.max_rows
        question.options = []
        # Reuse a column's id when its label is unchanged, so answers already
        # recorded against it (keyed by column id — see Answer.table_rows) stay
        # pointed at the right column instead of silently going stale.
        existing = {c.label: c.id for c in question.columns}
        question.columns = [
            models.QuestionColumn(
                id=existing.get(col.label.strip()),
                label=col.label.strip(),
                column_type=col.column_type,
                is_required=col.is_required,
                position=i,
                options=[
                    models.QuestionColumnOption(label=opt.label.strip(), position=j)
                    for j, opt in enumerate(col.options)
                ] if col.column_type == ColumnType.dropdown else [],
            )
            for i, col in enumerate(payload.columns)
        ]
        return

    question.max_length = None
    question.min_selections = (
        payload.min_selections if payload.question_type == QuestionType.multi_choice else None
    )
    question.max_selections = (
        payload.max_selections if payload.question_type == QuestionType.multi_choice else None
    )
    question.is_dropdown = (
        payload.is_dropdown if payload.question_type == QuestionType.single_choice else False
    )
    question.min_value = None
    question.max_value = None
    question.min_rows = None
    question.max_rows = None
    question.options = [
        models.QuestionOption(label=opt.label.strip(), position=i)
        for i, opt in enumerate(payload.options)
    ]
    question.columns = []


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

        if not _question_is_visible(question, submitted):
            # Never on the form as far as the respondent could tell — not required, and
            # whatever (if anything) was submitted for it is simply ignored, not validated.
            continue

        if question.question_type == QuestionType.short_text:
            text = (answer.text_value or "").strip() if answer else ""
            if not text:
                if question.is_mandatory:
                    errors[key] = "This question needs an answer."
                continue
            if question.max_length and len(text) > question.max_length:
                errors[key] = f"Keep this under {question.max_length} characters."
            continue

        if question.question_type == QuestionType.file_upload:
            text = (answer.text_value or "").strip() if answer else ""
            if not text and question.is_mandatory:
                errors[key] = "Upload a file for this question."
            continue

        if question.question_type == QuestionType.counter:
            text = (answer.text_value or "").strip() if answer else ""
            if not text:
                if question.is_mandatory:
                    errors[key] = "This question needs a value."
                continue
            try:
                value = int(text)
            except ValueError:
                errors[key] = "This needs to be a whole number."
                continue
            if question.min_value is not None and value < question.min_value:
                errors[key] = f"Must be at least {question.min_value}."
            elif question.max_value is not None and value > question.max_value:
                errors[key] = f"Must be at most {question.max_value}."
            continue

        if question.question_type == QuestionType.table:
            all_rows = answer.rows if answer else []
            rows = [row for row in all_rows if any(v.strip() for v in row.values())]

            if not rows:
                if question.is_mandatory or question.min_rows:
                    floor = question.min_rows or 1
                    errors[key] = f"Add at least {_plural(floor, 'row')}."
                continue
            if question.min_rows and len(rows) < question.min_rows:
                errors[key] = f"Add at least {question.min_rows} rows."
                continue
            if question.max_rows and len(rows) > question.max_rows:
                errors[key] = f"Use no more than {question.max_rows} rows."
                continue

            bad_row = None
            for index, row in enumerate(rows):
                missing = [
                    c.label for c in question.columns
                    if c.is_required and not row.get(str(c.id), "").strip()
                ]
                if missing:
                    bad_row = f"Row {index + 1} still needs: {', '.join(missing)}."
                    break
                bad_col = next(
                    (
                        c for c in question.columns
                        if row.get(str(c.id), "").strip() and not _cell_is_valid(c, row[str(c.id)])
                    ),
                    None,
                )
                if bad_col:
                    if bad_col.column_type == ColumnType.number:
                        kind = "takes a number"
                    elif bad_col.column_type == ColumnType.date:
                        kind = "takes a date"
                    else:
                        kind = "must be one of the listed options"
                    bad_row = f"Row {index + 1}: {bad_col.label} {kind}."
                    break
            if bad_row:
                errors[key] = bad_row
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
    submitted = {a.question_id: a for a in payload.answers}

    response = models.Response(
        process_id=process.id,
        respondent_name=(payload.respondent_name or "").strip() or None,
        respondent_email=(payload.respondent_email or "").strip() or None,
    )

    for incoming in payload.answers:
        question = questions[incoming.question_id]
        if not _question_is_visible(question, submitted):
            continue
        text = (incoming.text_value or "").strip() or None
        chosen = list(dict.fromkeys(incoming.option_ids))

        if question.question_type in (QuestionType.short_text, QuestionType.counter, QuestionType.file_upload):
            if text is None:
                continue
            response.answers.append(
                models.Answer(question_id=question.id, text_value=text)
            )
            continue

        if question.question_type == QuestionType.table:
            rows = [row for row in incoming.rows if any(v.strip() for v in row.values())]
            if not rows:
                continue
            response.answers.append(
                models.Answer(
                    question_id=question.id,
                    table_rows=[{k: v.strip() for k, v in row.items()} for row in rows],
                )
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
        column_labels = {str(c.id): c.label for c in question.columns}
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
                rows=(
                    [
                        {column_labels.get(cid, "(removed)"): value for cid, value in row.items()}
                        for row in (answer.table_rows or [])
                    ]
                    if answer
                    else []
                ),
                column_labels=[c.label for c in question.columns],
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
