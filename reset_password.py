
#!/usr/bin/env python3
"""
Script to reset a user's password in the database
"""
import psycopg2
import os
import bcrypt

def hash_password(password):
    """Hash password using bcrypt with salt"""
    if isinstance(password, str):
        password = password.encode('utf-8')
    
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password, salt)
    
    return hashed.decode('utf-8')

def reset_user_password(email, new_password):
    """Reset password for a specific user"""
    try:
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            print("DATABASE_URL environment variable not set")
            return False

        conn = psycopg2.connect(database_url)
        cur = conn.cursor()

        # Check if user exists
        cur.execute("SELECT id, username FROM users WHERE email = %s", (email,))
        user = cur.fetchone()

        if not user:
            print(f"User with email {email} not found")
            return False

        user_id, username = user
        print(f"Found user: {username} (ID: {user_id})")

        # Hash the new password
        password_hash = hash_password(new_password)

        # Update the password
        cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))
        conn.commit()

        print(f"Password updated successfully for user {username}")
        return True

    except Exception as e:
        print(f"Error resetting password: {e}")
        return False
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    # Reset password for the problematic user
    email = "johunna@gmail.com"
    new_password = "BudtBoy2024@!"  # You can change this to whatever password you want
    
    print(f"Resetting password for {email}...")
    success = reset_user_password(email, new_password)
    
    if success:
        print("✅ Password reset completed!")
        print(f"New password: {new_password}")
        print("You can now log in with this new password.")
    else:
        print("❌ Password reset failed!")
