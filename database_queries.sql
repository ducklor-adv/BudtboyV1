-- BudtBoy PostgreSQL Database Queries
-- Use this file with SQLTools or PostgreSQL extension in VS Code

-- View all users
SELECT id, username, email, is_approved, is_verified, created_at
FROM users
ORDER BY created_at DESC;

-- View all tables
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- Count records in each table
SELECT
    'users' as table_name, COUNT(*) as count FROM users
UNION ALL
SELECT 'buds_data', COUNT(*) FROM buds_data
UNION ALL
SELECT 'reviews', COUNT(*) FROM reviews
UNION ALL
SELECT 'activities', COUNT(*) FROM activities
UNION ALL
SELECT 'activity_participants', COUNT(*) FROM activity_participants
UNION ALL
SELECT 'friends', COUNT(*) FROM friends
UNION ALL
SELECT 'email_verifications', COUNT(*) FROM email_verifications
UNION ALL
SELECT 'password_resets', COUNT(*) FROM password_resets
UNION ALL
SELECT 'strain_names', COUNT(*) FROM strain_names
UNION ALL
SELECT 'breeders', COUNT(*) FROM breeders
UNION ALL
SELECT 'admin_settings', COUNT(*) FROM admin_settings
UNION ALL
SELECT 'referrals', COUNT(*) FROM referrals
UNION ALL
SELECT 'admin_accounts', COUNT(*) FROM admin_accounts;

-- View budtboy user details
SELECT * FROM users WHERE username = 'budtboy';

-- View database structure for users table
SELECT
    column_name,
    data_type,
    character_maximum_length,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;
