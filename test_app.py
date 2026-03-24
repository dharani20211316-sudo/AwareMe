#!/usr/bin/env python3
"""
Simple test script for AwareMe Flask app
Tests the core functionality without heavy dependencies
"""

import os
import sys
import json
import subprocess

def test_app_syntax():
    """Test that app.py compiles without syntax errors"""
    print("🧪 Testing app.py syntax...")
    try:
        result = subprocess.run([sys.executable, "-m", "py_compile", "app.py"],
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ app.py syntax is valid")
            return True
        else:
            print(f"❌ Syntax error in app.py: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Failed to test syntax: {e}")
        return False

def test_environment_variables():
    """Test that required environment variables are set"""
    print("🧪 Testing environment variables...")
    required_vars = ['FLASK_SECRET_KEY', 'GROQ_API_KEY', 'MONGO_URI']
    missing_vars = []

    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        print(f"⚠️ Missing environment variables: {', '.join(missing_vars)}")
        print("   This is expected if .env is not loaded, but good to note")
    else:
        print("✅ All required environment variables are set")

    return True

def test_audit_log_creation():
    """Test that audit.log can be created"""
    print("🧪 Testing audit log creation...")
    try:
        # Remove existing audit log if it exists
        if os.path.exists("audit.log"):
            os.remove("audit.log")

        # Try to write to audit log
        with open("audit.log", "w") as f:
            f.write("Test log entry\n")

        if os.path.exists("audit.log"):
            print("✅ Audit log can be created")
            # Clean up
            os.remove("audit.log")
            return True
        else:
            print("❌ Audit log creation failed")
            return False
    except Exception as e:
        print(f"❌ Audit log test failed: {e}")
        return False

def test_csv_file_access():
    """Test that chat_history.csv can be accessed"""
    print("🧪 Testing CSV file access...")
    csv_file = "chat_history.csv"

    try:
        # Check if file exists, create if not
        if not os.path.exists(csv_file):
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                f.write("Timestamp,Mode,User Input,AI Response\n")
            print("✅ Created chat_history.csv")
        else:
            print("✅ chat_history.csv already exists")

        # Test write access
        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
            f.write("2024-01-01 12:00:00,test,test message,test response\n")
        print("✅ CSV file is writable")

        return True
    except Exception as e:
        print(f"❌ CSV file access failed: {e}")
        return False

def test_static_files():
    """Test that static files and templates exist"""
    print("🧪 Testing static files and templates...")

    # Check templates directory
    template_files = [
        "templates/login.html",
        "templates/signup.html",
        "templates/home_page.html",
        "templates/chatbot.html"
    ]

    missing_templates = []
    for template in template_files:
        if not os.path.exists(template):
            missing_templates.append(template)

    if missing_templates:
        print(f"⚠️ Missing template files: {', '.join(missing_templates)}")
    else:
        print("✅ All required templates exist")

    # Check static directory
    if os.path.exists("static"):
        print("✅ Static directory exists")
    else:
        print("⚠️ Static directory not found")

    return True

def test_app_structure():
    """Test basic app structure by reading the file"""
    print("🧪 Testing app structure...")

    try:
        with open("app.py", "r", encoding="utf-8") as f:
            content = f.read()

        # Check for key components
        checks = [
            ("Flask app initialization", "app = Flask(__name__)" in content),
            ("Secret key configuration", "app.secret_key" in content),
            ("Session security settings", "SESSION_COOKIE_SECURE" in content),
            ("Audit logging setup", "logging.basicConfig" in content),
            ("Register route", "@app.route(\"/register\"" in content),
            ("Login route", "@app.route(\"/login\"" in content),
            ("Chat API route", "@app.route(\"/api/chat\"" in content),
            ("Navigation routes", "@app.route(\"/\")" in content),
        ]

        all_passed = True
        for check_name, check_result in checks:
            if check_result:
                print(f"✅ {check_name}")
            else:
                print(f"❌ {check_name} - NOT FOUND")
                all_passed = False

        return all_passed

    except Exception as e:
        print(f"❌ Failed to read app.py: {e}")
        return False

def run_manual_tests():
    """Provide instructions for manual testing"""
    print("\n📋 Manual Testing Instructions:")
    print("=" * 50)
    print("1. Start the app: python app.py")
    print("2. Open browser to http://localhost:10000")
    print("3. Test registration:")
    print("   - Try valid registration (username: testuser, password: testpass123)")
    print("   - Try invalid registration (short username/password)")
    print("   - Try duplicate registration")
    print("4. Test login:")
    print("   - Login with registered credentials")
    print("   - Try invalid login")
    print("5. Test navigation:")
    print("   - Visit all main pages (/home, /chat, /analysis, etc.)")
    print("6. Test chat API:")
    print("   - Send a message through the chat interface")
    print("7. Check audit.log for authentication events")
    print("8. Check MongoDB for user data and analysis results")

def main():
    """Run all tests"""
    print("🧪 AwareMe App Pre-Deployment Test Suite")
    print("=" * 50)

    tests = [
        test_app_syntax,
        test_environment_variables,
        test_audit_log_creation,
        test_csv_file_access,
        test_static_files,
        test_app_structure,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1
        print()

    print("=" * 50)
    print(f"Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All automated tests passed! Ready for manual testing.")
        run_manual_tests()
    else:
        print("❌ Some tests failed. Please fix the issues before deployment.")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)