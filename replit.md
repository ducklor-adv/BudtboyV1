# Cannabis App - Bud Management System

## Overview

This is a Flask-based web application for managing cannabis bud information, reviews, and user activities. The app provides comprehensive features for users to catalog their cannabis experiences, write reviews, and track activities. It includes an admin dashboard for system management and supports multiple user roles with authentication and authorization.

## User Preferences

Preferred communication style: Simple, everyday language.

## Recent Changes

**September 12, 2025**
- **RESOLVED: API monitoring loop issue**: Successfully handled excessive HEAD /api calls from Replit's monitoring service that was causing system instability and 500 errors
- **RESOLVED: bud-report loading failures**: Fixed page loading issues that prevented bud report functionality from working properly
- **RESOLVED: JavaScript syntax errors**: Eliminated all browser console errors that were affecting frontend functionality
- **Final solution**: Simplified `/api` endpoint to accept GET/POST methods only, allowing HEAD requests to be handled as successful 200 responses through Flask's automatic handling, eliminating all errors while maintaining monitoring compatibility
- **System restored to full functionality**: All major components (bud reporting, JavaScript features, server stability) now working properly

## System Architecture

### Backend Framework
The application is built using **Flask** as the primary web framework, providing a lightweight and flexible foundation for the web application. Flask was chosen for its simplicity and rapid development capabilities.

### Database Layer
- **PostgreSQL** is used as the primary database with **psycopg2** for database connectivity
- **Connection pooling** is implemented to manage database connections efficiently
- **Real-time cursor support** using `RealDictCursor` for JSON-like data handling
- Database operations include user management, bud cataloging, reviews, and activity tracking

### Caching Strategy
A multi-tiered caching system is implemented with different TTL (Time To Live) values:
- **Standard cache**: 15 minutes (900 seconds) for general data
- **Short-term cache**: 3 minutes (180 seconds) for frequently changing data
- **Profile cache**: 30 minutes (1800 seconds) for user profile data
- Thread-safe caching using locks to prevent race conditions

### Authentication & Security
- **Session-based authentication** using Flask sessions
- **bcrypt password hashing** with salt rounds for secure password storage
- **Secret key management** using environment variables with fallback defaults
- **File upload security** with allowed extensions and size limits (16MB max)
- **Admin role management** with separate admin interfaces

### File Management
- **Secure file uploads** using `werkzeug.utils.secure_filename`
- **Organized file storage** with separate directories for uploads and attached assets
- **File type validation** supporting PDF, PNG, JPG, and JPEG formats

### Email Integration
- **Flask-Mail** integration for email functionality
- **Gmail SMTP** configuration with TLS encryption
- **Environment-based configuration** for email credentials
- Email features likely used for user notifications and password resets

### Frontend Architecture
- **Server-side templating** using Jinja2 templates
- **Responsive design** with mobile-first approach using CSS Grid and Flexbox
- **Thai language support** with UTF-8 encoding
- **Modern UI/UX** with gradient backgrounds, card-based layouts, and smooth transitions
- **Component-based styling** with consistent design patterns across pages

### Admin Features
The application includes comprehensive admin functionality:
- **User management** with role-based access control
- **Bud data administration** for managing cannabis strain information
- **Review moderation** and management
- **System settings** configuration
- **Dedicated admin interfaces** with separate styling and functionality

### Data Management
- **Strain information** management with detailed cataloging
- **Review system** with rating and comment functionality
- **Activity tracking** for user engagement monitoring
- **Friend system** for social features
- **Search functionality** for finding specific bud information

## External Dependencies

### Core Framework Dependencies
- **Flask**: Web application framework
- **psycopg2**: PostgreSQL database adapter with connection pooling
- **Flask-Mail**: Email integration for notifications
- **bcrypt**: Password hashing and security

### Database
- **PostgreSQL**: Primary database system for data persistence
- Expects database connection via `DATABASE_URL` environment variable

### Email Service
- **Gmail SMTP**: Email service provider
- Requires `MAIL_USERNAME` and `MAIL_PASSWORD` environment variables
- Uses TLS encryption on port 587

### File Storage
- **Local file system**: For uploaded files and attached assets
- **werkzeug**: For secure file handling and uploads

### Frontend Assets
- **Static files**: CSS, JavaScript, and image assets served directly
- **Template engine**: Jinja2 for server-side rendering

### Security & Configuration
- **Environment variables**: For sensitive configuration (database URLs, email credentials, secret keys)
- **Session management**: Server-side session storage
- **CSRF protection**: Implicit through Flask session handling