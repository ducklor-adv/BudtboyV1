-- BudtBoy PostgreSQL Database Setup Script
-- Run this script with: psql -U postgres -f create_postgres_db.sql

-- Create database
CREATE DATABASE budtboy_db
    WITH
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- Create user
CREATE USER budtboy_user WITH PASSWORD 'BudtBoy2025!Secure';

-- Set user properties
ALTER ROLE budtboy_user SET client_encoding TO 'utf8';
ALTER ROLE budtboy_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE budtboy_user SET timezone TO 'UTC';

-- Connect to the new database
\c budtboy_db

-- Grant privileges on database
GRANT ALL PRIVILEGES ON DATABASE budtboy_db TO budtboy_user;

-- Grant privileges on schema
GRANT ALL ON SCHEMA public TO budtboy_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO budtboy_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO budtboy_user;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO budtboy_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO budtboy_user;

-- Display success message
\echo 'Database budtboy_db created successfully!'
\echo 'User: budtboy_user'
\echo 'Password: BudtBoy2025!Secure'
\echo ''
\echo 'Connection string:'
\echo 'postgresql://budtboy_user:BudtBoy2025!Secure@localhost:5432/budtboy_db'
