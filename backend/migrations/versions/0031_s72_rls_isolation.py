"""S-72: PostgreSQL RLS — изоляция данных классов учителей.

Revision ID: 0031_s72_rls_isolation
Revises: 0030_s67_lms_oauth
Create Date: 2026-11-05

Политики разрешают доступ к строке, если:
  * текущая роль — admin (системный/административный доступ);
  * строка принадлежит самому пользователю (`user_id`);
  * `user_id` состоит в классе, где текущий пользователь — учитель.

Контекст (`app.current_user_id`, `app.current_user_role`) выставляет
`core/db.py` через транзакционно-локальный `set_config`. Приложение
дополнительно переключается на непривилегированную роль `chess_app`
(роль-владелец БД — суперпользователь и иначе обходила бы RLS).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031_s72_rls_isolation"
down_revision: str | None = "0030_s67_lms_oauth"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

#: Таблицы, содержащие данные ученика, которые нельзя смешивать между классами.
TENANT_TABLES: tuple[str, ...] = (
    "bot_stats",
    "cognitive_skill_events",
    "anticheat_flags",
)

APP_ROLE = "chess_app"

#: Одна и та же проверка для USING и WITH CHECK.
_ACCESS_SQL = """
    current_setting('app.current_user_role', true) = 'admin'
    OR user_id = NULLIF(current_setting('app.current_user_id', true), '')::bigint
    OR EXISTS (
        SELECT 1
        FROM class_members AS cm
        JOIN classes AS c ON c.id = cm.class_id
        WHERE cm.user_id = {table}.user_id
          AND c.teacher_id =
              NULLIF(current_setting('app.current_user_id', true), '')::bigint
    )
"""


def _policy_sql(table: str) -> str:
    access = _ACCESS_SQL.format(table=table)
    return (
        f"CREATE POLICY s72_{table}_tenant ON {table} "
        f"FOR ALL USING ({access}) WITH CHECK ({access})"
    )


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN NOBYPASSRLS;
            END IF;
        END
        $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
        f"IN SCHEMA public TO {APP_ROLE}"
    )
    op.execute(
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
    )

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE — страховка на случай подключения владельцем таблиц.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(_policy_sql(table))


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS s72_{table}_tenant ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
               f"REVOKE ALL ON TABLES FROM {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
               f"REVOKE ALL ON SEQUENCES FROM {APP_ROLE}")
    op.execute(f"DROP OWNED BY {APP_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")
