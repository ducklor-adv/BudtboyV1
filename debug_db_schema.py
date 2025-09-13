#!/usr/bin/env python3
"""
Script to debug SQLite database schema and fix the missing overall_rating column issue
"""
import sqlite3
import os

def check_sqlite_schema():
    """Check SQLite database schema and fix issues"""
    db_path = 'budtboy_preview.db'
    
    if not os.path.exists(db_path):
        print(f"❌ Database file {db_path} does not exist")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if reviews table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reviews'")
        table_exists = cursor.fetchone()
        
        if not table_exists:
            print("❌ Reviews table does not exist")
            return False
            
        print("✅ Reviews table exists")
        
        # Get current schema of reviews table
        cursor.execute("PRAGMA table_info(reviews)")
        columns = cursor.fetchall()
        
        print("\n📋 Current reviews table schema:")
        column_names = []
        for col in columns:
            print(f"  {col[1]} ({col[2]}) - PK: {col[5]}, NOT NULL: {col[3]}, Default: {col[4]}")
            column_names.append(col[1])
        
        # Check if overall_rating column exists
        if 'overall_rating' not in column_names:
            print("\n❌ overall_rating column is missing!")
            print("📝 Adding overall_rating column...")
            
            cursor.execute("""
                ALTER TABLE reviews 
                ADD COLUMN overall_rating INTEGER CHECK(overall_rating >= 1 AND overall_rating <= 5)
            """)
            conn.commit()
            print("✅ overall_rating column added successfully")
        else:
            print("\n✅ overall_rating column exists")
        
        # Check data in reviews table
        cursor.execute("SELECT COUNT(*) FROM reviews")
        count = cursor.fetchone()[0]
        print(f"\n📊 Reviews table has {count} records")
        
        if count > 0:
            # Check if any records have null overall_rating
            cursor.execute("SELECT COUNT(*) FROM reviews WHERE overall_rating IS NULL")
            null_count = cursor.fetchone()[0]
            print(f"📊 Records with NULL overall_rating: {null_count}")
            
            # Show sample data
            cursor.execute("SELECT id, overall_rating, short_summary FROM reviews LIMIT 3")
            samples = cursor.fetchall()
            print("\n📝 Sample data:")
            for sample in samples:
                print(f"  ID: {sample[0]}, Rating: {sample[1]}, Summary: {sample[2][:50] if sample[2] else 'None'}...")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error checking SQLite schema: {e}")
        return False

def fix_reviews_schema():
    """Fix the reviews table schema to include all necessary columns"""
    db_path = 'budtboy_preview.db'
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get current column names
        cursor.execute("PRAGMA table_info(reviews)")
        existing_columns = [col[1] for col in cursor.fetchall()]
        
        # Define expected columns for reviews table
        expected_columns = [
            ('overall_rating', 'INTEGER CHECK(overall_rating >= 1 AND overall_rating <= 5)'),
            ('aroma_rating', 'INTEGER CHECK(aroma_rating >= 1 AND aroma_rating <= 5)'),
            ('short_summary', 'TEXT'),
            ('full_review_content', 'TEXT'),
            ('selected_effects', 'TEXT'),
            ('aroma_flavors', 'TEXT'),
            ('review_images', 'TEXT'),
            ('video_review_url', 'TEXT'),
            ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
            ('updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        ]
        
        print("🔧 Checking and adding missing columns...")
        
        for col_name, col_def in expected_columns:
            if col_name not in existing_columns:
                print(f"  Adding column: {col_name}")
                cursor.execute(f"ALTER TABLE reviews ADD COLUMN {col_name} {col_def}")
                
        conn.commit()
        conn.close()
        
        print("✅ Reviews table schema fixed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error fixing reviews schema: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Debugging SQLite database schema...")
    
    # Check current schema
    if check_sqlite_schema():
        print("\n🔧 Fixing schema if needed...")
        fix_reviews_schema()
        
        # Check again after fixes
        print("\n🔍 Verifying fixes...")
        check_sqlite_schema()
    
    print("\n✅ Database schema debugging complete!")