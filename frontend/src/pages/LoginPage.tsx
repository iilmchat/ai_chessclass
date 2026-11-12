import { useNavigate } from 'react-router-dom';
import { LoginGate } from '../shared/LoginGate';

/** Публичная страница входа (на неё ведут ссылки из писем). */
export function LoginPage() {
  const navigate = useNavigate();
  return (
    <section>
      <h1 className="page-title">Вход</h1>
      <p className="page-subtitle">Единый профиль ChessClass</p>
      <LoginGate
        hint="Demo: student1@chessclass.dev / dev-student-2026"
        onReady={() => navigate('/')}
      />
    </section>
  );
}
