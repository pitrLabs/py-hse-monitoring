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
