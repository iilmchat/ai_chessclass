import { NavLink, Route, Routes } from 'react-router-dom';
import { BotsPage } from '../pages/BotsPage';
import { ChessPage } from '../pages/ChessPage';
import { ClassesPage } from '../pages/ClassesPage';
import { DashboardPage } from '../pages/DashboardPage';
import { ExportPage } from '../pages/ExportPage';
import { ObservabilityPage } from '../pages/ObservabilityPage';
import { ProfilePage } from '../pages/ProfilePage';
import { PythonPage } from '../pages/PythonPage';
import { ReviewPage } from '../pages/ReviewPage';
import { SkillsPage } from '../pages/SkillsPage';
import { TournamentsPage } from '../pages/TournamentsPage';

const NAV_ITEMS = [
  { to: '/', label: 'Дашборд', end: true },
  { to: '/python', label: 'Python-курс' },
  { to: '/review', label: 'Повторение' },
  { to: '/chess', label: 'Шахматы' },
  { to: '/bots', label: 'Боты' },
  { to: '/tournaments', label: 'Турниры' },
  { to: '/skills', label: 'Навыки' },
  { to: '/classes', label: 'Классы' },
  { to: '/profile', label: 'Профиль' },
  { to: '/export', label: 'Экспорт' },
  { to: '/ops', label: 'Наблюдаемость' },
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
          <span className="brand-stage">v0.2 · dev</span>
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
      <a className="skip-link" href="#main">
        Перейти к содержимому
      </a>
      <main className="main" id="main">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/python" element={<PythonPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/chess" element={<ChessPage />} />
          <Route path="/bots" element={<BotsPage />} />
          <Route path="/skills" element={<SkillsPage />} />
          <Route path="/classes" element={<ClassesPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/tournaments" element={<TournamentsPage />} />
          <Route path="/export" element={<ExportPage />} />
          <Route path="/ops" element={<ObservabilityPage />} />
        </Routes>
      </main>
    </div>
  );
}
