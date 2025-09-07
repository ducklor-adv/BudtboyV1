
#!/usr/bin/env python3
"""
Script to initialize sample data for production database
"""
import os
import sys
sys.path.append('.')
from main import get_db_connection, return_db_connection, init_connection_pool
from datetime import datetime

def create_sample_data():
    """Create sample bud data and user data for production"""
    print("🔧 Initializing sample data for production...")
    
    # Initialize database connection
    init_connection_pool()
    
    conn = get_db_connection()
    if not conn:
        print("❌ Failed to connect to database")
        return
    
    try:
        cur = conn.cursor()
        
        # Check if sample user exists
        cur.execute("SELECT id FROM users WHERE username = 'Budt.Boy'")
        sample_user = cur.fetchone()
        
        if not sample_user:
            print("Creating sample user...")
            from main import hash_password
            import secrets
            
            password_hash = hash_password('BudtBoy123!')
            referral_code = secrets.token_urlsafe(8)
            
            cur.execute("""
                INSERT INTO users (username, email, password_hash, is_grower, is_consumer, 
                                 is_verified, is_approved, referral_code, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING id
            """, ('Budt.Boy', 'budtboy@example.com', password_hash, True, True, True, True, referral_code))
            
            sample_user_id = cur.fetchone()[0]
            print(f"✅ Created sample user with ID: {sample_user_id}")
        else:
            sample_user_id = sample_user[0]
            print(f"✅ Sample user already exists with ID: {sample_user_id}")
        
        # Check if sample buds exist
        cur.execute("SELECT COUNT(*) FROM buds_data WHERE created_by = %s", (sample_user_id,))
        existing_count = cur.fetchone()[0]
        
        if existing_count == 0:
            print("Creating sample bud data...")
            
            sample_buds = [
                # Blue Dream
                (
                    'บลูดรีม', 'Blue Dream', 'Barney\'s Farm', 'Hybrid',
                    18.5, 1.2, 'A+', 'หวาน, เบอร์รี่, ซิตรัส',
                    'Myrcene', 'Limonene', 'Pinene',
                    'ผ่อนคลาย, สร้างสรรค์, สุขใจ', '',
                    'บรรเทาปวด, คลายกล้าม', 'ปากแห้ง',
                    'ตลอดวัน', 'Indoor', '2024-12-01',
                    'BD2024-001', sample_user_id, True,
                    'Organic', 'Photoperiod', sample_user_id
                ),
                # OG Kush
                (
                    'โอจี คัช', 'OG Kush', 'DNA Genetics', 'Indica',
                    22.3, 0.8, 'A', 'ดิน, สน, เผ็ด',
                    'Myrcene', 'Caryophyllene', 'Limonene',
                    'ผ่อนคลาย, หลับง่าย', 'ง่วงหนัก',
                    'บรรเทาปวด, หลับง่าย', 'ตาแดง, ปากแห้ง',
                    'กลางคืน', 'Indoor', '2024-11-15',
                    'OG2024-001', sample_user_id, True,
                    'Chemical', 'Photoperiod', sample_user_id
                ),
                # White Widow
                (
                    'ไวท์ วิโดว์', 'White Widow', 'Green House Seed Company', 'Hybrid',
                    20.1, 1.5, 'A+', 'หวาน, ดอกไม้, มินต์',
                    'Pinene', 'Myrcene', 'Limonene',
                    'ตื่นตัว, โฟกัส, เบิกบาน', '',
                    'ต้านอักเสบ, สดชื่น', 'ตาแห้ง',
                    'กลางวัน', 'Greenhouse', '2024-10-20',
                    'WW2024-001', sample_user_id, True,
                    'Organic', 'Photoperiod', sample_user_id
                ),
                # Blue Dream (variant 2)
                (
                    'บลูดรีม 2', 'Blue Dream', 'DNA Genetics', 'Hybrid',
                    19.2, 2.0, 'B+', 'กาแฟ, สตรอว์เบอร์รี่, บัตเตอร์',
                    'Myrcene', 'Limonene', 'Caryophyllene',
                    'ผ่อนคลาย, สร้างสรรค์', '',
                    'บรรเทาปวด, คลายกล้าม', 'ปากแห้ง',
                    'ตลอดวัน', 'Indoor', '2025-07-16',
                    '', sample_user_id, True,
                    'Organic', 'Photoperiod', sample_user_id
                )
            ]
            
            cur.executemany("""
                INSERT INTO buds_data (
                    strain_name_th, strain_name_en, breeder, strain_type,
                    thc_percentage, cbd_percentage, grade, aroma_flavor,
                    top_terpenes_1, top_terpenes_2, top_terpenes_3,
                    mental_effects_positive, mental_effects_negative,
                    physical_effects_positive, physical_effects_negative,
                    recommended_time, grow_method, harvest_date,
                    batch_number, grower_id, grower_license_verified,
                    fertilizer_type, flowering_type, created_by
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, sample_buds)
            
            print(f"✅ Created {len(sample_buds)} sample bud records")
            
            # Get the created bud IDs for reviews
            cur.execute("""
                SELECT id FROM buds_data 
                WHERE created_by = %s 
                ORDER BY created_at DESC LIMIT 4
            """, (sample_user_id,))
            bud_ids = [row[0] for row in cur.fetchall()]
            
            if len(bud_ids) >= 2:
                # Create sample reviews
                sample_reviews = [
                    # Review for first bud
                    (
                        bud_ids[0], sample_user_id, 4,
                        ['หวาน', 'เบอร์รี่', 'ซิตรัส'], 4,
                        ['ผ่อนคลาย', 'สร้างสรรค์', 'สุขใจ'],
                        'ดอกเยี่ยม รสชาติดี',
                        'Blue Dream นี้เป็นสายพันธุ์ที่ยอดเยี่ยมมาก กลิ่นหอมหวานของเบอร์รี่ผสมซิตรัส ให้ความรู้สึกผ่อนคลายแต่ยังคงความตื่นตัว เหมาะสำหรับใช้ตลอดวัน'
                    ),
                    # Review for second bud  
                    (
                        bud_ids[1], sample_user_id, 5,
                        ['ดิน', 'สน', 'เผ็ด'], 5,
                        ['ผ่อนคลาย', 'หลับง่าย'],
                        'OG Kush คลาสสิค เยี่ยม!',
                        'OG Kush ต้นตำรับที่ดีเยี่ยม กลิ่นเป็นเอกลักษณ์ของดิน สน และเครื่องเทศ ให้ความรู้สึกผ่อนคลายลึก เหมาะสำหรับเย็นและกลางคืน ช่วยให้หลับง่ายมาก'
                    )
                ]
                
                cur.executemany("""
                    INSERT INTO reviews (
                        bud_reference_id, reviewer_id, overall_rating,
                        aroma_flavors, aroma_rating, selected_effects,
                        short_summary, full_review_content
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, sample_reviews)
                
                print(f"✅ Created {len(sample_reviews)} sample reviews")
        else:
            print(f"✅ Sample buds already exist ({existing_count} records)")
        
        conn.commit()
        print("🎉 Sample data initialization completed successfully!")
        
    except Exception as e:
        print(f"❌ Error creating sample data: {e}")
        conn.rollback()
    finally:
        cur.close()
        return_db_connection(conn)

if __name__ == "__main__":
    create_sample_data()
