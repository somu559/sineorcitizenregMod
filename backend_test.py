import requests
import sys
import json
import io
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

class RegistrationAPITester:
    def __init__(self, base_url="https://senior-id-portal.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def run_test(self, name, method, endpoint, expected_status, data=None, files=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}"
        headers = {}
        
        if data and not files:
            headers['Content-Type'] = 'application/json'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                if files:
                    response = requests.post(url, data=data, files=files)
                else:
                    response = requests.post(url, json=data, headers=headers)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"   Response: {json.dumps(response_data, indent=2)[:200]}...")
                except:
                    print(f"   Response: {response.text[:200]}...")
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:300]}...")
                self.failed_tests.append({
                    'name': name,
                    'expected': expected_status,
                    'actual': response.status_code,
                    'response': response.text[:300]
                })

            return success, response.json() if success and response.content else {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.failed_tests.append({
                'name': name,
                'error': str(e)
            })
            return False, {}

    def create_test_image(self, text_content):
        """Create a test image with text for OCR testing"""
        # Create a simple image with text
        img = Image.new('RGB', (800, 600), color='white')
        draw = ImageDraw.Draw(img)
        
        try:
            # Try to use a default font
            font = ImageFont.load_default()
        except:
            font = None
        
        # Add text to image
        lines = text_content.split('\n')
        y_position = 50
        for line in lines:
            draw.text((50, y_position), line, fill='black', font=font)
            y_position += 40
        
        # Convert to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        return img_bytes

    def test_root_endpoint(self):
        """Test root API endpoint"""
        success, response = self.run_test(
            "Root API Endpoint",
            "GET",
            "",
            200
        )
        return success

    def test_ocr_extract_valid_image(self):
        """Test OCR extraction with a valid test image"""
        # Create test image with Aadhaar-like content
        test_content = """Government of India
Aadhaar
Name: RAJESH KUMAR SHARMA
DOB: 15/08/1970
Address: 123 Main Street
New Delhi 110001
2345 6789 0123"""
        
        test_image = self.create_test_image(test_content)
        
        files = {'file': ('test_aadhaar.png', test_image, 'image/png')}
        
        success, response = self.run_test(
            "OCR Extract - Valid Image",
            "POST",
            "ocr/extract",
            200,
            files=files
        )
        
        if success and response:
            # Check if OCR response has expected structure
            expected_keys = ['success', 'extracted_text', 'parsed_data']
            if all(key in response for key in expected_keys):
                print(f"   ✅ OCR Response structure is correct")
                if response.get('success'):
                    print(f"   ✅ OCR extraction successful")
                    parsed_data = response.get('parsed_data', {})
                    if parsed_data.get('id_number'):
                        print(f"   ✅ ID number extracted: {parsed_data.get('id_number')}")
                    if parsed_data.get('full_name'):
                        print(f"   ✅ Name extracted: {parsed_data.get('full_name')}")
                else:
                    print(f"   ⚠️ OCR extraction failed: {response.get('error')}")
            else:
                print(f"   ❌ OCR Response missing expected keys")
                
        return success

    def test_ocr_extract_no_file(self):
        """Test OCR extraction without file"""
        success, response = self.run_test(
            "OCR Extract - No File",
            "POST",
            "ocr/extract",
            422  # Unprocessable Entity for missing file
        )
        return success

    def test_registration_valid_senior(self):
        """Test registration with valid senior citizen data"""
        registration_data = {
            "full_name": "Rajesh Kumar Sharma",
            "date_of_birth": "15/08/1970",  # Age 54
            "address": "123 Main Street, New Delhi 110001",
            "id_number": "234567890123",
            "id_type": "Aadhaar"
        }
        
        success, response = self.run_test(
            "Registration - Valid Senior Citizen",
            "POST",
            "registration",
            200,
            data=registration_data
        )
        
        if success and response:
            # Check registration response structure
            expected_keys = ['registration_id', 'full_name', 'age', 'created_at']
            if all(key in response for key in expected_keys):
                print(f"   ✅ Registration response structure is correct")
                reg_id = response.get('registration_id')
                if reg_id and reg_id.startswith('REG2025-'):
                    print(f"   ✅ Registration ID format correct: {reg_id}")
                age = response.get('age')
                if age and age >= 50:
                    print(f"   ✅ Age validation passed: {age} years")
                else:
                    print(f"   ❌ Age validation issue: {age} years")
            else:
                print(f"   ❌ Registration response missing expected keys")
                
        return success

    def test_registration_under_age(self):
        """Test registration with under-age person (should fail)"""
        registration_data = {
            "full_name": "Young Person",
            "date_of_birth": "15/08/2000",  # Age 24
            "address": "123 Young Street, City",
            "id_number": "123456789012",
            "id_type": "Aadhaar"
        }
        
        success, response = self.run_test(
            "Registration - Under Age (Should Fail)",
            "POST",
            "registration",
            400,  # Bad Request for age validation failure
            data=registration_data
        )
        return success

    def test_registration_missing_fields(self):
        """Test registration with missing required fields"""
        registration_data = {
            "full_name": "Incomplete Person",
            # Missing date_of_birth, address, id_number
            "id_type": "Aadhaar"
        }
        
        success, response = self.run_test(
            "Registration - Missing Fields",
            "POST",
            "registration",
            422,  # Unprocessable Entity for validation error
            data=registration_data
        )
        return success

    def test_get_registrations(self):
        """Test getting all registrations"""
        success, response = self.run_test(
            "Get All Registrations",
            "GET",
            "registrations",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✅ Registrations list returned: {len(response)} records")
        
        return success

def main():
    print("🚀 Starting Registration Module API Tests")
    print("=" * 60)
    
    tester = RegistrationAPITester()
    
    # Run all tests
    tests = [
        tester.test_root_endpoint,
        tester.test_ocr_extract_valid_image,
        tester.test_ocr_extract_no_file,
        tester.test_registration_valid_senior,
        tester.test_registration_under_age,
        tester.test_registration_missing_fields,
        tester.test_get_registrations
    ]
    
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"❌ Test failed with exception: {str(e)}")
            tester.failed_tests.append({
                'name': test.__name__,
                'error': str(e)
            })
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"Total Tests: {tester.tests_run}")
    print(f"Passed: {tester.tests_passed}")
    print(f"Failed: {len(tester.failed_tests)}")
    print(f"Success Rate: {(tester.tests_passed/tester.tests_run*100):.1f}%" if tester.tests_run > 0 else "0%")
    
    if tester.failed_tests:
        print("\n❌ FAILED TESTS:")
        for i, failure in enumerate(tester.failed_tests, 1):
            print(f"{i}. {failure['name']}")
            if 'error' in failure:
                print(f"   Error: {failure['error']}")
            else:
                print(f"   Expected: {failure['expected']}, Got: {failure['actual']}")
                print(f"   Response: {failure['response']}")
    
    return 0 if tester.tests_passed == tester.tests_run else 1

if __name__ == "__main__":
    sys.exit(main())