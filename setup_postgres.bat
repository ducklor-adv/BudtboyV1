@echo off
REM BudtBoy PostgreSQL Setup Script
REM This script will create the database and user for BudtBoy

echo ========================================
echo BudtBoy PostgreSQL Database Setup
echo ========================================
echo.
echo This will create:
echo - Database: budtboy_db
echo - User: budtboy_user
echo - Password: BudtBoy2025!Secure
echo.
echo You will need to enter your postgres user password.
echo.
pause

REM Run the SQL script
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -f create_postgres_db.sql

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Connection details saved in .env file
echo.
pause
