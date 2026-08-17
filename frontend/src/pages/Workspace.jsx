import { useCallback, useEffect, useState } from 'react';
import { api } from '../api.js';
import Builder from './Builder.jsx';
import FillForm from './FillForm.jsx';
import ResponsesView from './ResponsesView.jsx';

const TABS = [
  { id: 'build', label: 'Build' },
  { id: 'fill', label: 'Fill in' },
  { id: 'responses', label: 'Responses' },
];

export default function Workspace({ processId, tab, onTabChange, onBack, onOpenProcess }) {
  const [process, setProcess] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [savingMeta, setSavingMeta] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setProcess(await api.getProcess(processId));
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [processId]);

  useEffect(() => {
    load();
  }, [load]);

  const saveMeta = async (changes) => {
    setSavingMeta(true);
    try {
      const updated = await api.updateProcess(processId, {
        name: changes.name ?? process.name,
        description: changes.description ?? process.description ?? null,
        status: changes.status ?? process.status,
      });
      setProcess(updated);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingMeta(false);
    }
  };

  const duplicate = async () => {
    try {
      const copy = await api.duplicateProcess(processId);
      onOpenProcess(copy.id, 'build');
    } catch (err) {
      setError(err.message);
    }
  };

  if (loading && !process) {
    return (
      <div className="page">
        <p className="muted">Loading…</p>
      </div>
    );
  }

  if (!process) {
    return (
      <div className="page">
        <p className="alert">{error ?? 'That process could not be loaded.'}</p>
        <button className="btn" onClick={onBack}>
          Back to processes
        </button>
      </div>
    );
  }

  const questionCount = process.sections.reduce((n, s) => n + s.questions.length, 0);
  const mandatoryCount = process.sections.reduce(
    (n, s) => n + s.questions.filter((q) => q.is_mandatory).length,
    0,
  );

  return (
    <div className="page page--wide">
      <button className="backlink" onClick={onBack}>
        ← All processes
      </button>

      <header className="workspace-head">
        <input
          className="title-input"
          value={process.name}
          aria-label="Process name"
          onChange={(e) => setProcess({ ...process, name: e.target.value })}
          onBlur={(e) => {
            const next = e.target.value.trim();
            if (next && next !== process.name) saveMeta({ name: next });
            else if (!next) load();
          }}
        />

        <div className="workspace-meta">
          <label className="inline-field">
            <span className="label">Status</span>
            <select
              className="select"
              value={process.status}
              onChange={(e) => saveMeta({ status: e.target.value })}
              disabled={savingMeta}
            >
              <option value="draft">Draft — not collecting</option>
              <option value="published">Published — collecting</option>
              <option value="closed">Closed — no new responses</option>
            </select>
          </label>

          <p className="counts">
            <span>{process.sections.length} sections</span>
            <span>{questionCount} questions</span>
            <span>{mandatoryCount} mandatory</span>
            <span>{process.response_count} responses</span>
          </p>
        </div>

        <textarea
          className="textarea textarea--quiet"
          rows={2}
          placeholder="Describe what this process is for. Respondents see this at the top of the form."
          value={process.description ?? ''}
          onChange={(e) => setProcess({ ...process, description: e.target.value })}
          onBlur={(e) => saveMeta({ description: e.target.value.trim() || null })}
        />
      </header>

      <nav className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`tab ${tab === t.id ? 'tab--on' : ''}`}
            onClick={() => onTabChange(t.id)}
          >
            {t.label}
            {t.id === 'responses' && process.response_count > 0 && (
              <span className="tab__count">{process.response_count}</span>
            )}
          </button>
        ))}
      </nav>

      {error && <p className="alert">{error}</p>}

      {tab === 'build' && (
        <Builder process={process} setProcess={setProcess} onDuplicate={duplicate} />
      )}
      {tab === 'fill' && <FillForm process={process} onSubmitted={load} />}
      {tab === 'responses' && <ResponsesView process={process} onChanged={load} />}
    </div>
  );
}
