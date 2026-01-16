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
        
        # Monitoring permissions (example)
        {"name": "monitoring.read", "resource": "monitoring", "action": "read", "description": "Read monitoring data"},
        {"name": "monitoring.create", "resource": "monitoring", "action": "create", "description": "Create monitoring records"},
        {"name": "monitoring.update", "resource": "monitoring", "action": "update", "description": "Update monitoring records"},
        {"name": "monitoring.delete", "resource": "monitoring", "action": "delete", "description": "Delete monitoring records"},
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
    admin_role = db.query(Role).filter(Role.name == "admin").first()

    if not admin_role:
        admin_role = Role(name="admin", description="Administrator with full access")
        admin_role.permissions = permissions
        db.add(admin_role)
        print("Created role: admin")

    else:
        print("Role already exists: admin")

    manager_perms = [p for p in permissions if p.action in ["read", "create", "update"]]
    manager_role = db.query(Role).filter(Role.name == "manager").first()

    if not manager_role:
        manager_role = Role(name="manager", description="Manager with read, create, and update access")
        manager_role.permissions = manager_perms
        db.add(manager_role)
        print("Created role: manager")

    else:
        print("Role already exists: manager")
    
    viewer_perms = [p for p in permissions if p.action == "read"]
    viewer_role = db.query(Role).filter(Role.name == "viewer").first()

    if not viewer_role:
        viewer_role = Role(name="viewer", description="Viewer with read-only access")
        viewer_role.permissions = viewer_perms
        db.add(viewer_role)
        print("Created role: viewer")

    else:
        print("Role already exists: viewer")
    
    db.commit()
    return admin_role, manager_role, viewer_role


def create_admin_user(db: Session, admin_role: Role):
    """Create default admin user"""
    admin_user = db.query(User).filter(User.username == "admin").first()
    if not admin_user:
        admin_user = User(username="admin",
                          email="admin@example.com",
                          full_name="System Administrator",
                          hashed_password=get_password_hash("admin123"),
                          is_superuser=True,
                          is_active=True,
                          user_level=10)
        admin_user.roles = [admin_role]
        db.add(admin_user)
        db.commit()
        print("Created admin user:")
        print("  Username: admin")
        print("  Password: admin123")
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
        admin_role, manager_role, viewer_role = create_default_roles(db, permissions)

        print("\nCreating admin user...")
        create_admin_user(db, admin_role)
        
        print("\n✅ Database initialization completed successfully!")
        print("\nDefault user credentials:")
        print("  Username: admin")
        print("  Password: admin123")
        print("\nDefault roles created:")
        print("  - admin: Full access")
        print("  - manager: Read, create, update access")
        print("  - viewer: Read-only access")
        
    except Exception as e:
        print(f"\n❌ Error during initialization: {e}")
        db.rollback()

    finally:
        db.close()


if __name__ == "__main__":
    main()
