#!/usr/bin/env python3
"""
Test script to verify get_user_reviews function works with SQLite schema
"""
import sqlite3
import os
import sys

# Add current directory to path to import main.py functions
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import get_db_connection, is_sqlite, db_placeholder

def test_user_reviews_query():
    """Test the user reviews query directly"""
    print("🔍 Testing user_reviews query...")
    
    # Connect to database
    conn = get_db_connection()
    if not conn:
        print("❌ Failed to get database connection")
        return False
    
    try:
        cur = conn.cursor()
        
        print(f"✅ Connected to {'SQLite' if is_sqlite(conn) else 'PostgreSQL'} database")
        
        # Test the exact query from get_user_reviews function
        placeholder = db_placeholder(conn)
        
        if is_sqlite(conn):
            query = f"""
                SELECT r.id, r.overall_rating, r.short_summary, r.full_review_content,
                       r.aroma_rating, r.selected_effects, r.aroma_flavors, r.review_images,
                       r.created_at, r.updated_at, r.video_review_url,
                       COALESCE(b.strain_name_en, 'Unknown Strain') as strain_name_en,
                       COALESCE(b.strain_name_th, '') as strain_name_th,
                       COALESCE(b.breeder, 'Unknown') as breeder,
                       COALESCE(u.username, 'Unknown User') as reviewer_name,
                       u.profile_image_url as reviewer_profile_image,
                       r.bud_id as bud_reference_id
                FROM reviews r
                LEFT JOIN buds_data b ON r.bud_id = b.id
                LEFT JOIN users u ON r.user_id = u.id
                WHERE r.user_id = {placeholder}
                ORDER BY r.created_at DESC
                LIMIT 50
            """
        else:
            query = f"""
                SELECT r.id, r.overall_rating, r.short_summary, r.full_review_content,
                       r.aroma_rating, r.selected_effects, r.aroma_flavors, r.review_images,
                       r.created_at, r.updated_at, r.video_review_url,
                       COALESCE(b.strain_name_en, 'Unknown Strain') as strain_name_en,
                       COALESCE(b.strain_name_th, '') as strain_name_th,
                       COALESCE(b.breeder, 'Unknown') as breeder,
                       COALESCE(u.username, 'Unknown User') as reviewer_name,
                       u.profile_image_url as reviewer_profile_image,
                       r.bud_reference_id
                FROM reviews r
                LEFT JOIN buds_data b ON r.bud_reference_id = b.id
                LEFT JOIN users u ON r.reviewer_id = u.id
                WHERE r.reviewer_id = {placeholder}
                ORDER BY r.created_at DESC
                LIMIT 50
            """
        
        # Test with user_id = 1 (assuming user exists)
        test_user_id = 1
        print(f"📋 Testing query with user_id: {test_user_id}")
        print(f"📋 Query: {query}")
        
        try:
            cur.execute(query, (test_user_id,))
            results = cur.fetchall()
            
            print(f"✅ Query executed successfully!")
            print(f"📊 Found {len(results)} reviews")
            
            if results:
                print("📝 Sample review data:")
                for i, row in enumerate(results[:3]):  # Show first 3 results
                    print(f"  Review {i+1}: ID={row[0]}, Rating={row[1]}, Summary={row[2][:50] if row[2] else 'None'}...")
            else:
                print("📝 No reviews found for this user")
                
            return True
            
        except Exception as query_error:
            print(f"❌ Query execution failed: {query_error}")
            
            # Let's check what columns actually exist
            if is_sqlite(conn):
                print("\n🔍 Checking actual SQLite reviews table schema:")
                cur.execute("PRAGMA table_info(reviews)")
                columns = cur.fetchall()
                print("Available columns:")
                for col in columns:
                    print(f"  - {col[1]} ({col[2]})")
                    
                # Test simpler query
                print("\n🔍 Testing simpler query:")
                cur.execute("SELECT COUNT(*) FROM reviews")
                count = cur.fetchone()[0]
                print(f"Total reviews in table: {count}")
                
                if count > 0:
                    cur.execute("SELECT * FROM reviews LIMIT 1")
                    sample = cur.fetchone()
                    print(f"Sample row: {sample}")
            
            return False
            
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False
        
    finally:
        if cur:
            cur.close()
        if conn:
            if is_sqlite(conn):
                conn.close()
            else:
                # Return to pool if PostgreSQL
                try:
                    from main import return_db_connection
                    return_db_connection(conn)
                except:
                    conn.close()

def test_create_sample_review():
    """Create a sample review for testing"""
    print("\n🔧 Creating sample review for testing...")
    
    conn = get_db_connection()
    if not conn:
        print("❌ Failed to get database connection")
        return False
        
    try:
        cur = conn.cursor()
        
        # Check if user exists first
        if is_sqlite(conn):
            cur.execute("SELECT id FROM users LIMIT 1")
        else:
            cur.execute("SELECT id FROM users LIMIT 1")
            
        user_result = cur.fetchone()
        if not user_result:
            print("❌ No users found in database")
            return False
            
        user_id = user_result[0]
        print(f"✅ Found user with ID: {user_id}")
        
        # Insert a test review
        if is_sqlite(conn):
            cur.execute("""
                INSERT INTO reviews (
                    user_id, bud_id, overall_rating, short_summary, 
                    full_review_content, aroma_rating, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (user_id, 1, 4, "Test review summary", "This is a test review content", 3))
        else:
            cur.execute("""
                INSERT INTO reviews (
                    reviewer_id, bud_reference_id, overall_rating, short_summary, 
                    full_review_content, aroma_rating, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (user_id, 1, 4, "Test review summary", "This is a test review content", 3))
            
        conn.commit()
        print("✅ Sample review created successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error creating sample review: {e}")
        return False
        
    finally:
        if cur:
            cur.close()
        if conn:
            if is_sqlite(conn):
                conn.close()
            else:
                try:
                    from main import return_db_connection
                    return_db_connection(conn)
                except:
                    conn.close()

if __name__ == "__main__":
    print("🧪 Testing user_reviews functionality...")
    
    # Test the query first
    if test_user_reviews_query():
        print("\n✅ user_reviews query test completed successfully")
    else:
        print("\n❌ user_reviews query test failed")
        
        # Try creating a sample review and test again
        if test_create_sample_review():
            print("\n🔄 Retesting query after creating sample data...")
            test_user_reviews_query()
    
    print("\n✅ Testing complete!")