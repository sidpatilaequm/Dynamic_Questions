import { useEffect, useState } from 'react';
import { api } from '../api.js';

function AnswerValue({ answer }) {
  if (answer.question_type === 'short_text') {
    return answer.text_value ? (
      <p className="answer-value">{answer.text_value}</p>
    ) : (
      <p className="answer-value answer-value--empty">Left blank</p>
    );
  }
  if (answer.selected_labels.length === 0) {
    return <p className="answer-value answer-value--empty">Left blank</p>;
  }
  return (
    <ul className="answer-chips">
      {answer.selected_labels.map((label, i) => (
        <li key={`${label}-${i}`}>{label}</li>
      ))}
    </ul>
  );
}

export default function ResponsesView({ process, onChanged }) {
  const [responses, setResponses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [openId, setOpenId] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.listResponses(process.id);
      setResponses(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [process.id]);

  const remove = async (id) => {
    if (!window.confirm('Delete this response?')) return;
    try {
      await api.deleteResponse(id);
      await load();
      onChanged?.();
    } catch (err) {
      setError(err.message);
    }
  };

  const exportCsv = () => {
    const questions = process.sections.flatMap((s) => s.questions);
    const header = ['Response', 'Submitted', 'Name', 'Email', ...questions.map((q) => q.prompt)];
    const cell = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;

    const rows = responses.map((r) => {
      const byQuestion = Object.fromEntries(r.answers.map((a) => [a.question_id, a]));
      return [
        r.id,
        new Date(r.submitted_at).toLocaleString(),
        r.respondent_name ?? '',
        r.respondent_email ?? '',
        ...questions.map((q) => {
          const a = byQuestion[q.id];
          if (!a) return '';
          return q.question_type === 'short_text'
            ? a.text_value ?? ''
            : a.selected_labels.join('; ');
        }),
      ]
        .map(cell)
        .join(',');
    });

    const blob = new Blob([[header.map(cell).join(','), ...rows].join('\n')], {
      type: 'text/csv;charset=utf-8;',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${process.name.replace(/\s+/g, '-').toLowerCase()}-responses.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (loading) return <p className="muted">Loading…</p>;

  return (
    <div className="stack">
      {error && <p className="alert">{error}</p>}

      {responses.length === 0 ? (
        <div className="empty">
          <p className="empty__title">No responses yet.</p>
          <p className="muted">
            Publish the process and use the Fill in tab to record the first one.
          </p>
        </div>
      ) : (
        <>
          <div className="row-actions">
            <button className="btn" onClick={exportCsv}>
              Download CSV
            </button>
            <button className="btn btn--ghost" onClick={load}>
              Refresh
            </button>
          </div>

          <ul className="stack">
            {responses.map((response) => {
              const open = openId === response.id;
              const answered = response.answers.filter(
                (a) => a.text_value || a.selected_labels.length,
              ).length;

              return (
                <li key={response.id} className="card response">
                  <button
                    className="response__head"
                    aria-expanded={open}
                    onClick={() => setOpenId(open ? null : response.id)}
                  >
                    <span className="code">#{response.id}</span>
                    <span className="response__who">
                      {response.respondent_name || 'Anonymous'}
                      {response.respondent_email && (
                        <span className="muted"> · {response.respondent_email}</span>
                      )}
                    </span>
                    <span className="muted">
                      {new Date(response.submitted_at).toLocaleString()}
                    </span>
                    <span className="muted">
                      {answered}/{response.answers.length} answered
                    </span>
                    <span className="response__chev" aria-hidden="true">
                      {open ? '▲' : '▼'}
                    </span>
                  </button>

                  {open && (
                    <div className="response__body">
                      <dl className="answer-list">
                        {response.answers.map((answer) => (
                          <div key={answer.question_id} className="answer">
                            <dt>
                              {answer.prompt}
                              {answer.is_mandatory && <span className="stamp">Required</span>}
                            </dt>
                            <dd>
                              <AnswerValue answer={answer} />
                            </dd>
                          </div>
                        ))}
                      </dl>
                      <button
                        className="btn btn--tiny btn--danger"
                        onClick={() => remove(response.id)}
                      >
                        Delete response
                      </button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
