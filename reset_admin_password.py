
#!/usr/bin/env python3
"""
Script to reset admin password
"""
import os
import sys
sys.path.append('.')
from main import init_connection_pool, get_db_connection, hash_password, validate_password_strength

def reset_admin_password():
    """Reset admin password"""
    print("🔧 Reset Admin Password...")
    
    # Initialize database connection
    init_connection_pool()
    
    # List existing admins
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT admin_name, is_active 
                FROM admin_accounts 
                WHERE is_active = TRUE
                ORDER BY admin_name
            """)
            
            admins = cur.fetchall()
            if not admins:
                print("❌ No active admin accounts found")
                return
            
            print("📋 Active admin accounts:")
            for i, admin in enumerate(admins, 1):
                print(f"   {i}. {admin[0]}")
            
            # Select admin
            while True:
                try:
                    choice = int(input(f"Select admin (1-{len(admins)}): "))
                    if 1 <= choice <= len(admins):
                        selected_admin = admins[choice-1][0]
                        break
                    else:
                        print(f"❌ Please enter number between 1 and {len(admins)}")
                except ValueError:
                    print("❌ Please enter a valid number")
            
            # Get new password
            while True:
                password = input("Enter new password (min 8 chars, mix of upper/lower/numbers): ").strip()
                is_valid, message = validate_password_strength(password)
                if is_valid:
                    break
                print(f"❌ {message}")
            
            # Confirm password
            confirm_password = input("Confirm new password: ").strip()
            if password != confirm_password:
                print("❌ Passwords do not match")
                return
            
            # Update password
            password_hash = hash_password(password)
            
            cur.execute("""
                UPDATE admin_accounts 
                SET password_hash = %s, 
                    login_attempts = 0, 
                    locked_until = NULL,
                    session_token = NULL,
                    token_expires = NULL
                WHERE admin_name = %s
            """, (password_hash, selected_admin))
            
            if cur.rowcount > 0:
                conn.commit()
                print(f"✅ Password reset successful for admin: {selected_admin}")
                print("🔑 Admin can now login with the new password")
            else:
                print("❌ Failed to reset password")
            
            cur.close()
        except Exception as e:
            print(f"❌ Error resetting password: {e}")
            conn.rollback()
        finally:
            from main import return_db_connection
            return_db_connection(conn)
    else:
        print("❌ Database connection failed")

if __name__ == "__main__":
    reset_admin_password()
