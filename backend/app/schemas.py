"""Pydantic v2 schemas: what the API accepts and returns."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import ColumnType, ProcessStatus, QuestionType

ORM = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------
# Options
# --------------------------------------------------------------------
class OptionIn(BaseModel):
    label: str = Field(min_length=1, max_length=300)


class OptionOut(BaseModel):
    model_config = ORM

    id: int
    label: str
    position: int


# --------------------------------------------------------------------
# Table columns
# --------------------------------------------------------------------
class ColumnIn(BaseModel):
    label: str = Field(min_length=1, max_length=300)
    column_type: ColumnType = ColumnType.text
    is_required: bool = False
    options: list[OptionIn] = Field(default_factory=list)  # dropdown columns only


class ColumnOut(BaseModel):
    model_config = ORM

    id: int
    label: str
    column_type: ColumnType
    is_required: bool
    position: int
    options: list[OptionOut] = []


# --------------------------------------------------------------------
# Questions
# --------------------------------------------------------------------
class QuestionIn(BaseModel):
    prompt: str = Field(min_length=1)
    help_text: str | None = Field(default=None, max_length=500)
    question_type: QuestionType
    is_mandatory: bool = False
    max_length: int | None = Field(default=None, ge=1, le=5000)
    min_selections: int | None = Field(default=None, ge=1)
    max_selections: int | None = Field(default=None, ge=1)
    is_dropdown: bool = False
    min_value: int | None = None
    max_value: int | None = None
    min_rows: int | None = Field(default=None, ge=1, le=200)
    max_rows: int | None = Field(default=None, ge=1, le=200)
    options: list[OptionIn] = Field(default_factory=list)
    columns: list[ColumnIn] = Field(default_factory=list)
    # Conditional visibility — both set together or both left None. Cross-referential checks
    # (the target question exists, is single_choice, isn't this question itself, and the option
    # actually belongs to it) need DB access, so those live in main.py's endpoint, not here.
    depends_on_question_id: int | None = None
    depends_on_option_id: int | None = None

    @field_validator("help_text")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        return v.strip() or None if v else None

    def check_shape(self) -> None:
        """Rules a question definition has to satisfy. Raises ValueError."""
        if (self.depends_on_question_id is None) != (self.depends_on_option_id is None):
            raise ValueError("A conditional question needs both a question and an option to depend on.")

        if self.question_type == QuestionType.short_text:
            if self.options:
                raise ValueError("A short answer question cannot carry options.")
            return

        if self.question_type == QuestionType.file_upload:
            if self.options:
                raise ValueError("A file upload question cannot carry options.")
            return

        if self.question_type == QuestionType.counter:
            if self.options:
                raise ValueError("A counter question cannot carry options.")
            if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
                raise ValueError("The minimum cannot be larger than the maximum.")
            return

        if self.question_type == QuestionType.table:
            labels = [c.label.strip() for c in self.columns]
            if len(labels) < 1:
                raise ValueError("Give this table at least one column.")
            if len({label.lower() for label in labels}) != len(labels):
                raise ValueError("Two columns have the same heading.")
            if self.min_rows is not None and self.max_rows is not None and self.min_rows > self.max_rows:
                raise ValueError("The fewest rows cannot be more than the most rows.")
            for c in self.columns:
                col_label = c.label.strip()
                opt_labels = [o.label.strip() for o in c.options]
                if c.column_type == ColumnType.dropdown:
                    if len(opt_labels) < 2:
                        raise ValueError(f'Dropdown column "{col_label}" needs at least two options.')
                    if len({o.lower() for o in opt_labels}) != len(opt_labels):
                        raise ValueError(f'Dropdown column "{col_label}" has two options with the same label.')
                elif opt_labels:
                    raise ValueError(f'Column "{col_label}" is not a dropdown, so it cannot carry options.')
            return

        labels = [o.label.strip() for o in self.options]
        if len(labels) < 2:
            raise ValueError("Give this question at least two options.")
        if len({label.lower() for label in labels}) != len(labels):
            raise ValueError("Two options have the same label.")

        if self.question_type == QuestionType.single_choice:
            if self.min_selections or self.max_selections:
                raise ValueError(
                    "Selection limits only apply to multiple choice questions."
                )
            return

        lo, hi = self.min_selections, self.max_selections
        if lo and hi and lo > hi:
            raise ValueError("The minimum cannot be larger than the maximum.")
        if hi and hi > len(labels):
            raise ValueError("The maximum is higher than the number of options.")
        if lo and lo > len(labels):
            raise ValueError("The minimum is higher than the number of options.")


class QuestionOut(BaseModel):
    model_config = ORM

    id: int
    section_id: int
    prompt: str
    help_text: str | None
    question_type: QuestionType
    is_mandatory: bool
    position: int
    max_length: int | None
    min_selections: int | None
    max_selections: int | None
    is_dropdown: bool
    min_value: int | None
    max_value: int | None
    min_rows: int | None
    max_rows: int | None
    options: list[OptionOut] = []
    columns: list[ColumnOut] = []
    depends_on_question_id: int | None = None
    depends_on_option_id: int | None = None


# --------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------
class SectionIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


class SectionOut(BaseModel):
    model_config = ORM

    id: int
    process_id: int
    title: str
    description: str | None
    position: int
    questions: list[QuestionOut] = []


# --------------------------------------------------------------------
# Processes
# --------------------------------------------------------------------
class ProcessIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: ProcessStatus = ProcessStatus.draft


class ProcessSummary(BaseModel):
    model_config = ORM

    id: int
    name: str
    description: str | None
    status: ProcessStatus
    external_key: str | None = None
    created_at: datetime
    updated_at: datetime
    section_count: int = 0
    question_count: int = 0
    response_count: int = 0


class ProcessDetail(BaseModel):
    model_config = ORM

    id: int
    name: str
    description: str | None
    status: ProcessStatus
    external_key: str | None = None
    created_at: datetime
    updated_at: datetime
    sections: list[SectionOut] = []
    response_count: int = 0
    locked: bool = False


# --------------------------------------------------------------------
# Reordering
# --------------------------------------------------------------------
class SectionOrderIn(BaseModel):
    section_ids: list[int] = Field(min_length=1)


class QuestionOrderIn(BaseModel):
    """The full, ordered list of questions that should end up in a section.

    Question ids that currently live in a different section of the same
    process are moved across, so this doubles as the "move" endpoint.
    """

    question_ids: list[int]


# --------------------------------------------------------------------
# Responses
# --------------------------------------------------------------------
class AnswerIn(BaseModel):
    question_id: int
    text_value: str | None = None
    option_ids: list[int] = Field(default_factory=list)
    # table-type only: one dict per row, keyed by column id (as a string, since
    # JSON object keys are always strings) -> the cell value typed in for that column.
    rows: list[dict[str, str]] = Field(default_factory=list)


class ResponseIn(BaseModel):
    respondent_name: str | None = Field(default=None, max_length=200)
    respondent_email: str | None = Field(default=None, max_length=200)
    answers: list[AnswerIn] = Field(default_factory=list)


class AnswerOut(BaseModel):
    question_id: int
    prompt: str
    question_type: QuestionType
    is_mandatory: bool
    text_value: str | None = None
    selected_labels: list[str] = []
    # table-type only: each row's cell values, keyed by column label (not column id
    # -- this is a read model for display/export, so it should stay legible even
    # after a column is later deleted) alongside the current column headings.
    rows: list[dict[str, str]] = []
    column_labels: list[str] = []


class ResponseOut(BaseModel):
    id: int
    process_id: int
    respondent_name: str | None
    respondent_email: str | None
    submitted_at: datetime
    answers: list[AnswerOut] = []
