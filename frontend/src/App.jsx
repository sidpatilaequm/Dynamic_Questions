import { useState } from 'react';
import ProcessList from './pages/ProcessList.jsx';
import Workspace from './pages/Workspace.jsx';

export default function App() {
  // Small app, no router dependency: one piece of state describes the screen.
  const [route, setRoute] = useState({ name: 'processes' });

  const openProcess = (id, tab = 'build') => setRoute({ name: 'process', id, tab });
  const openList = () => setRoute({ name: 'processes' });

  return (
    <div className="app">
      <header className="topbar">
        <button className="wordmark" onClick={openList}>
          <span className="wordmark__mark" aria-hidden="true">FS</span>
          <span className="wordmark__text">Form Studio</span>
        </button>
        <p className="topbar__note">
          Build a process, arrange its questions, collect the answers.
        </p>
      </header>

      <main>
        {route.name === 'processes' ? (
          <ProcessList onOpen={openProcess} />
        ) : (
          <Workspace
            processId={route.id}
            tab={route.tab}
            onTabChange={(tab) => setRoute((r) => ({ ...r, tab }))}
            onBack={openList}
            onOpenProcess={openProcess}
          />
        )}
      </main>
    </div>
  );
}
