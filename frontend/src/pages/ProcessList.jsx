import { useEffect, useState } from 'react';
import { api } from '../api.js';

const STATUS_COPY = {
  draft: 'Draft',
  published: 'Taking responses',
  closed: 'Closed',
};

// The only integration this Form Studio actually feeds today — see backend_java's
// questionnaire.external-key.supplier-registration property. Whichever process holds this key
// is the one live applicants see on the Become-a-Supplier form.
const SUPPLIER_KEY = 'become_a_supplier';

export default function ProcessList({ onOpen }) {
  const [processes, setProcesses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [name, setName] = useState('');
  const [creating, setCreating] = useState(false);

  const load = async () => {
    try {
      setProcesses(await api.listProcesses());
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const createProcess = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError('Give the process a name first.');
      return;
    }
    setCreating(true);
    try {
      const created = await api.createProcess({ name: trimmed, status: 'draft' });
      setName('');
      onOpen(created.id, 'build');
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  const duplicate = async (id) => {
    try {
      const copy = await api.duplicateProcess(id);
      onOpen(copy.id, 'build');
    } catch (err) {
      setError(err.message);
    }
  };

  const activate = async (process) => {
    if (
      !window.confirm(
        `Make "${process.name}" the live Become-a-Supplier form? New applicants will see this one immediately; whichever process is currently live will stop being shown.`,
      )
    )
      return;
    try {
      await api.activateProcess(process.id, SUPPLIER_KEY);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const remove = async (process) => {
    const warning =
      process.response_count > 0
        ? `Delete "${process.name}" and its ${process.response_count} response(s)? This cannot be undone.`
        : `Delete "${process.name}"?`;
    if (!window.confirm(warning)) return;
    try {
      await api.deleteProcess(process.id);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="page page--wide">
      <div className="page-head">
        <p className="eyebrow">Your processes</p>
        <h1 className="display">Every form starts as a process.</h1>
        <p className="lede">
          A process holds sections. Sections hold questions, in the order you set. Publish it
          and the answers land back here.
        </p>
      </div>

      <div className="card create-row">
        <label className="label" htmlFor="new-process">
          Name a new process
        </label>
        <div className="create-row__controls">
          <input
            id="new-process"
            className="input"
            placeholder="Vendor onboarding"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && createProcess()}
          />
          <button className="btn btn--primary" onClick={createProcess} disabled={creating}>
            {creating ? 'Creating…' : 'Create process'}
          </button>
        </div>
      </div>

      {error && <p className="alert">{error}</p>}

      {loading ? (
        <p className="muted">Loading…</p>
      ) : processes.length === 0 ? (
        <div className="empty">
          <p className="empty__title">Nothing here yet.</p>
          <p className="muted">Name a process above to start building its first section.</p>
        </div>
      ) : (
        <ul className="grid">
          {processes.map((process) => (
            <li key={process.id} className="card process-card">
              <div className="row-actions" style={{ marginBottom: '4px' }}>
                <div className={`chip chip--${process.status}`}>{STATUS_COPY[process.status]}</div>
                {process.external_key === SUPPLIER_KEY && (
                  <div className="chip chip--published">Live — Become-a-Supplier</div>
                )}
              </div>
              <h2 className="process-card__name">{process.name}</h2>
              {process.description && <p className="muted clamp">{process.description}</p>}

              <dl className="stat-row">
                <div>
                  <dt>Sections</dt>
                  <dd>{process.section_count}</dd>
                </div>
                <div>
                  <dt>Questions</dt>
                  <dd>{process.question_count}</dd>
                </div>
                <div>
                  <dt>Responses</dt>
                  <dd>{process.response_count}</dd>
                </div>
              </dl>

              <div className="row-actions">
                <button className="btn btn--primary" onClick={() => onOpen(process.id, 'build')}>
                  Open
                </button>
                <button className="btn" onClick={() => onOpen(process.id, 'fill')}>
                  Fill in
                </button>
                <button className="btn btn--ghost" onClick={() => duplicate(process.id)}>
                  Duplicate
                </button>
                {process.status === 'published' && process.external_key !== SUPPLIER_KEY && (
                  <button className="btn btn--primary" onClick={() => activate(process)}>
                    Make live
                  </button>
                )}
                <button className="btn btn--danger" onClick={() => remove(process)}>
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
