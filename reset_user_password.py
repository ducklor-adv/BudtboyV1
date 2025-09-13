
#!/usr/bin/env python3
"""
Script to reset password for johunna@gmail.com
"""
import os
import sys
sys.path.append('.')
from main import get_db_connection, return_db_connection, hash_password, is_sqlite

def reset_user_password():
    """Reset password for johunna@gmail.com"""
    email = "johunna@gmail.com"
    new_password = "Freedom2010"
    
    print(f"🔧 Resetting password for {email}...")
    
    conn = get_db_connection()
    if not conn:
        print("❌ Database connection failed")
        return False
    
    try:
        cur = conn.cursor()
        
        # Check if user exists
        if is_sqlite(conn):
            cur.execute("SELECT id, username FROM users WHERE email = ?", (email,))
        else:
            cur.execute("SELECT id, username FROM users WHERE email = %s", (email,))
        
        user = cur.fetchone()
        
        if not user:
            print(f"❌ User with email {email} not found")
            return False
        
        user_id, username = user
        print(f"✅ Found user: {username} (ID: {user_id})")
        
        # Hash the new password
        password_hash = hash_password(new_password)
        
        # Update the password
        if is_sqlite(conn):
            cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        else:
            cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))
        
        conn.commit()
        
        print(f"✅ Password reset successful for user {username}")
        print(f"🔑 New password: {new_password}")
        print("✅ User can now log in with the new password")
        
        return True
        
    except Exception as e:
        print(f"❌ Error resetting password: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        return_db_connection(conn)

if __name__ == "__main__":
    success = reset_user_password()
    if success:
        print("\n🎉 Password reset completed successfully!")
    else:
        print("\n💥 Password reset failed!")
