import { useRef, useState } from 'react';
import { QUESTION_TYPES } from '../api.js';

let keySeed = 0;
const newOption = (label = '') => ({ key: `opt-${keySeed++}`, label });

function initialDraft(question) {
  if (!question) {
    return {
      prompt: '',
      help_text: '',
      question_type: 'short_text',
      is_mandatory: false,
      max_length: '',
      min_selections: '',
      max_selections: '',
      options: [newOption(), newOption()],
    };
  }
  return {
    prompt: question.prompt,
    help_text: question.help_text ?? '',
    question_type: question.question_type,
    is_mandatory: question.is_mandatory,
    max_length: question.max_length ?? '',
    min_selections: question.min_selections ?? '',
    max_selections: question.max_selections ?? '',
    options: question.options.length
      ? question.options.map((o) => newOption(o.label))
      : [newOption(), newOption()],
  };
}

export default function QuestionEditor({ question, busy, onSave, onCancel }) {
  const [draft, setDraft] = useState(() => initialDraft(question));
  const [problem, setProblem] = useState(null);
  const lastOptionRef = useRef(null);

  const set = (patch) => setDraft((d) => ({ ...d, ...patch }));
  const isChoice = draft.question_type !== 'short_text';
  const isMulti = draft.question_type === 'multi_choice';

  const setOption = (key, label) =>
    set({ options: draft.options.map((o) => (o.key === key ? { ...o, label } : o)) });

  const addOption = () => set({ options: [...draft.options, newOption()] });

  const removeOption = (key) =>
    set({ options: draft.options.filter((o) => o.key !== key) });

  const moveOption = (index, delta) => {
    const target = index + delta;
    if (target < 0 || target >= draft.options.length) return;
    const options = [...draft.options];
    [options[index], options[target]] = [options[target], options[index]];
    set({ options });
  };

  /** Mirrors the checks the API runs, so problems surface before the round trip. */
  const validate = () => {
    if (!draft.prompt.trim()) return 'Write the question itself.';
    if (!isChoice) return null;

    const labels = draft.options.map((o) => o.label.trim()).filter(Boolean);
    if (labels.length < 2) return 'Give this question at least two options.';
    if (new Set(labels.map((l) => l.toLowerCase())).size !== labels.length)
      return 'Two options have the same label.';

    if (isMulti) {
      const lo = draft.min_selections ? Number(draft.min_selections) : null;
      const hi = draft.max_selections ? Number(draft.max_selections) : null;
      if (lo && hi && lo > hi) return 'The minimum cannot be larger than the maximum.';
      if (hi && hi > labels.length) return 'The maximum is higher than the number of options.';
      if (lo && lo > labels.length) return 'The minimum is higher than the number of options.';
    }
    return null;
  };

  const save = () => {
    const found = validate();
    setProblem(found);
    if (found) return;

    const payload = {
      prompt: draft.prompt.trim(),
      help_text: draft.help_text.trim() || null,
      question_type: draft.question_type,
      is_mandatory: draft.is_mandatory,
      max_length: !isChoice && draft.max_length ? Number(draft.max_length) : null,
      min_selections: isMulti && draft.min_selections ? Number(draft.min_selections) : null,
      max_selections: isMulti && draft.max_selections ? Number(draft.max_selections) : null,
      options: isChoice
        ? draft.options
            .map((o) => ({ label: o.label.trim() }))
            .filter((o) => o.label)
        : [],
    };
    onSave(payload);
  };

  return (
    <div className="editor">
      <p className="eyebrow">{question ? 'Editing question' : 'New question'}</p>

      <label className="field">
        <span className="label">Question</span>
        <input
          className="input"
          autoFocus
          placeholder="What do you want to ask?"
          value={draft.prompt}
          onChange={(e) => set({ prompt: e.target.value })}
        />
      </label>

      <label className="field">
        <span className="label">Helper text</span>
        <input
          className="input"
          placeholder="Optional. Sits under the question to explain what a good answer looks like."
          value={draft.help_text}
          onChange={(e) => set({ help_text: e.target.value })}
        />
      </label>

      <fieldset className="field">
        <legend className="label">Answer type</legend>
        <div className="type-picker">
          {QUESTION_TYPES.map((type) => (
            <label
              key={type.value}
              className={`type-option ${draft.question_type === type.value ? 'type-option--on' : ''}`}
            >
              <input
                type="radio"
                name="question_type"
                value={type.value}
                checked={draft.question_type === type.value}
                onChange={() => set({ question_type: type.value })}
              />
              <span className="type-option__name">{type.name}</span>
              <span className="type-option__hint">{type.hint}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <label className="toggle">
        <input
          type="checkbox"
          checked={draft.is_mandatory}
          onChange={(e) => set({ is_mandatory: e.target.checked })}
        />
        <span>
          <strong>Mandatory</strong>
          <span className="muted">
            {' '}
            — the form cannot be submitted until this one is answered.
          </span>
        </span>
      </label>

      {!isChoice && (
        <label className="field field--narrow">
          <span className="label">Character limit</span>
          <input
            className="input"
            type="number"
            min="1"
            max="5000"
            placeholder="No limit"
            value={draft.max_length}
            onChange={(e) => set({ max_length: e.target.value })}
          />
        </label>
      )}

      {isChoice && (
        <div className="field">
          <span className="label">Options</span>
          <ul className="option-editor">
            {draft.options.map((option, index) => (
              <li key={option.key}>
                <span className="code">{index + 1}</span>
                <input
                  className="input"
                  placeholder={`Option ${index + 1}`}
                  value={option.label}
                  ref={index === draft.options.length - 1 ? lastOptionRef : null}
                  onChange={(e) => setOption(option.key, e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      addOption();
                    }
                  }}
                />
                <button
                  className="icon-btn"
                  aria-label="Move option up"
                  title="Move up"
                  disabled={index === 0}
                  onClick={() => moveOption(index, -1)}
                >
                  ↑
                </button>
                <button
                  className="icon-btn"
                  aria-label="Move option down"
                  title="Move down"
                  disabled={index === draft.options.length - 1}
                  onClick={() => moveOption(index, 1)}
                >
                  ↓
                </button>
                <button
                  className="icon-btn icon-btn--danger"
                  aria-label="Remove option"
                  title="Remove"
                  disabled={draft.options.length <= 2}
                  onClick={() => removeOption(option.key)}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
          <button className="btn btn--tiny" onClick={addOption}>
            + Add option
          </button>
        </div>
      )}

      {isMulti && (
        <div className="pair">
          <label className="field field--narrow">
            <span className="label">Pick at least</span>
            <input
              className="input"
              type="number"
              min="1"
              placeholder="No minimum"
              value={draft.min_selections}
              onChange={(e) => set({ min_selections: e.target.value })}
            />
          </label>
          <label className="field field--narrow">
            <span className="label">Pick no more than</span>
            <input
              className="input"
              type="number"
              min="1"
              placeholder="No maximum"
              value={draft.max_selections}
              onChange={(e) => set({ max_selections: e.target.value })}
            />
          </label>
        </div>
      )}

      {problem && <p className="alert">{problem}</p>}

      <div className="row-actions">
        <button className="btn btn--primary" onClick={save} disabled={busy}>
          {busy ? 'Saving…' : question ? 'Save changes' : 'Add question'}
        </button>
        <button className="btn btn--ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </div>
  );
}
