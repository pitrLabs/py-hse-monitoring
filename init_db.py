from sqlalchemy.orm import Session
from app.database import SessionLocal, init_db
from app.models import User, Role, Permission
from app.auth import get_password_hash


def create_default_permissions(db: Session):
    permissions_data = [
        # User permissions
        {"name": "users.read", "resource": "users", "action": "read", "description": "Read user information"},
        {"name": "users.create", "resource": "users", "action": "create", "description": "Create new users"},
        {"name": "users.update", "resource": "users", "action": "update", "description": "Update user information"},
        {"name": "users.delete", "resource": "users", "action": "delete", "description": "Delete users"},

        # Role permissions
        {"name": "roles.read", "resource": "roles", "action": "read", "description": "Read roles and permissions"},
        {"name": "roles.create", "resource": "roles", "action": "create", "description": "Create new roles"},
        {"name": "roles.update", "resource": "roles", "action": "update", "description": "Update roles"},
        {"name": "roles.delete", "resource": "roles", "action": "delete", "description": "Delete roles"},

        # Monitoring permissions
        {"name": "monitoring.read", "resource": "monitoring", "action": "read", "description": "Read monitoring data"},
        {"name": "monitoring.create", "resource": "monitoring", "action": "create", "description": "Create monitoring records"},
        {"name": "monitoring.update", "resource": "monitoring", "action": "update", "description": "Update monitoring records"},
        {"name": "monitoring.delete", "resource": "monitoring", "action": "delete", "description": "Delete monitoring records"},

        # Statistics permissions
        {"name": "statistics.read", "resource": "statistics", "action": "read", "description": "View statistics dashboard"},

        # Real-time preview permissions
        {"name": "realtime-preview.read", "resource": "realtime-preview", "action": "read", "description": "View real-time preview"},

        # Video source permissions
        {"name": "video-sources.read", "resource": "video-sources", "action": "read", "description": "View video sources"},
        {"name": "video-sources.create", "resource": "video-sources", "action": "create", "description": "Create video sources"},
        {"name": "video-sources.update", "resource": "video-sources", "action": "update", "description": "Update video sources"},
        {"name": "video-sources.delete", "resource": "video-sources", "action": "delete", "description": "Delete video sources"},

        # AI tasks permissions
        {"name": "ai-tasks.read", "resource": "ai-tasks", "action": "read", "description": "View AI tasks"},
        {"name": "ai-tasks.create", "resource": "ai-tasks", "action": "create", "description": "Create AI tasks"},
        {"name": "ai-tasks.update", "resource": "ai-tasks", "action": "update", "description": "Update AI tasks"},
        {"name": "ai-tasks.delete", "resource": "ai-tasks", "action": "delete", "description": "Delete AI tasks"},

        # Alarms permissions
        {"name": "alarms.read", "resource": "alarms", "action": "read", "description": "View alarms"},
        {"name": "alarms.update", "resource": "alarms", "action": "update", "description": "Acknowledge/resolve alarms"},
    ]
    
    created_permissions = []
    for perm_data in permissions_data:
        existing = db.query(Permission).filter(Permission.name == perm_data["name"]).first()

        if not existing:
            permission = Permission(**perm_data)
            db.add(permission)
            created_permissions.append(permission)
            print(f"Created permission: {perm_data['name']}")

        else:
            created_permissions.append(existing)
            print(f"Permission already exists: {perm_data['name']}")
    
    db.commit()

    return created_permissions


