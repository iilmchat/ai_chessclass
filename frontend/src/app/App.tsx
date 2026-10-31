import { NavLink, Route, Routes } from 'react-router-dom';
import { BotsPage } from '../pages/BotsPage';
import { ChessPage } from '../pages/ChessPage';
import { DashboardPage } from '../pages/DashboardPage';
import { PythonPage } from '../pages/PythonPage';
import { SkillsPage } from '../pages/SkillsPage';

const NAV_ITEMS = [
  { to: '/', label: 'Дашборд', end: true },
  { to: '/python', label: 'Python-курс' },
  { to: '/chess', label: 'Шахматы' },
  { to: '/bots', label: 'Боты' },
  { to: '/skills', label: 'Навыки' },
];

export function App() {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            ♞
          </span>
          <span className="brand-name">ChessClass</span>
          <span className="brand-stage">v0.1 · dev</span>
        </div>
        <nav className="nav" aria-label="Основная навигация">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="main">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/python" element={<PythonPage />} />
          <Route path="/chess" element={<ChessPage />} />
          <Route path="/bots" element={<BotsPage />} />
          <Route path="/skills" element={<SkillsPage />} />
        </Routes>
      </main>
    </div>
  );
}
