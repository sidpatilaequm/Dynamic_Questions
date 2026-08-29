"""ORM models. These mirror db/schema.sql one-to-one."""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class QuestionType(str, enum.Enum):
    short_text = "short_text"
    single_choice = "single_choice"
    multi_choice = "multi_choice"
    counter = "counter"
    table = "table"
    file_upload = "file_upload"


class ColumnType(str, enum.Enum):
    text = "text"
    number = "number"
    date = "date"
    dropdown = "dropdown"


class ProcessStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    closed = "closed"


class Process(Base):
    __tablename__ = "processes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProcessStatus] = mapped_column(
        Enum(ProcessStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ProcessStatus.draft,
    )
    # Lets another service look up "the active questionnaire for X" by a stable
    # name instead of a numeric id that shifts every time the process is
    # duplicated. At most one process holds a given key at a time.
    external_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    sections: Mapped[list["Section"]] = relationship(
        back_populates="process",
        cascade="all, delete-orphan",
        order_by="Section.position",
    )
    responses: Mapped[list["Response"]] = relationship(
        back_populates="process",
        cascade="all, delete-orphan",
        order_by="Response.submitted_at.desc()",
    )


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("processes.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    process: Mapped[Process] = relationship(back_populates="sections")
    questions: Mapped[list["Question"]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="Question.position",
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), nullable=False
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    help_text: Mapped[str | None] = mapped_column(String(500))
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_length: Mapped[int | None] = mapped_column(Integer)
    min_selections: Mapped[int | None] = mapped_column(Integer)
    max_selections: Mapped[int | None] = mapped_column(Integer)
    is_dropdown: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    min_value: Mapped[int | None] = mapped_column(Integer)
    max_value: Mapped[int | None] = mapped_column(Integer)
    min_rows: Mapped[int | None] = mapped_column(Integer)
    max_rows: Mapped[int | None] = mapped_column(Integer)
    # Conditional visibility: this question only counts as "on the form" when the respondent
    # picked depends_on_option_id on depends_on_question_id (a single_choice question). Both
    # null (the default) means always visible. ON DELETE SET NULL rather than CASCADE: deleting
    # the question/option this depends on should fall back to "always visible", not silently
    # delete an unrelated question along with it.
    depends_on_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL")
    )
    depends_on_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("question_options.id", ondelete="SET NULL")
    )

    section: Mapped[Section] = relationship(back_populates="questions")
    # foreign_keys explicit: depends_on_option_id is a second FK path between questions and
    # question_options (pointing the other way — "which option this question depends on"), which
    # would otherwise make SQLAlchemy unable to infer which FK this relationship should join on.
    options: Mapped[list["QuestionOption"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionOption.position",
        foreign_keys="QuestionOption.question_id",
    )
    columns: Mapped[list["QuestionColumn"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionColumn.position",
    )


class QuestionOption(Base):
    __tablename__ = "question_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    question: Mapped[Question] = relationship(back_populates="options", foreign_keys=[question_id])


class QuestionColumn(Base):
    """One column definition for a `table`-type question — the respondent fills in
    one row at a time, each row supplying a value per column (see Answer.table_rows)."""

    __tablename__ = "question_columns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    column_type: Mapped[ColumnType] = mapped_column(
        Enum(ColumnType, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ColumnType.text,
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    question: Mapped[Question] = relationship(back_populates="columns")
    options: Mapped[list["QuestionColumnOption"]] = relationship(
        back_populates="column",
        cascade="all, delete-orphan",
        order_by="QuestionColumnOption.position",
    )


class QuestionColumnOption(Base):
    """Choice list for a `dropdown`-type table column — same shape as QuestionOption,
    just scoped to one column instead of one question."""

    __tablename__ = "question_column_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    column_id: Mapped[int] = mapped_column(
        ForeignKey("question_columns.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    column: Mapped[QuestionColumn] = relationship(back_populates="options")


class Response(Base):
    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("processes.id", ondelete="CASCADE"), nullable=False
    )
    respondent_name: Mapped[str | None] = mapped_column(String(200))
    respondent_email: Mapped[str | None] = mapped_column(String(200))
    submitted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    process: Mapped[Process] = relationship(back_populates="responses")
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="response", cascade="all, delete-orphan"
    )


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("response_id", "question_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    response_id: Mapped[int] = mapped_column(
        ForeignKey("responses.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    text_value: Mapped[str | None] = mapped_column(Text)
    # table-type answers only: list of rows, each row a {column_id (as str): cell value}
    # dict — keyed by column id rather than position so a later column reorder/rename
    # can't silently misalign already-stored answers with the wrong column.
    table_rows: Mapped[list | None] = mapped_column(JSON)

    response: Mapped[Response] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship()
    selected_options: Mapped[list["AnswerOption"]] = relationship(
        back_populates="answer", cascade="all, delete-orphan"
    )


class AnswerOption(Base):
    __tablename__ = "answer_options"

    answer_id: Mapped[int] = mapped_column(
        ForeignKey("answers.id", ondelete="CASCADE"), primary_key=True
    )
    option_id: Mapped[int] = mapped_column(
        ForeignKey("question_options.id", ondelete="CASCADE"), primary_key=True
    )

    answer: Mapped[Answer] = relationship(back_populates="selected_options")
    option: Mapped[QuestionOption] = relationship()