def create_default_roles(db: Session, permissions: list):
    """Create 4 account levels: superadmin, manager, operator, P3"""

    # Helper to get permissions by names
    def get_perms_by_names(names: list) -> list:
        return [p for p in permissions if p.name in names]

    # 1. Superadmin - Full access to everything
    superadmin_role = db.query(Role).filter(Role.name == "superadmin").first()
    if not superadmin_role:
        superadmin_role = Role(name="superadmin", description="Super Administrator with full system access")
        superadmin_role.permissions = permissions  # All permissions
        db.add(superadmin_role)
        print("Created role: superadmin")
    else:
        print("Role already exists: superadmin")

    # 2. Manager - Can manage users, video sources, AI tasks, alarms
    manager_perms = get_perms_by_names([
        "users.read", "users.create", "users.update",
        "roles.read",
        "monitoring.read", "monitoring.create", "monitoring.update",
        "statistics.read",
        "realtime-preview.read",
        "video-sources.read", "video-sources.create", "video-sources.update",
        "ai-tasks.read", "ai-tasks.create", "ai-tasks.update",
        "alarms.read", "alarms.update",
    ])
    manager_role = db.query(Role).filter(Role.name == "manager").first()
    if not manager_role:
        manager_role = Role(name="manager", description="Manager with access to users, video sources, AI tasks, alarms")
        manager_role.permissions = manager_perms
        db.add(manager_role)
        print("Created role: manager")
    else:
        print("Role already exists: manager")

    # 3. Operator - Can operate video sources and AI tasks, view alarms
    operator_perms = get_perms_by_names([
        "monitoring.read",
        "statistics.read",
        "realtime-preview.read",
        "video-sources.read",
        "ai-tasks.read",
        "alarms.read", "alarms.update",
    ])
    operator_role = db.query(Role).filter(Role.name == "operator").first()
    if not operator_role:
        operator_role = Role(name="operator", description="Operator with access to video sources, AI tasks, and alarms")
        operator_role.permissions = operator_perms
        db.add(operator_role)
        print("Created role: operator")
    else:
        print("Role already exists: operator")

    # 4. P3 - Can view Statistics and Real-time Preview only
    p3_perms = get_perms_by_names([
        "monitoring.read",
        "statistics.read",
        "realtime-preview.read",
    ])
    p3_role = db.query(Role).filter(Role.name == "p3").first()
    if not p3_role:
        p3_role = Role(name="p3", description="P3 user with view access to Statistics and Real-time Preview")
        p3_role.permissions = p3_perms
        db.add(p3_role)
        print("Created role: p3")
    else:
        print("Role already exists: p3")

    db.commit()
    return superadmin_role, manager_role, operator_role, p3_role


def create_admin_user(db: Session, superadmin_role: Role):
    """Create default superadmin user"""
    admin_user = db.query(User).filter(User.username == "admin").first()
    if not admin_user:
        admin_user = User(username="admin",
                          email="admin@example.com",
                          full_name="System Administrator",
                          hashed_password=get_password_hash("admin123"),
                          is_superuser=True,
                          is_active=True)
        admin_user.roles = [superadmin_role]
        db.add(admin_user)
        db.commit()
        print("Created superadmin user:")
        print("  Username: admin")
        print("  Password: admin123")
        print("  Role: superadmin")
        print("  ⚠️  IMPORTANT: Change this password immediately!")

    else:
        print("Admin user already exists")


def main():
    print("Initializing database...")

    init_db()
    print("Database tables created")

    db = SessionLocal()

    try:
        print("\nCreating permissions...")
        permissions = create_default_permissions(db)

        print("\nCreating roles...")
        superadmin_role, manager_role, operator_role, p3_role = create_default_roles(db, permissions)

        print("\nCreating superadmin user...")
        create_admin_user(db, superadmin_role)

        print("\n✅ Database initialization completed successfully!")
        print("\nDefault user credentials:")
        print("  Username: admin")
        print("  Password: admin123")
        print("\nAccount levels created:")
        print("  - superadmin: Full system access")
        print("  - manager: Manage users, video sources, AI tasks, alarms")
        print("  - operator: Operate video sources, AI tasks, view alarms")
        print("  - p3: View Statistics and Real-time Preview only")

    except Exception as e:
        print(f"\n❌ Error during initialization: {e}")
        db.rollback()

    finally:
        db.close()


if __name__ == "__main__":
    main()
