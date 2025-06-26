#!/usr/bin/env python3
"""
Development Environment Setup Script for MKW Stats Bot.

This script automates the setup of a complete development environment
including dependencies, pre-commit hooks, and configuration validation.
"""

import os
import subprocess
import sys
import venv
from pathlib import Path
from typing import List, Optional

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_step(message: str, step_num: int = 0) -> None:
    """Print a formatted step message."""
    if step_num:
        print(f"\n{Colors.OKBLUE}📋 Step {step_num}: {message}{Colors.ENDC}")
    else:
        print(f"{Colors.OKCYAN}   {message}{Colors.ENDC}")


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"{Colors.OKGREEN}✅ {message}{Colors.ENDC}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"{Colors.WARNING}⚠️  {message}{Colors.ENDC}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"{Colors.FAIL}❌ {message}{Colors.ENDC}")


def run_command(cmd: List[str], check: bool = True, capture_output: bool = False) -> subprocess.CompletedProcess:
    """Run a command and handle errors."""
    try:
        print_step(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=check, capture_output=capture_output, text=True)
        if result.returncode == 0:
            print_success(f"Command completed successfully")
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed with return code {e.returncode}")
        if capture_output and e.stdout:
            print(f"STDOUT: {e.stdout}")
        if capture_output and e.stderr:
            print(f"STDERR: {e.stderr}")
        raise


def check_python_version() -> bool:
    """Check if Python version is 3.11 or higher."""
    version = sys.version_info
    if version.major == 3 and version.minor >= 11:
        print_success(f"Python {version.major}.{version.minor}.{version.micro} is supported")
        return True
    else:
        print_error(f"Python {version.major}.{version.minor}.{version.micro} is not supported. Need Python 3.11+")
        return False


def check_system_dependencies() -> bool:
    """Check for required system dependencies."""
    print_step("Checking system dependencies")
    
    dependencies = {
        'git': 'git --version',
        'tesseract': 'tesseract --version',
    }
    
    missing = []
    for name, cmd in dependencies.items():
        try:
            result = subprocess.run(cmd.split(), capture_output=True, text=True, check=True)
            print_success(f"{name} is installed")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print_warning(f"{name} is not installed or not in PATH")
            missing.append(name)
    
    if missing:
        print_error("Missing system dependencies. Please install:")
        for dep in missing:
            if dep == 'tesseract':
                print("  • Tesseract OCR:")
                print("    - macOS: brew install tesseract")
                print("    - Ubuntu: sudo apt-get install tesseract-ocr")
                print("    - Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki")
        return False
    
    return True


def create_virtual_environment(venv_path: Path) -> bool:
    """Create a virtual environment if it doesn't exist."""
    if venv_path.exists():
        print_success(f"Virtual environment already exists at {venv_path}")
        return True
    
    try:
        print_step(f"Creating virtual environment at {venv_path}")
        venv.create(venv_path, with_pip=True)
        print_success("Virtual environment created successfully")
        return True
    except Exception as e:
        print_error(f"Failed to create virtual environment: {e}")
        return False


def get_pip_command(venv_path: Path) -> str:
    """Get the pip command for the virtual environment."""
    if sys.platform == "win32":
        return str(venv_path / "Scripts" / "pip")
    else:
        return str(venv_path / "bin" / "pip")


def install_dependencies(venv_path: Path) -> bool:
    """Install Python dependencies."""
    pip_cmd = get_pip_command(venv_path)
    
    try:
        # Upgrade pip first
        print_step("Upgrading pip")
        run_command([pip_cmd, "install", "--upgrade", "pip"])
        
        # Install production dependencies
        print_step("Installing production dependencies")
        run_command([pip_cmd, "install", "-r", "requirements.txt"])
        
        # Install development dependencies
        print_step("Installing development dependencies")
        run_command([pip_cmd, "install", "-r", "requirements-dev.txt"])
        
        # Install project in editable mode
        print_step("Installing project in editable mode")
        run_command([pip_cmd, "install", "-e", "."])
        
        print_success("All dependencies installed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install dependencies: {e}")
        return False


def setup_pre_commit_hooks(venv_path: Path) -> bool:
    """Setup pre-commit hooks."""
    pip_cmd = get_pip_command(venv_path)
    
    try:
        # Install pre-commit if not already installed
        print_step("Installing pre-commit hooks")
        run_command([pip_cmd, "install", "pre-commit"])
        
        # Get pre-commit command
        if sys.platform == "win32":
            precommit_cmd = str(venv_path / "Scripts" / "pre-commit")
        else:
            precommit_cmd = str(venv_path / "bin" / "pre-commit")
        
        # Install hooks
        run_command([precommit_cmd, "install"])
        
        # Run hooks on all files to test
        print_step("Running pre-commit on all files (this may take a while)")
        try:
            run_command([precommit_cmd, "run", "--all-files"], check=False)
        except subprocess.CalledProcessError:
            print_warning("Some pre-commit hooks failed, but this is normal for first run")
        
        print_success("Pre-commit hooks installed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to setup pre-commit hooks: {e}")
        return False


