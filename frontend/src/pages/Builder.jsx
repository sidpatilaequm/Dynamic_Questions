import { useState } from 'react';
import { api } from '../api.js';
import QuestionCard from '../components/QuestionCard.jsx';
import QuestionEditor from '../components/QuestionEditor.jsx';

/** Uncontrolled text input that saves when it loses focus. */
function InlineText({ value, onSave, className, ...rest }) {
  return (
    <input
      className={className}
      defaultValue={value ?? ''}
      onBlur={(e) => {
        const next = e.target.value.trim();
        if (next && next !== (value ?? '')) onSave(next);
        else if (!next) e.target.value = value ?? '';
      }}
      {...rest}
    />
  );
}

export default function Builder({ process, setProcess, onDuplicate }) {
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  // { sectionId, question }  — question === null means "adding a new one"
  const [editing, setEditing] = useState(null);

  const locked = process.locked;

  const run = async (work) => {
    setBusy(true);
    try {
      const updated = await work();
      if (updated) setProcess(updated);
      setError(null);
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  // --- sections ------------------------------------------------------
  const addSection = () =>
    run(() =>
      api.createSection(process.id, {
        title: `Section ${process.sections.length + 1}`,
        description: null,
      }),
    );

  const moveSection = (index, delta) => {
    const ids = process.sections.map((s) => s.id);
    const target = index + delta;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    run(() => api.reorderSections(process.id, ids));
  };

  const deleteSection = (section) => {
    const warning = section.questions.length
      ? `Delete "${section.title}" and its ${section.questions.length} question(s)?`
      : `Delete "${section.title}"?`;
    if (!window.confirm(warning)) return;
    run(() => api.deleteSection(section.id));
  };

  // --- questions -----------------------------------------------------
  const moveQuestion = (section, index, delta) => {
    const ids = section.questions.map((q) => q.id);
    const target = index + delta;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    run(() => api.reorderQuestions(section.id, ids));
  };

  const moveQuestionToSection = (question, targetSectionId) => {
    const target = process.sections.find((s) => s.id === Number(targetSectionId));
    if (!target) return;
    const ids = [...target.questions.map((q) => q.id), question.id];
    run(() => api.reorderQuestions(target.id, ids));
  };

  const deleteQuestion = (question) => {
    if (!window.confirm('Delete this question?')) return;
    run(() => api.deleteQuestion(question.id));
  };

  const saveQuestion = async (payload) => {
    const { sectionId, question } = editing;
    const done = await run(() =>
      question ? api.updateQuestion(question.id, payload) : api.createQuestion(sectionId, payload),
    );
    if (done) setEditing(null);
  };

  return (
    <div className="stack">
      {locked && (
        <div className="banner">
          <div>
            <p className="banner__title">Questions are locked</p>
            <p className="muted">
              {process.response_count} response(s) are stored against this form. Changing the
              questions now would break them. Duplicate the process to carry on editing.
            </p>
          </div>
          <button className="btn btn--primary" onClick={onDuplicate}>
            Duplicate process
          </button>
        </div>
      )}

      {error && <p className="alert">{error}</p>}

      {process.sections.map((section, sIndex) => {
        const addingHere = editing && editing.sectionId === section.id && !editing.question;

        return (
          <section key={section.id} className="section-block">
            <div className="section-tab">
              <span className="code">S{sIndex + 1}</span>
              <InlineText
                className="section-title"
                aria-label="Section title"
                value={section.title}
                onSave={(title) =>
                  run(() =>
                    api.updateSection(section.id, {
                      title,
                      description: section.description ?? null,
                    }),
                  )
                }
              />
              <div className="section-tab__actions">
                <button
                  className="icon-btn"
                  title="Move section up"
                  aria-label="Move section up"
                  disabled={locked || busy || sIndex === 0}
                  onClick={() => moveSection(sIndex, -1)}
                >
                  ↑
                </button>
                <button
                  className="icon-btn"
                  title="Move section down"
                  aria-label="Move section down"
                  disabled={locked || busy || sIndex === process.sections.length - 1}
                  onClick={() => moveSection(sIndex, 1)}
                >
                  ↓
                </button>
                <button
                  className="icon-btn icon-btn--danger"
                  title="Delete section"
                  aria-label="Delete section"
                  disabled={locked || busy}
                  onClick={() => deleteSection(section)}
                >
                  ✕
                </button>
              </div>
            </div>

            <textarea
              className="textarea textarea--quiet"
              rows={1}
              placeholder="Optional note shown above this section."
              defaultValue={section.description ?? ''}
              onBlur={(e) => {
                const next = e.target.value.trim() || null;
                if (next !== (section.description ?? null)) {
                  run(() =>
                    api.updateSection(section.id, { title: section.title, description: next }),
                  );
                }
              }}
            />

            {section.questions.length === 0 && !addingHere && (
              <p className="muted section-empty">
                No questions in this section yet. Add the first one below.
              </p>
            )}

            <ol className="q-list">
              {section.questions.map((question, qIndex) => {
                const isEditing = editing?.question?.id === question.id;
                return (
                  <li key={question.id}>
                    {isEditing ? (
                      <QuestionEditor
                        question={question}
                        busy={busy}
                        onSave={saveQuestion}
                        onCancel={() => setEditing(null)}
                      />
                    ) : (
                      <QuestionCard
                        question={question}
                        code={`S${sIndex + 1}·Q${qIndex + 1}`}
                        locked={locked}
                        busy={busy}
                        isFirst={qIndex === 0}
                        isLast={qIndex === section.questions.length - 1}
                        sections={process.sections}
                        currentSectionId={section.id}
                        onEdit={() => setEditing({ sectionId: section.id, question })}
                        onDelete={() => deleteQuestion(question)}
                        onMove={(delta) => moveQuestion(section, qIndex, delta)}
                        onMoveToSection={(id) => moveQuestionToSection(question, id)}
                      />
                    )}
                  </li>
                );
              })}
            </ol>

            {addingHere ? (
              <QuestionEditor
                question={null}
                busy={busy}
                onSave={saveQuestion}
                onCancel={() => setEditing(null)}
              />
            ) : (
              <button
                className="btn btn--dashed"
                disabled={locked || busy}
                onClick={() => setEditing({ sectionId: section.id, question: null })}
              >
                + Add a question to {section.title}
              </button>
            )}
          </section>
        );
      })}

      <button className="btn btn--dashed btn--wide" disabled={locked || busy} onClick={addSection}>
        + Add a section
      </button>
    </div>
  );
}
