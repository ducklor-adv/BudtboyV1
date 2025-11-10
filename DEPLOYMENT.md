# BudtBoy Production Deployment Guide

## 📋 Table of Contents
- [Prerequisites](#prerequisites)
- [Quick Production Checklist](#quick-production-checklist)
- [Step-by-Step Deployment](#step-by-step-deployment)
- [Environment Variables](#environment-variables)
- [Database Migration](#database-migration)
- [Web Server Configuration](#web-server-configuration)
- [Security Hardening](#security-hardening)
- [Monitoring and Logging](#monitoring-and-logging)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required
- Linux server (Ubuntu 20.04+ or similar)
- Python 3.10+
- PostgreSQL 13+ (or MySQL 8+)
- Nginx
- Domain name with SSL certificate (Let's Encrypt recommended)
- Minimum 1GB RAM, 10GB disk space

### Recommended
- Redis (for caching)
- Cloudflare (CDN + DDoS protection)
- AWS S3 or Google Cloud Storage (for file uploads)
- Sentry account (for error tracking)

---

## Quick Production Checklist

```bash
# Before deploying to production, ensure:
□ Environment variables configured (.env file)
□ Database migrated from SQLite to PostgreSQL/MySQL
□ SECRET_KEY is a strong random string (not default)
□ DEBUG = False in production
□ HTTPS/SSL certificate installed
□ File uploads moved to cloud storage (S3/GCS)
□ Gunicorn installed and configured
□ Nginx reverse proxy configured
□ Firewall rules configured (UFW/iptables)
□ Automated backups configured
□ Monitoring/logging enabled (Sentry recommended)
□ Static files served by Nginx (not Flask)
□ Admin master password changed
□ Google OAuth credentials configured (if using)
```

---

## Step-by-Step Deployment

### 1. Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y python3-pip python3-venv nginx postgresql postgresql-contrib redis-server

# Install certbot for SSL
sudo apt install -y certbot python3-certbot-nginx
```

### 2. Create Application User

```bash
# Create dedicated user for the application
sudo adduser budtboy --disabled-password
sudo su - budtboy
```

### 3. Clone and Setup Application

```bash
# Clone repository (or upload files)
git clone <repository-url> /home/budtboy/BudtBoy
cd /home/budtboy/BudtBoy

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install production dependencies
pip install -r requirements.txt

# Install production-only packages
pip install gunicorn psycopg2-binary redis sentry-sdk[flask]
```

### 4. Configure Environment Variables

```bash
# Copy example environment file
cp .env.example .env

# Edit with production values
nano .env
```

**Required production `.env` configuration:**

```bash
# Flask Configuration
SECRET_KEY=your-very-strong-random-secret-key-here-generate-with-uuid
FLASK_ENV=production
DEBUG=False

# Database (PostgreSQL)
DATABASE_URL=postgresql://budtboy_user:password@localhost/budtboy_db

# Email Configuration
MAIL_USERNAME=noreply@yourdomain.com
MAIL_PASSWORD=your-app-specific-password
MAIL_DEFAULT_SENDER=noreply@yourdomain.com

# Google OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# Admin Configuration
ADMIN_MASTER_PASSWORD=YourVeryStrongPassword123!@#

# Upload Configuration
UPLOAD_FOLDER=/home/budtboy/BudtBoy/uploads
MAX_CONTENT_LENGTH=16777216

# Application Settings
FALLBACK_AUTH_ENABLED=False

# Sentry (Error Tracking - optional but recommended)
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
```

**Generate secure SECRET_KEY:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Setup PostgreSQL Database

```bash
# Switch to postgres user
sudo su - postgres

# Create database and user
psql
```

```sql
CREATE DATABASE budtboy_db;
CREATE USER budtboy_user WITH PASSWORD 'your_secure_password';
ALTER ROLE budtboy_user SET client_encoding TO 'utf8';
ALTER ROLE budtboy_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE budtboy_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE budtboy_db TO budtboy_user;
\q
```

```bash
exit  # Exit postgres user
```

### 6. Migrate Database from SQLite to PostgreSQL

**Option A: Manual Export/Import (Recommended)**

```bash
# Export SQLite data
sqlite3 budtboy_local.db .dump > data_export.sql

# Import to PostgreSQL (requires manual adjustment of SQL syntax)
# You'll need to modify the SQL file to be PostgreSQL compatible
```

**Option B: Use Python Script**

Create `migrate_to_postgres.py`:

```python
import sqlite3
import psycopg2
from config import config

# Connect to SQLite
sqlite_conn = sqlite3.connect('budtboy_local.db')
sqlite_conn.row_factory = sqlite3.Row

# Connect to PostgreSQL
pg_conn = psycopg2.connect(os.environ.get('DATABASE_URL'))

# Migrate each table...
# (Implementation depends on your schema)
```

### 7. Configure Gunicorn

Create `/home/budtboy/BudtBoy/gunicorn_config.py`:

```python
import multiprocessing

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'sync'
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = '/home/budtboy/BudtBoy/logs/gunicorn-access.log'
errorlog = '/home/budtboy/BudtBoy/logs/gunicorn-error.log'
loglevel = 'info'

# Process naming
proc_name = 'budtboy'

# Server mechanics
daemon = False
pidfile = '/home/budtboy/BudtBoy/gunicorn.pid'
user = 'budtboy'
group = 'budtboy'
tmp_upload_dir = None

# SSL (if terminating SSL at Gunicorn instead of Nginx)
# keyfile = '/path/to/key.pem'
# certfile = '/path/to/cert.pem'
```

### 8. Create Systemd Service

Create `/etc/systemd/system/budtboy.service`:

```ini
[Unit]
Description=BudtBoy Gunicorn Application
After=network.target

[Service]
User=budtboy
Group=budtboy
WorkingDirectory=/home/budtboy/BudtBoy
Environment="PATH=/home/budtboy/BudtBoy/venv/bin"
ExecStart=/home/budtboy/BudtBoy/venv/bin/gunicorn \
    --config /home/budtboy/BudtBoy/gunicorn_config.py \
    run:app

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable budtboy
sudo systemctl start budtboy
sudo systemctl status budtboy
```

### 9. Configure Nginx

Create `/etc/nginx/sites-available/budtboy`:

```nginx
# Rate limiting zone
limit_req_zone $binary_remote_addr zone=budtboy_limit:10m rate=10r/s;

# Upstream Gunicorn
upstream budtboy_app {
    server 127.0.0.1:8000 fail_timeout=0;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_session_timeout 10m;
    ssl_session_cache shared:SSL:10m;

    # Security headers (additional to Flask's headers)
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Max upload size
    client_max_body_size 20M;

    # Logging
    access_log /var/log/nginx/budtboy-access.log;
    error_log /var/log/nginx/budtboy-error.log;

    # Rate limiting
    limit_req zone=budtboy_limit burst=20 nodelay;

    # Static files
    location /static/ {
        alias /home/budtboy/BudtBoy/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Uploads
    location /uploads/ {
        alias /home/budtboy/BudtBoy/uploads/;
        expires 30d;
        add_header Cache-Control "public";
    }

    # Proxy to Gunicorn
    location / {
        proxy_pass http://budtboy_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        proxy_buffering off;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/budtboy /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 10. Setup SSL Certificate

```bash
# Get Let's Encrypt certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Auto-renewal is configured automatically
sudo certbot renew --dry-run
```

### 11. Configure Firewall

```bash
# Allow SSH, HTTP, HTTPS
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

---

## Database Migration

### Updating Database Schema in Production

```bash
# Backup database first!
pg_dump budtboy_db > backup_$(date +%Y%m%d_%H%M%S).sql

# Run migrations
cd /home/budtboy/BudtBoy
source venv/bin/activate
python migrate_data.py  # If you have migration scripts

# Restart application
sudo systemctl restart budtboy
```

---

## Security Hardening

### 1. SSH Security

```bash
# Disable root login
sudo nano /etc/ssh/sshd_config
# Set: PermitRootLogin no
# Set: PasswordAuthentication no (use SSH keys)
sudo systemctl restart sshd
```

### 2. Fail2Ban (Prevent Brute Force)

```bash
sudo apt install fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 3. Automatic Security Updates

```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

### 4. Regular Backups

Create `/home/budtboy/backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/home/budtboy/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Backup database
pg_dump budtboy_db | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"

# Backup uploads
tar -czf "$BACKUP_DIR/uploads_$DATE.tar.gz" /home/budtboy/BudtBoy/uploads/

# Keep only last 30 days
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete

# Upload to S3 (optional)
# aws s3 cp "$BACKUP_DIR/db_$DATE.sql.gz" s3://your-bucket/backups/
```

```bash
# Make executable
chmod +x /home/budtboy/backup.sh

# Add to crontab (daily at 2 AM)
crontab -e
# Add: 0 2 * * * /home/budtboy/backup.sh
```

---

## Monitoring and Logging

### Setup Sentry for Error Tracking

1. Sign up at https://sentry.io
2. Create a new Python/Flask project
3. Add SENTRY_DSN to `.env`
4. Update `app/__init__.py`:

```python
# Add to create_app function
if not app.config['DEBUG'] and os.environ.get('SENTRY_DSN'):
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration

    sentry_sdk.init(
        dsn=os.environ.get('SENTRY_DSN'),
        integrations=[FlaskIntegration()],
        traces_sample_rate=0.1,
        environment='production'
    )
```

### Log Rotation

Create `/etc/logrotate.d/budtboy`:

```
/home/budtboy/BudtBoy/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 budtboy budtboy
    sharedscripts
    postrotate
        systemctl reload budtboy
    endscript
}
```

---

## Troubleshooting

### Application Won't Start

```bash
# Check systemd logs
sudo journalctl -u budtboy -n 50 --no-pager

# Check Gunicorn logs
tail -f /home/budtboy/BudtBoy/logs/gunicorn-error.log

# Check application logs
tail -f /home/budtboy/BudtBoy/logs/budtboy.log
```

### Database Connection Issues

```bash
# Test PostgreSQL connection
psql -U budtboy_user -d budtboy_db -h localhost

# Check PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-13-main.log
```

### Nginx Issues

```bash
# Test configuration
sudo nginx -t

# Check error logs
sudo tail -f /var/log/nginx/budtboy-error.log

# Check access logs
sudo tail -f /var/log/nginx/budtboy-access.log
```

### File Upload Issues

```bash
# Check permissions
ls -la /home/budtboy/BudtBoy/uploads/
sudo chown -R budtboy:budtboy /home/budtboy/BudtBoy/uploads/
sudo chmod -R 755 /home/budtboy/BudtBoy/uploads/
```

### High Memory Usage

```bash
# Check processes
top
htop

# Restart application
sudo systemctl restart budtboy

# Reduce Gunicorn workers if needed
# Edit gunicorn_config.py and reduce workers count
```

---

## Performance Optimization

### Enable Redis Caching

```bash
pip install redis

# Update config.py
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# Update cache implementation to use Redis instead of in-memory cache
```

### Database Query Optimization

```bash
# Enable query logging to find slow queries
# Add to PostgreSQL config
log_min_duration_statement = 1000  # Log queries slower than 1 second
```

### CDN Setup (Cloudflare)

1. Point your domain DNS to Cloudflare
2. Enable CDN caching for static assets
3. Enable DDoS protection
4. Configure page rules for caching

---

## Health Checks

Create `/home/budtboy/BudtBoy/health_check.sh`:

```bash
#!/bin/bash

# Check if application is responding
if curl -f http://localhost:8000/ > /dev/null 2>&1; then
    echo "✓ Application is running"
else
    echo "✗ Application is not responding"
    sudo systemctl restart budtboy
fi

# Check database
if sudo -u postgres psql -c "SELECT 1" budtboy_db > /dev/null 2>&1; then
    echo "✓ Database is accessible"
else
    echo "✗ Database is not accessible"
fi

# Check disk space
DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 90 ]; then
    echo "⚠ Disk usage is high: ${DISK_USAGE}%"
fi
```

---

## Additional Resources

- Flask Production Best Practices: https://flask.palletsprojects.com/en/latest/deploying/
- Gunicorn Documentation: https://docs.gunicorn.org/
- Nginx Documentation: https://nginx.org/en/docs/
- PostgreSQL Documentation: https://www.postgresql.org/docs/
- Let's Encrypt: https://letsencrypt.org/
- Sentry Documentation: https://docs.sentry.io/

---

## Support

For issues or questions:
- Check application logs: `/home/budtboy/BudtBoy/logs/`
- Check system logs: `sudo journalctl -u budtboy`
- Review error tracking: Sentry dashboard

---

**Last Updated:** 2025-01-10
