
#!/usr/bin/env python3
"""
Script to create initial admin account
"""
import os
import sys
sys.path.append('.')
from main import create_admin_account, init_connection_pool, create_tables

def setup_initial_admin():
    """Setup initial admin account"""
    print("🔧 Setting up initial admin account...")
    
    # Initialize database connection
    init_connection_pool()
    create_tables()
    
    # Create first admin
    admin_name = input("Enter admin name: ").strip()
    
    while True:
        password = input("Enter admin password (min 8 chars, mix of upper/lower/numbers): ").strip()
        if len(password) >= 8:
            break
        print("❌ Password must be at least 8 characters long")
    
    success, message = create_admin_account(admin_name, password)
    
    if success:
        print(f"✅ {message}")
        print(f"🔑 Admin login URL: /admin_login")
        print(f"👤 Admin name: {admin_name}")
        print("🛡️  Please keep your credentials secure!")
    else:
        print(f"❌ Failed to create admin: {message}")

if __name__ == "__main__":
    setup_initial_admin()
