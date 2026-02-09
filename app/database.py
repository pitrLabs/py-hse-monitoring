from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base
from app.config import settings

SQLALCHEMY_DATABASE_URL = settings.database_url
engine = create_engine(SQLALCHEMY_DATABASE_URL,
                       pool_pre_ping=True,
                       pool_size=10,
                       max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    # Run schema upgrades for existing tables (columns that create_all won't add)
    _upgrade_schema()


def _upgrade_schema():
    """Add columns/tables that create_all won't add to existing tables"""
    from sqlalchemy import text, inspect
    inspector = inspect(engine)

    with engine.connect() as conn:
        # Add user_id column to camera_groups if it doesn't exist
        if 'camera_groups' in inspector.get_table_names():
            columns = [c['name'] for c in inspector.get_columns('camera_groups')]
            if 'user_id' not in columns:
                print("[Migration] Adding user_id column to camera_groups...")
                conn.execute(text(
                    'ALTER TABLE camera_groups ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE'
                ))
                conn.execute(text(
                    'CREATE INDEX IF NOT EXISTS ix_camera_groups_user_id ON camera_groups(user_id)'
                ))
                conn.commit()
                print("[Migration] Done: user_id column added to camera_groups")

        # Clean up deprecated roles: migrate 'admin' users to 'superadmin', remove 'admin' and 'viewer'
        if 'roles' in inspector.get_table_names():
            deprecated = conn.execute(text(
                "SELECT id, name FROM roles WHERE name IN ('admin', 'viewer')"
            )).fetchall()
            deprecated_names = [r[1] for r in deprecated]

            if deprecated_names:
                print(f"[Migration] Cleaning up deprecated roles: {deprecated_names}")

                if 'admin' in deprecated_names:
                    # Get superadmin role id
                    sa = conn.execute(text(
                        "SELECT id FROM roles WHERE name = 'superadmin'"
                    )).fetchone()
                    admin_role = conn.execute(text(
                        "SELECT id FROM roles WHERE name = 'admin'"
                    )).fetchone()

                    if sa and admin_role:
                        # Reassign users from 'admin' to 'superadmin' (skip if already assigned)
                        conn.execute(text(
                            "UPDATE user_roles SET role_id = :sa_id "
                            "WHERE role_id = :admin_id "
                            "AND user_id NOT IN (SELECT user_id FROM user_roles WHERE role_id = :sa_id)"
                        ), {"sa_id": sa[0], "admin_id": admin_role[0]})
                        # Delete remaining admin role assignments (duplicates)
                        conn.execute(text(
                            "DELETE FROM user_roles WHERE role_id = :admin_id"
                        ), {"admin_id": admin_role[0]})
                        print("[Migration] Reassigned 'admin' users to 'superadmin'")

                # Delete deprecated roles
                for role_row in deprecated:
                    # Delete role_permissions entries
                    conn.execute(text(
                        "DELETE FROM role_permissions WHERE role_id = :rid"
                    ), {"rid": role_row[0]})
                    # Delete the role itself
                    conn.execute(text(
                        "DELETE FROM roles WHERE id = :rid"
                    ), {"rid": role_row[0]})
                    print(f"[Migration] Deleted deprecated role: {role_row[1]}")

                conn.commit()
                print("[Migration] Done: deprecated roles cleaned up")

        # Drop user_level column from users table (no longer used)
        if 'users' in inspector.get_table_names():
            columns = [c['name'] for c in inspector.get_columns('users')]
            if 'user_level' in columns:
                print("[Migration] Dropping user_level column from users...")
                conn.execute(text('ALTER TABLE users DROP COLUMN user_level'))
                conn.commit()
                print("[Migration] Done: user_level column dropped from users")

        # Add minio_labeled_image_path column to alarms if it doesn't exist
        if 'alarms' in inspector.get_table_names():
            columns = [c['name'] for c in inspector.get_columns('alarms')]
            if 'minio_labeled_image_path' not in columns:
                print("[Migration] Adding minio_labeled_image_path column to alarms...")
                conn.execute(text(
                    'ALTER TABLE alarms ADD COLUMN minio_labeled_image_path VARCHAR(500)'
                ))
                conn.commit()
                print("[Migration] Done: minio_labeled_image_path column added to alarms")

        # Create ai_boxes table if it doesn't exist
        if 'ai_boxes' not in inspector.get_table_names():
            print("[Migration] Creating ai_boxes table...")
            conn.execute(text('''
                CREATE TABLE ai_boxes (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(100) NOT NULL,
                    code VARCHAR(20) UNIQUE NOT NULL,
                    api_url VARCHAR(500) NOT NULL,
                    alarm_ws_url VARCHAR(500) NOT NULL,
                    stream_ws_url VARCHAR(500) NOT NULL,
                    is_active BOOLEAN DEFAULT true NOT NULL,
                    is_online BOOLEAN DEFAULT false NOT NULL,
                    last_seen_at TIMESTAMP,
                    last_error VARCHAR(500),
                    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
                )
            '''))
            conn.execute(text('CREATE INDEX ix_ai_boxes_code ON ai_boxes(code)'))
            conn.commit()
            print("[Migration] Done: ai_boxes table created")

        # Add aibox_id column to video_sources if it doesn't exist
        if 'video_sources' in inspector.get_table_names():
            columns = [c['name'] for c in inspector.get_columns('video_sources')]
            if 'aibox_id' not in columns:
                print("[Migration] Adding aibox_id column to video_sources...")
                conn.execute(text(
                    'ALTER TABLE video_sources ADD COLUMN aibox_id UUID REFERENCES ai_boxes(id) ON DELETE SET NULL'
                ))
                conn.execute(text('CREATE INDEX ix_video_sources_aibox_id ON video_sources(aibox_id)'))
                conn.commit()
                print("[Migration] Done: aibox_id column added to video_sources")

        # Add aibox columns to alarms if they don't exist
        if 'alarms' in inspector.get_table_names():
            columns = [c['name'] for c in inspector.get_columns('alarms')]
            if 'aibox_id' not in columns:
                print("[Migration] Adding aibox_id column to alarms...")
                conn.execute(text(
                    'ALTER TABLE alarms ADD COLUMN aibox_id UUID REFERENCES ai_boxes(id) ON DELETE SET NULL'
                ))
                conn.execute(text('CREATE INDEX ix_alarms_aibox_id ON alarms(aibox_id)'))
                conn.commit()
                print("[Migration] Done: aibox_id column added to alarms")
            if 'aibox_name' not in columns:
                print("[Migration] Adding aibox_name column to alarms...")
                conn.execute(text(
                    'ALTER TABLE alarms ADD COLUMN aibox_name VARCHAR(100)'
                ))
                conn.commit()
                print("[Migration] Done: aibox_name column added to alarms")
            if 'media_url' not in columns:
                print("[Migration] Adding media_url column to alarms...")
                conn.execute(text(
                    'ALTER TABLE alarms ADD COLUMN media_url VARCHAR(500)'
                ))
                conn.commit()
                print("[Migration] Done: media_url column added to alarms")
