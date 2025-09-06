
#!/usr/bin/env python3
"""
Script to create additional admin accounts
"""
import os
import sys
sys.path.append('.')
from main import create_admin_account, init_connection_pool, create_tables, get_db_connection, hash_password, validate_password_strength

def create_additional_admin():
    """Create additional admin account"""
    print("🔧 Creating additional admin account...")
    
    # Initialize database connection
    init_connection_pool()
    create_tables()
    
    # Get admin details
    admin_name = input("Enter new admin name: ").strip()
    
    if not admin_name:
        print("❌ Admin name cannot be empty")
        return
    
    # Check if admin already exists
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM admin_accounts WHERE admin_name = %s", (admin_name,))
            if cur.fetchone():
                print(f"❌ Admin '{admin_name}' already exists")
                cur.close()
                return
            cur.close()
        except Exception as e:
            print(f"❌ Error checking admin: {e}")
            return
        finally:
            if conn:
                from main import return_db_connection
                return_db_connection(conn)
    
    while True:
        password = input("Enter admin password (min 8 chars, mix of upper/lower/numbers): ").strip()
        is_valid, message = validate_password_strength(password)
        if is_valid:
            break
        print(f"❌ {message}")
    
    # Confirm password
    confirm_password = input("Confirm password: ").strip()
    if password != confirm_password:
        print("❌ Passwords do not match")
        return
    
    # Create admin account
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            password_hash = hash_password(password)
            
            cur.execute("""
                INSERT INTO admin_accounts (admin_name, password_hash, is_active, created_at)
                VALUES (%s, %s, TRUE, NOW())
                RETURNING id
            """, (admin_name, password_hash))
            
            admin_id = cur.fetchone()[0]
            conn.commit()
            
            print(f"✅ Created admin account: {admin_name}")
            print(f"🔑 Admin login URL: /admin_login")
            print(f"👤 Admin name: {admin_name}")
            print("🛡️  Please keep your credentials secure!")
            
            cur.close()
        except Exception as e:
            print(f"❌ Error creating admin: {e}")
            conn.rollback()
        finally:
            from main import return_db_connection
            return_db_connection(conn)
    else:
        print("❌ Database connection failed")

def list_admins():
    """List all admin accounts"""
    print("📋 Current admin accounts:")
    
    init_connection_pool()
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT admin_name, is_active, created_at, last_login 
                FROM admin_accounts 
                ORDER BY created_at
            """)
            
            admins = cur.fetchall()
            if not admins:
                print("   No admin accounts found")
            else:
                for admin in admins:
                    status = "🟢 Active" if admin[1] else "🔴 Inactive"
                    last_login = admin[3].strftime('%Y-%m-%d %H:%M') if admin[3] else "Never"
                    print(f"   👤 {admin[0]} - {status} - Created: {admin[2].strftime('%Y-%m-%d')} - Last login: {last_login}")
            
            cur.close()
        except Exception as e:
            print(f"❌ Error listing admins: {e}")
        finally:
            from main import return_db_connection
            return_db_connection(conn)

if __name__ == "__main__":
    print("🛡️  Admin Management Tool")
    print("1. Create new admin account")
    print("2. List all admin accounts")
    
    choice = input("Select option (1 or 2): ").strip()
    
    if choice == "1":
        create_additional_admin()
    elif choice == "2":
        list_admins()
    else:
        print("❌ Invalid option")
