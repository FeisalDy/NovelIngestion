"""
Setup script for novel-ingestion backend.

Run this to initialize the project:
1. Create database tables
2. Verify Scrapy configuration
3. Run basic validation checks
"""
import subprocess
import sys
import os
from pathlib import Path


def print_section(title):
    """Print section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def run_command(command, cwd=None):
    """Run a shell command and return success status."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True
        )
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print(f"Output: {e.output}")
        print(f"Stderr: {e.stderr}")
        return False


def check_env_file():
    """Check if .env file exists."""
    print_section("Checking Environment Configuration")
    
    if Path(".env").exists():
        print("✓ .env file found")
        return True
    else:
        print("✗ .env file not found")
        print("\nPlease create .env file:")
        print("  cp .env.example .env")
        print("  # Then edit .env with your settings")
        return False


def check_database():
    """Check database connectivity."""
    print_section("Checking Database Connection")
    
    try:
        from database import sync_engine
        from sqlalchemy import text
        
        with sync_engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✓ Database connection successful")
            return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        print("\nPlease check your DATABASE_URL in .env")
        return False


def run_migrations():
    """Run database migrations."""
    print_section("Running Database Migrations")
    
    print("Creating/updating database tables...")
    success = run_command("alembic upgrade head")
    
    if success:
        print("✓ Migrations completed successfully")
    else:
        print("✗ Migrations failed")
    
    return success


def verify_scrapy():
    """Verify Scrapy configuration."""
    print_section("Verifying Scrapy Configuration")
    
    print("Checking Scrapy spiders...")
    success = run_command("scrapy list", cwd="./crawler")
    
    if success:
        print("✓ Scrapy configured correctly")
    else:
        print("✗ Scrapy configuration issue")
    
    return success


def create_initial_migration():
    """Create initial migration if needed."""
    print_section("Creating Initial Migration")
    
    # Check if migrations exist
    migrations_dir = Path("alembic/versions")
    
    if migrations_dir.exists() and list(migrations_dir.glob("*.py")):
        print("✓ Migrations already exist")
        return True
    
    print("Creating initial migration...")
    success = run_command(
        'alembic revision --autogenerate -m "Initial migration"'
    )
    
    if success:
        print("✓ Initial migration created")
    else:
        print("✗ Failed to create migration")
    
    return success


def main():
    """Main setup routine."""
    print("\n" + "=" * 60)
    print("  Novel Ingestion Backend - Setup")
    print("=" * 60)
    
    # Track overall success
    all_checks_passed = True
    
    # 1. Check environment file
    if not check_env_file():
        all_checks_passed = False
        print("\n⚠ Setup cannot continue without .env file")
        sys.exit(1)
    
    # 2. Check database
    if not check_database():
        all_checks_passed = False
        print("\n⚠ Setup cannot continue without database connection")
        sys.exit(1)
    
    # 3. Create initial migration
    if not create_initial_migration():
        all_checks_passed = False
    
    # 4. Run migrations
    if not run_migrations():
        all_checks_passed = False
    
    # 5. Verify Scrapy
    if not verify_scrapy():
        all_checks_passed = False
    
    # Final status
    print_section("Setup Complete")
    
    if all_checks_passed:
        print("✓ All checks passed!")
        print("\nYou can now start the server:")
        print("  python main.py")
        print("\nOr with uvicorn:")
        print("  uvicorn main:app --reload")
        print("\nAPI docs will be available at:")
        print("  http://localhost:8000/docs")
    else:
        print("✗ Some checks failed. Please review errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
