# UAE Phone Number Validator & Converter

## Overview

This is a Streamlit-based web application designed to validate and convert UAE phone numbers to international format. The application accepts file uploads (CSV/Excel), processes phone number data, validates them against UAE mobile number standards, and converts valid numbers to international format with the +971 country code.

## System Architecture

### Frontend Architecture
- **Framework**: Streamlit - A Python web framework for rapid data app development
- **UI Components**: Simple upload interface for CSV/Excel files with real-time processing feedback
- **Data Display**: Pandas DataFrames rendered through Streamlit's native data display components

### Backend Architecture
- **Language**: Python 3.11
- **Database**: PostgreSQL with SQLAlchemy ORM for data persistence
- **Core Logic**: Phone number validation and conversion utilities
- **Data Processing**: Pandas for file parsing and data manipulation
- **File Support**: CSV and Excel files via pandas and openpyxl
- **Data Storage**: Processing sessions and cleaned numbers stored in database

### Validation Logic
- Validates UAE mobile numbers with exactly 9 digits
- Checks for valid UAE mobile prefixes: 50, 52, 54, 55, 56, 58
- Converts valid numbers to international format by prepending 971

## Key Components

### Core Functions
1. **validate_uae_phone_number()**: Validates phone numbers against UAE mobile standards
2. **convert_to_international_format()**: Converts valid UAE numbers to international format
3. **process_phone_numbers()**: Main processing function that handles batch validation and conversion

### Database Functions
1. **save_processing_session()**: Stores processing session metadata in PostgreSQL
2. **save_cleaned_numbers()**: Stores individual cleaned numbers with session tracking
3. **get_processing_history()**: Retrieves processing history for display
4. **delete_processing_session()**: Deletes individual sessions and associated data
5. **delete_old_sessions()**: Bulk deletion of sessions older than specified days
6. **get_database_stats()**: Provides storage statistics and database information

### File Processing
- Supports CSV and Excel file formats
- Uses pandas for data parsing and manipulation
- Handles missing data and various input formats

### User Interface
- **Login System**: Secure authentication with funny Naim security questions
- **Tabbed Interface**: Organized into Phone Cleaner, Processing History, Database Management, and Debug/Test sections
- **File Upload**: Drag-and-drop support for CSV/Excel files with auto-detection
- **Column Selection**: Intelligent auto-detection of phone number columns
- **Real-time Processing**: Progress tracking with percentage completion for large files
- **Results Display**: Comprehensive statistics and processed data visualization
- **Download Functionality**: WhatsApp-ready CSV export with proper formatting
- **Database Management**: Storage cleanup tools to delete old sessions and manage server space
- **Processing History**: Enhanced dashboard with session statistics and export capabilities
- **Debug Tools**: Live validation testing and format verification utilities

## Data Flow

1. **File Upload**: User uploads CSV/Excel file containing phone numbers
2. **Column Selection**: User selects which column contains phone numbers
3. **Data Processing**: Application validates each phone number and converts valid ones
4. **Results Display**: Shows statistics (valid/invalid counts) and processed data
5. **Data Export**: Allows download of processed results

## External Dependencies

### Python Packages
- **streamlit (>=1.46.0)**: Web application framework
- **pandas (>=2.3.0)**: Data manipulation and analysis
- **openpyxl (>=3.1.5)**: Excel file reading support
- **sqlalchemy (>=2.0.41)**: Database ORM for PostgreSQL integration
- **psycopg2-binary (>=2.9.10)**: PostgreSQL database adapter

### System Dependencies
- Python 3.11 runtime
- Nix package management (stable-24_05 channel)
- glibc locales for proper text handling

## Deployment Strategy

### Replit Configuration
- **Deployment Target**: Autoscale deployment for automatic scaling
- **Runtime**: Python 3.11 with Nix package management
- **Port Configuration**: Streamlit server running on port 5000
- **Process Management**: Streamlit run command with server configuration

### Server Configuration
- Headless mode enabled for server deployment
- Configured to accept connections from all addresses (0.0.0.0)
- Custom port binding to 5000 for Replit compatibility

### Workflow Management
- Parallel workflow execution
- Automatic port waiting for service readiness
- Shell execution for Streamlit startup

## Changelog

```
Changelog:
- June 18, 2025. Initial setup with UAE phone validation
- June 18, 2025. Added PostgreSQL database integration for session tracking
- June 18, 2025. Enhanced validation to handle multiple phone formats (+971, 971, 0-prefix)
- June 18, 2025. Added progress tracking for large files (100,000+ numbers)
- June 18, 2025. Implemented batch processing for memory efficiency
- June 18, 2025. Added comprehensive debugging and validation testing tools
- June 18, 2025. Enhanced validation to support decimal point formats (501234567.00, etc.)
- June 18, 2025. Added funny login system with JavaScript animations and Naim security questions
- June 18, 2025. Implemented database cleanup functionality to manage server storage
```

## User Preferences

```
Preferred communication style: Simple, everyday language.
```

## Technical Notes

### UAE Phone Number Standards
- Valid UAE mobile numbers are exactly 9 digits
- Must start with specific prefixes: 50, 52, 54, 55, 56, 58
- International format adds 971 country code prefix

### File Processing Capabilities
- Handles both CSV and Excel formats
- Processes data in batches for memory efficiency
- Provides real-time feedback on processing status
- Generates downloadable results with processed data

### Error Handling
- Validates file formats before processing
- Handles missing or invalid data gracefully
- Provides clear feedback on validation failures
- Maintains data integrity throughout processing