import { useMemo, useState } from 'react';
import { api } from '../api.js';

const blankAnswers = (process) => {
  const answers = {};
  for (const section of process.sections) {
    for (const question of section.questions) {
      answers[question.id] = { text: '', options: [] };
    }
  }
  return answers;
};

export default function FillForm({ process, onSubmitted }) {
  const [answers, setAnswers] = useState(() => blankAnswers(process));
  const [who, setWho] = useState({ name: '', email: '' });
  const [errors, setErrors] = useState({});
  const [notice, setNotice] = useState(null);
  const [receipt, setReceipt] = useState(null);
  const [sending, setSending] = useState(false);

  const questions = useMemo(
    () => process.sections.flatMap((s) => s.questions),
    [process],
  );

  const collecting = process.status === 'published';

  const setText = (id, text) =>
    setAnswers((a) => ({ ...a, [id]: { ...a[id], text } }));

  const pickOne = (id, optionId) =>
    setAnswers((a) => ({ ...a, [id]: { ...a[id], options: [optionId] } }));

  const toggleMany = (id, optionId) =>
    setAnswers((a) => {
      const current = a[id].options;
      const options = current.includes(optionId)
        ? current.filter((o) => o !== optionId)
        : [...current, optionId];
      return { ...a, [id]: { ...a[id], options } };
    });

  /** Same rules the API enforces, run first so nothing bounces off the server. */
  const validate = () => {
    const found = {};
    for (const question of questions) {
      const answer = answers[question.id] ?? { text: '', options: [] };

      if (question.question_type === 'short_text') {
        const text = answer.text.trim();
        if (!text) {
          if (question.is_mandatory) found[question.id] = 'This question needs an answer.';
          continue;
        }
        if (question.max_length && text.length > question.max_length) {
          found[question.id] = `Keep this under ${question.max_length} characters.`;
        }
        continue;
      }

      const chosen = answer.options;
      if (chosen.length === 0) {
        if (question.is_mandatory) {
          found[question.id] =
            question.question_type === 'single_choice'
              ? 'Pick an option.'
              : 'Pick at least one option.';
        }
        continue;
      }

      if (question.question_type === 'multi_choice') {
        const lo = question.min_selections ?? (question.is_mandatory ? 1 : 0);
        if (chosen.length < lo) {
          found[question.id] = `Pick at least ${lo} option${lo > 1 ? 's' : ''}.`;
        } else if (question.max_selections && chosen.length > question.max_selections) {
          found[question.id] = `Pick no more than ${question.max_selections} options.`;
        }
      }
    }
    return found;
  };

  const submit = async () => {
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length) {
      setNotice('Some answers still need attention.');
      const first = document.querySelector('.form-question--bad');
      first?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }

    setSending(true);
    try {
      const stored = await api.submitResponse(process.id, {
        respondent_name: who.name.trim() || null,
        respondent_email: who.email.trim() || null,
        answers: questions.map((q) => ({
          question_id: q.id,
          text_value: q.question_type === 'short_text' ? answers[q.id].text : null,
          option_ids: q.question_type === 'short_text' ? [] : answers[q.id].options,
        })),
      });
      setReceipt(stored);
      setNotice(null);
      setErrors({});
      onSubmitted?.();
    } catch (err) {
      setNotice(err.message);
      if (err.fieldErrors) setErrors(err.fieldErrors);
    } finally {
      setSending(false);
    }
  };

  const startAnother = () => {
    setAnswers(blankAnswers(process));
    setWho({ name: '', email: '' });
    setReceipt(null);
    setNotice(null);
  };

  if (receipt) {
    return (
      <div className="card receipt">
        <p className="eyebrow">Response {receipt.id}</p>
        <h2 className="display display--sm">Answers recorded.</h2>
        <p className="muted">
          Saved at {new Date(receipt.submitted_at).toLocaleString()}. You can see it on the
          Responses tab.
        </p>
        <button className="btn btn--primary" onClick={startAnother}>
          Fill in another
        </button>
      </div>
    );
  }

  if (questions.length === 0) {
    return (
      <div className="empty">
        <p className="empty__title">There is nothing to answer yet.</p>
        <p className="muted">Add questions on the Build tab, then come back.</p>
      </div>
    );
  }

  return (
    <div className="stack">
      {!collecting && (
        <div className="banner">
          <div>
            <p className="banner__title">
              {process.status === 'draft' ? 'This process is a draft' : 'This process is closed'}
            </p>
            <p className="muted">
              You can read through the form, but it will not accept a submission until the status
              is set to Published.
            </p>
          </div>
        </div>
      )}

      {process.description && <p className="lede">{process.description}</p>}

      <div className="card who-card">
        <p className="eyebrow">Who is answering</p>
        <div className="pair">
          <label className="field">
            <span className="label">Name</span>
            <input
              className="input"
              value={who.name}
              placeholder="Optional"
              onChange={(e) => setWho({ ...who, name: e.target.value })}
            />
          </label>
          <label className="field">
            <span className="label">Email</span>
            <input
              className="input"
              type="email"
              value={who.email}
              placeholder="Optional"
              onChange={(e) => setWho({ ...who, email: e.target.value })}
            />
          </label>
        </div>
      </div>

      {process.sections.map((section, sIndex) =>
        section.questions.length === 0 ? null : (
          <section key={section.id} className="section-block">
            <div className="section-tab">
              <span className="code">S{sIndex + 1}</span>
              <h2 className="section-title section-title--static">{section.title}</h2>
            </div>
            {section.description && <p className="muted section-note">{section.description}</p>}

            <ol className="q-list">
              {section.questions.map((question, qIndex) => {
                const answer = answers[question.id] ?? { text: '', options: [] };
                const bad = errors[question.id];
                const inputId = `q-${question.id}`;

                return (
                  <li key={question.id}>
                    <div className={`q-card form-question ${bad ? 'form-question--bad' : ''}`}>
                      <div className="q-gutter">
                        <span className="code">
                          S{sIndex + 1}·Q{qIndex + 1}
                        </span>
                      </div>

                      <div className="q-body">
                        <div className="q-head">
                          <label className="q-prompt" htmlFor={inputId}>
                            {question.prompt}
                          </label>
                          {question.is_mandatory && <span className="stamp">Required</span>}
                        </div>

                        {question.help_text && <p className="muted">{question.help_text}</p>}

                        {question.question_type === 'short_text' && (
                          <>
                            <input
                              id={inputId}
                              className="input"
                              maxLength={question.max_length ?? undefined}
                              value={answer.text}
                              onChange={(e) => setText(question.id, e.target.value)}
                            />
                            {question.max_length && (
                              <p className="counter">
                                {answer.text.length} / {question.max_length}
                              </p>
                            )}
                          </>
                        )}

                        {question.question_type === 'single_choice' && (
                          <div className="choices" role="radiogroup" aria-labelledby={inputId}>
                            {question.options.map((option) => (
                              <label key={option.id} className="choice">
                                <input
                                  type="radio"
                                  name={inputId}
                                  checked={answer.options[0] === option.id}
                                  onChange={() => pickOne(question.id, option.id)}
                                />
                                <span>{option.label}</span>
                              </label>
                            ))}
                          </div>
                        )}

                        {question.question_type === 'multi_choice' && (
                          <div className="choices">
                            {question.options.map((option) => (
                              <label key={option.id} className="choice">
                                <input
                                  type="checkbox"
                                  checked={answer.options.includes(option.id)}
                                  onChange={() => toggleMany(question.id, option.id)}
                                />
                                <span>{option.label}</span>
                              </label>
                            ))}
                          </div>
                        )}

                        {bad && <p className="field-error">{bad}</p>}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>
        ),
      )}

      {notice && <p className="alert">{notice}</p>}

      <div className="submit-row">
        <button
          className="btn btn--primary btn--lg"
          onClick={submit}
          disabled={sending || !collecting}
        >
          {sending ? 'Sending…' : 'Submit response'}
        </button>
        <p className="muted">
          {questions.filter((q) => q.is_mandatory).length} of {questions.length} questions are
          required.
        </p>
      </div>
    </div>
  );
}
