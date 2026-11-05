import { NavLink, Route, Routes } from 'react-router-dom';
import { BotsPage } from '../pages/BotsPage';
import { ChessPage } from '../pages/ChessPage';
import { ClassesPage } from '../pages/ClassesPage';
import { ComplaintsPage } from '../pages/ComplaintsPage';
import { ConsentPage } from '../pages/ConsentPage';
import { DashboardPage } from '../pages/DashboardPage';
import { ExportPage } from '../pages/ExportPage';
import { ObservabilityPage } from '../pages/ObservabilityPage';
import { ProfilePage } from '../pages/ProfilePage';
import { PythonPage } from '../pages/PythonPage';
import { RagEditorPage } from '../pages/RagEditorPage';
import { ReviewPage } from '../pages/ReviewPage';
import { PvpPage } from '../pages/PvpPage';
import { SkillsPage } from '../pages/SkillsPage';
import { TournamentsPage } from '../pages/TournamentsPage';

const NAV_ITEMS = [
  { to: '/', label: 'Дашборд', end: true },
  { to: '/python', label: 'Python-курс' },
  { to: '/review', label: 'Повторение' },
  { to: '/chess', label: 'Шахматы' },
  { to: '/bots', label: 'Боты' },
  { to: '/pvp', label: 'PvP' },
  { to: '/complaints', label: 'Жалобы' },
  { to: '/tournaments', label: 'Турниры' },
  { to: '/skills', label: 'Навыки' },
  { to: '/classes', label: 'Классы' },
  { to: '/rag', label: 'RAG-база' },
  { to: '/profile', label: 'Профиль' },
  { to: '/consent', label: 'Согласие' },
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
          <span className="brand-stage">v{__APP_VERSION__} · {__APP_STAGE__}</span>
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
          <Route path="/pvp" element={<PvpPage />} />
          <Route path="/complaints" element={<ComplaintsPage />} />
          <Route path="/skills" element={<SkillsPage />} />
          <Route path="/classes" element={<ClassesPage />} />
          <Route path="/rag" element={<RagEditorPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/consent" element={<ConsentPage />} />
          <Route path="/tournaments" element={<TournamentsPage />} />
          <Route path="/export" element={<ExportPage />} />
          <Route path="/ops" element={<ObservabilityPage />} />
        </Routes>
      </main>
    </div>
  );
}