def create_env_file() -> bool:
    """Create .env file from example if it doesn't exist."""
    env_file = Path(".env")
    example_file = Path(".env.example")
    
    if env_file.exists():
        print_success(".env file already exists")
        return True
    
    if not example_file.exists():
        print_warning(".env.example file not found")
        return False
    
    try:
        print_step("Creating .env file from .env.example")
        env_file.write_text(example_file.read_text())
        print_success(".env file created successfully")
        print_warning("Please edit .env file with your Discord bot token and other settings")
        return True
    except Exception as e:
        print_error(f"Failed to create .env file: {e}")
        return False


def validate_setup(venv_path: Path) -> bool:
    """Validate the development setup."""
    print_step("Validating setup")
    
    python_cmd = str(venv_path / ("Scripts/python" if sys.platform == "win32" else "bin/python"))
    
    try:
        # Test imports
        print_step("Testing imports")
        test_script = """
import mkw_stats
import mkw_stats.bot
import mkw_stats.database
import mkw_stats.ocr_processor
import mkw_stats.logging_config
print("All imports successful")
"""
        result = run_command([python_cmd, "-c", test_script], capture_output=True)
        print_success("All imports working correctly")
        
        # Test database connection (without actual connection)
        print_step("Testing database module")
        test_db_script = """
from mkw_stats.database import DatabaseManager
print("Database module loads correctly")
"""
        run_command([python_cmd, "-c", test_db_script], capture_output=True)
        print_success("Database module working correctly")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print_error(f"Setup validation failed: {e}")
        if e.stdout:
            print(f"STDOUT: {e.stdout}")
        if e.stderr:
            print(f"STDERR: {e.stderr}")
        return False


def print_next_steps() -> None:
    """Print next steps for the user."""
    print(f"\n{Colors.HEADER}🎉 Development Environment Setup Complete!{Colors.ENDC}")
    print(f"\n{Colors.BOLD}Next Steps:{Colors.ENDC}")
    print("1. Edit .env file with your Discord bot token:")
    print("   DISCORD_BOT_TOKEN=your_token_here")
    print("\n2. Initialize your clan database:")
    print("   python management/setup_players.py")
    print("\n3. Start the bot:")
    print("   python main.py")
    print("\n4. Activate virtual environment for development:")
    if sys.platform == "win32":
        print("   venv\\Scripts\\activate")
    else:
        print("   source venv/bin/activate")
    print("\n5. Run tests:")
    print("   pytest")
    print("\n6. Run linting:")
    print("   black mkw_stats/")
    print("   flake8 mkw_stats/")
    print("   mypy mkw_stats/")
    print(f"\n{Colors.OKGREEN}Happy coding! 🚀{Colors.ENDC}")


def main() -> None:
    """Main setup function."""
    print(f"{Colors.HEADER}")
    print("🏁" + "=" * 60)
    print("   MKW Stats Bot - Development Environment Setup")
    print("=" * 62)
    print(f"{Colors.ENDC}")
    
    # Change to project directory
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    print(f"Working in: {project_root.absolute()}")
    
    # Step 1: Check Python version
    print_step("Checking Python version", 1)
    if not check_python_version():
        sys.exit(1)
    
    # Step 2: Check system dependencies
    print_step("Checking system dependencies", 2)
    if not check_system_dependencies():
        print_error("Please install missing system dependencies and try again")
        sys.exit(1)
    
    # Step 3: Create virtual environment
    venv_path = Path("venv")
    print_step("Setting up virtual environment", 3)
    if not create_virtual_environment(venv_path):
        sys.exit(1)
    
    # Step 4: Install dependencies
    print_step("Installing dependencies", 4)
    if not install_dependencies(venv_path):
        sys.exit(1)
    
    # Step 5: Setup pre-commit hooks
    print_step("Setting up pre-commit hooks", 5)
    if not setup_pre_commit_hooks(venv_path):
        print_warning("Pre-commit setup failed, but continuing...")
    
    # Step 6: Create .env file
    print_step("Setting up environment configuration", 6)
    create_env_file()
    
    # Step 7: Validate setup
    print_step("Validating setup", 7)
    if not validate_setup(venv_path):
        print_error("Setup validation failed")
        sys.exit(1)
    
    # Print next steps
    print_next_steps()


if __name__ == "__main__":
    main()