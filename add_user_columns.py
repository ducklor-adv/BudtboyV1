import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# Database connection
conn = psycopg2.connect(
    host='localhost',
    database='budtboy_db',
    user='budtboy_user',
    password='budtboy2025',
    port='5432'
)

cursor = conn.cursor()

try:
    # Add is_shop column
    print("Adding is_shop column...")
    cursor.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS is_shop BOOLEAN DEFAULT FALSE;
    """)
    print("OK - is_shop column added")

    # Add province column
    print("Adding province column...")
    cursor.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS province VARCHAR(100);
    """)
    print("OK - province column added")

    conn.commit()
    print("\nSUCCESS - All columns added successfully!")

    # Verify columns
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'users'
        AND column_name IN ('is_shop', 'province')
        ORDER BY column_name;
    """)

    print("\nVerifying columns:")
    for row in cursor.fetchall():
        print(f"  - {row[0]}: {row[1]}")

except Exception as e:
    print(f"ERROR: {e}")
    conn.rollback()
finally:
    cursor.close()
    conn.close()
