from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, date
import json
import base64
import io
from google.cloud import vision
from google.oauth2 import service_account
import re

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Google Vision API setup
google_creds_json = os.environ.get('GOOGLE_CLOUD_CREDENTIALS_JSON')
if google_creds_json:
    credentials_dict = json.loads(google_creds_json)
    credentials = service_account.Credentials.from_service_account_info(credentials_dict)
    vision_client = vision.ImageAnnotatorClient(credentials=credentials)
else:
    vision_client = None

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Define Models
class RegistrationCreate(BaseModel):
    full_name: str
    date_of_birth: str
    address: str
    id_number: str
    id_type: str
    extracted_data: Optional[Dict[str, Any]] = None

class Registration(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    registration_id: str
    full_name: str
    date_of_birth: str
    age: int
    address: str
    id_number: str
    id_type: str
    extracted_data: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OCRResponse(BaseModel):
    success: bool
    extracted_text: str
    parsed_data: Dict[str, Any]
    error: Optional[str] = None

def calculate_age(birth_date_str: str) -> int:
    """Calculate age from date of birth string (DD/MM/YYYY or DD-MM-YYYY or YYYY-MM-DD)"""
    try:
        # Try different date formats
        for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d.%m.%Y']:
            try:
                birth_date = datetime.strptime(birth_date_str, fmt).date()
                today = datetime.now(timezone.utc).date()
                age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                return age
            except ValueError:
                continue
        return 0
    except Exception as e:
        logging.error(f"Error calculating age: {str(e)}")
        return 0

def generate_registration_id() -> str:
    """Generate unique registration ID in format REG2025-XXXX"""
    year = datetime.now(timezone.utc).year
    random_suffix = str(uuid.uuid4())[:4].upper()
    return f"REG{year}-{random_suffix}"

def extract_aadhaar_number(text: str) -> Optional[str]:
    """Extract Aadhaar number from text using regex"""
    # Pattern: 12 digits, not starting with 0 or 1
    patterns = [
        r'[2-9]\d{3}\s?\d{4}\s?\d{4}',  # With spaces
        r'[2-9]\d{11}'  # Without spaces
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            number = match.group(0)
            # Remove spaces and return
            return re.sub(r'\s', '', number)
    return None

def extract_pan_number(text: str) -> Optional[str]:
    """Extract PAN number from text using regex"""
    # Pattern: 5 letters, 4 digits, 1 letter
    pattern = r'[A-Z]{5}[0-9]{4}[A-Z]{1}'
    match = re.search(pattern, text.upper())
    if match:
        return match.group(0)
    return None

def extract_date_of_birth(text: str) -> Optional[str]:
    """Extract date of birth from text"""
    patterns = [
        r'\b(\d{2}[/-]\d{2}[/-]\d{4})\b',  # DD/MM/YYYY or DD-MM-YYYY
        r'\b(\d{4}[/-]\d{2}[/-]\d{2})\b',  # YYYY-MM-DD
        r'DOB[:\s]*(\d{2}[/-]\d{2}[/-]\d{4})',  # DOB: DD/MM/YYYY
        r'Birth[:\s]*(\d{2}[/-]\d{2}[/-]\d{4})',  # Birth: DD/MM/YYYY
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1) if match.lastindex else match.group(0)
    return None

def extract_name_from_text(text: str, id_type: str) -> Optional[str]:
    """Extract name from text based on ID type"""
    lines = text.split('\n')
    name_candidates = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        # Look for name patterns
        if any(keyword in line.lower() for keyword in ['name', 'naam']):
            # Name is likely in the next line or after colon
            if ':' in line:
                potential_name = line.split(':', 1)[1].strip()
                if len(potential_name) > 2:
                    name_candidates.append(potential_name)
            elif i + 1 < len(lines):
                potential_name = lines[i + 1].strip()
                if len(potential_name) > 2:
                    name_candidates.append(potential_name)
    
    # Return first candidate or try to find capitalized words
    if name_candidates:
        return name_candidates[0]
    
    # Fallback: look for lines with capital letters
    for line in lines[:5]:  # Check first 5 lines
        words = line.strip().split()
        if len(words) >= 2 and all(word[0].isupper() if word else False for word in words[:2]):
            return line.strip()
    
    return None

def parse_ocr_text(full_text: str) -> Dict[str, Any]:
    """Parse OCR text to extract structured data"""
    parsed_data = {
        'full_name': '',
        'date_of_birth': '',
        'id_number': '',
        'id_type': '',
        'address': ''
    }
    
    # Detect ID type and extract number
    aadhaar = extract_aadhaar_number(full_text)
    pan = extract_pan_number(full_text)
    
    if aadhaar:
        parsed_data['id_number'] = aadhaar
        parsed_data['id_type'] = 'Aadhaar'
    elif pan:
        parsed_data['id_number'] = pan
        parsed_data['id_type'] = 'PAN'
    
    # Extract DOB
    dob = extract_date_of_birth(full_text)
    if dob:
        parsed_data['date_of_birth'] = dob
    
    # Extract name
    name = extract_name_from_text(full_text, parsed_data['id_type'])
    if name:
        parsed_data['full_name'] = name
    
    # Extract address (simplified - take lines that look like address)
    lines = full_text.split('\n')
    address_parts = []
    for i, line in enumerate(lines):
        if any(keyword in line.lower() for keyword in ['address', 'addr', 'pincode', 'pin']):
            # Collect next few lines as address
            for j in range(i+1, min(i+4, len(lines))):
                if lines[j].strip():
                    address_parts.append(lines[j].strip())
            break
    
    if address_parts:
        parsed_data['address'] = ', '.join(address_parts)
    
    return parsed_data

@api_router.post("/ocr/extract", response_model=OCRResponse)
async def extract_text_from_id(file: UploadFile = File(...)):
    """Extract text from uploaded ID card using Google Vision API"""
    if not vision_client:
        raise HTTPException(status_code=500, detail="Vision API not configured")
    
    try:
        # Read file content
        contents = await file.read()
        
        # Validate file size (max 10MB)
        if len(contents) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")
        
        # Create Vision API image object
        image = vision.Image(content=contents)
        
        # Perform text detection
        response = vision_client.document_text_detection(image=image)
        
        if response.error.message:
            raise HTTPException(status_code=500, detail=f"Vision API error: {response.error.message}")
        
        # Extract full text
        full_text = response.full_text_annotation.text if response.full_text_annotation else ""
        
        if not full_text:
            return OCRResponse(
                success=False,
                extracted_text="",
                parsed_data={},
                error="No text detected in the image"
            )
        
        # Parse the text to extract structured data
        parsed_data = parse_ocr_text(full_text)
        
        return OCRResponse(
            success=True,
            extracted_text=full_text,
            parsed_data=parsed_data
        )
        
    except Exception as e:
        logging.error(f"OCR extraction error: {str(e)}")
        return OCRResponse(
            success=False,
            extracted_text="",
            parsed_data={},
            error=str(e)
        )

@api_router.post("/registration", response_model=Registration)
async def create_registration(registration: RegistrationCreate):
    """Create a new registration"""
    try:
        # Calculate age
        age = calculate_age(registration.date_of_birth)
        
        # Validate age (must be 50 or above)
        if age < 50:
            raise HTTPException(
                status_code=400, 
                detail=f"Age must be 50 or above. Current age: {age}"
            )
        
        # Generate unique registration ID
        reg_id = generate_registration_id()
        
        # Create registration object
        reg_obj = Registration(
            registration_id=reg_id,
            full_name=registration.full_name,
            date_of_birth=registration.date_of_birth,
            age=age,
            address=registration.address,
            id_number=registration.id_number,
            id_type=registration.id_type,
            extracted_data=registration.extracted_data
        )
        
        # Save to database
        doc = reg_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await db.registrations.insert_one(doc)
        
        return reg_obj
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Registration creation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/registrations", response_model=List[Registration])
async def get_registrations():
    """Get all registrations"""
    try:
        registrations = await db.registrations.find({}, {"_id": 0}).to_list(1000)
        
        # Convert ISO string timestamps back to datetime objects
        for reg in registrations:
            if isinstance(reg.get('created_at'), str):
                reg['created_at'] = datetime.fromisoformat(reg['created_at'])
        
        return registrations
    except Exception as e:
        logging.error(f"Error fetching registrations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/")
async def root():
    return {"message": "Registration Module API", "status": "active"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()