import { typeInfo } from '../api.js';

export default function QuestionCard({
  question,
  code,
  locked,
  busy,
  isFirst,
  isLast,
  sections,
  currentSectionId,
  onEdit,
  onDelete,
  onMove,
  onMoveToSection,
}) {
  const info = typeInfo(question.question_type);
  const elsewhere = sections.filter((s) => s.id !== currentSectionId);

  return (
    <article className={`q-card ${question.is_mandatory ? 'q-card--required' : ''}`}>
      <div className="q-gutter">
        <span className="code">{code}</span>
        <span className="type-tag">{info.tag}</span>
      </div>

      <div className="q-body">
        <div className="q-head">
          <h3 className="q-prompt">{question.prompt}</h3>
          {question.is_mandatory ? (
            <span className="stamp">Required</span>
          ) : (
            <span className="stamp stamp--optional">Optional</span>
          )}
        </div>

        {question.help_text && <p className="muted">{question.help_text}</p>}

        {question.question_type === 'short_text' ? (
          <p className="q-preview">
            Free text
            {question.max_length ? ` · up to ${question.max_length} characters` : ''}
          </p>
        ) : (
          <ul className="option-preview">
            {question.options.map((option) => (
              <li key={option.id}>
                <span
                  className={
                    question.question_type === 'single_choice' ? 'dot dot--round' : 'dot dot--square'
                  }
                  aria-hidden="true"
                />
                {option.label}
              </li>
            ))}
          </ul>
        )}

        {question.question_type === 'multi_choice' &&
          (question.min_selections || question.max_selections) && (
            <p className="q-preview">
              Pick
              {question.min_selections ? ` at least ${question.min_selections}` : ''}
              {question.min_selections && question.max_selections ? ',' : ''}
              {question.max_selections ? ` no more than ${question.max_selections}` : ''}
            </p>
          )}

        <div className="q-actions">
          <button className="btn btn--tiny" onClick={onEdit} disabled={locked || busy}>
            Edit
          </button>
          <button
            className="icon-btn"
            title="Move up"
            aria-label="Move question up"
            onClick={() => onMove(-1)}
            disabled={locked || busy || isFirst}
          >
            ↑
          </button>
          <button
            className="icon-btn"
            title="Move down"
            aria-label="Move question down"
            onClick={() => onMove(1)}
            disabled={locked || busy || isLast}
          >
            ↓
          </button>

          {elsewhere.length > 0 && (
            <select
              className="select select--tiny"
              value=""
              disabled={locked || busy}
              aria-label="Move question to another section"
              onChange={(e) => e.target.value && onMoveToSection(e.target.value)}
            >
              <option value="">Move to section…</option>
              {elsewhere.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
          )}

          <button
            className="btn btn--tiny btn--danger"
            onClick={onDelete}
            disabled={locked || busy}
          >
            Delete
          </button>
        </div>
      </div>
    </article>
  );
}
