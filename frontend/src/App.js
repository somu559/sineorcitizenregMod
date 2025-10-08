import { useState, useEffect } from 'react';
import '@/App.css';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { Loader2, Upload, CheckCircle2, AlertCircle, Moon, Sun, User, Calendar, MapPin, CreditCard, Sparkles } from 'lucide-react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function App() {
  const [darkMode, setDarkMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [formData, setFormData] = useState({
    full_name: '',
    date_of_birth: '',
    address: '',
    id_number: '',
    id_type: 'Aadhaar'
  });
  const [extractedData, setExtractedData] = useState(null);
  const [registrationSuccess, setRegistrationSuccess] = useState(false);
  const [registrationId, setRegistrationId] = useState('');
  const [ageError, setAgeError] = useState('');
  const [showSuccess, setShowSuccess] = useState(false);

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [darkMode]);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('image/')) {
      toast.error('Please upload a valid image file');
      return;
    }

    // Validate file size (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
      toast.error('File size should not exceed 10MB');
      return;
    }

    setUploadedFile(file);
    setPreviewUrl(URL.createObjectURL(file));

    // Perform OCR
    await performOCR(file);
  };

  const performOCR = async (file) => {
    setOcrLoading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post(`${API}/ocr/extract`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });

      if (response.data.success) {
        const parsed = response.data.parsed_data;
        setExtractedData(response.data);
        
        // Auto-fill form with extracted data
        setFormData(prev => ({
          ...prev,
          full_name: parsed.full_name || prev.full_name,
          date_of_birth: parsed.date_of_birth || prev.date_of_birth,
          address: parsed.address || prev.address,
          id_number: parsed.id_number || prev.id_number,
          id_type: parsed.id_type || prev.id_type
        }));

        toast.success('Data extracted successfully! Please review and edit if needed.');
      } else {
        toast.error(response.data.error || 'Failed to extract data from image');
      }
    } catch (error) {
      console.error('OCR error:', error);
      toast.error('Failed to process image. Please try again.');
    } finally {
      setOcrLoading(false);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    
    // Clear age error when DOB changes
    if (name === 'date_of_birth') {
      setAgeError('');
    }
  };

  const calculateAge = (dobString) => {
    try {
      // Try different date formats
      let birthDate;
      const formats = [
        { regex: /^(\d{2})[\/\-](\d{2})[\/\-](\d{4})$/, order: [2, 1, 0] }, // DD/MM/YYYY or DD-MM-YYYY
        { regex: /^(\d{4})[\/\-](\d{2})[\/\-](\d{2})$/, order: [0, 1, 2] }  // YYYY-MM-DD
      ];

      for (const format of formats) {
        const match = dobString.match(format.regex);
        if (match) {
          const [year, month, day] = format.order.map(i => parseInt(match[i + 1]));
          birthDate = new Date(year, month - 1, day);
          break;
        }
      }

      if (!birthDate) return null;

      const today = new Date();
      let age = today.getFullYear() - birthDate.getFullYear();
      const monthDiff = today.getMonth() - birthDate.getMonth();
      
      if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birthDate.getDate())) {
        age--;
      }
      
      return age;
    } catch (error) {
      return null;
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setAgeError('');

    // Validate required fields
    if (!formData.full_name || !formData.date_of_birth || !formData.address || !formData.id_number) {
      toast.error('Please fill in all required fields');
      return;
    }

    // Client-side age validation
    const age = calculateAge(formData.date_of_birth);
    if (age !== null && age < 50) {
      setAgeError(`Age must be 50 or above. Your age: ${age} years`);
      toast.error('Age requirement not met');
      return;
    }

    setLoading(true);

    try {
      const response = await axios.post(`${API}/registration`, {
        ...formData,
        extracted_data: extractedData?.parsed_data || null
      });

      setRegistrationId(response.data.registration_id);
      setRegistrationSuccess(true);
      setShowSuccess(true);
      toast.success('Registration completed successfully!');

      // Reset form after 3 seconds
      setTimeout(() => {
        resetForm();
      }, 5000);
    } catch (error) {
      console.error('Registration error:', error);
      const errorMessage = error.response?.data?.detail || 'Registration failed. Please try again.';
      
      if (errorMessage.includes('Age must be 50')) {
        setAgeError(errorMessage);
      }
      
      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setFormData({
      full_name: '',
      date_of_birth: '',
      address: '',
      id_number: '',
      id_type: 'Aadhaar'
    });
    setUploadedFile(null);
    setPreviewUrl(null);
    setExtractedData(null);
    setRegistrationSuccess(false);
    setShowSuccess(false);
    setRegistrationId('');
    setAgeError('');
  };

  return (
    <div className={`min-h-screen transition-colors duration-300 ${darkMode ? 'dark' : ''}`}>
      <div className="app-container">
        {/* Header */}
        <header className="header">
          <div className="header-content">
            <div className="header-title">
              <Sparkles className="header-icon" />
              <h1>Senior Citizen Registration</h1>
            </div>
            <Button
              data-testid="theme-toggle-btn"
              variant="outline"
              size="icon"
              onClick={() => setDarkMode(!darkMode)}
              className="theme-toggle"
            >
              {darkMode ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
            </Button>
          </div>
        </header>

        {/* Main Content */}
        <main className="main-content">
          {!showSuccess ? (
            <Card className="registration-card" data-testid="registration-form-card">
              <CardHeader className="card-header">
                <CardTitle className="card-title">Register Your Details</CardTitle>
                <CardDescription className="card-description">
                  Upload your ID card for automatic data extraction, or fill in the form manually
                </CardDescription>
              </CardHeader>
              <CardContent className="card-content">
                <form onSubmit={handleSubmit} className="registration-form">
                  {/* File Upload Section */}
                  <div className="upload-section">
                    <Label htmlFor="file-upload" className="form-label">
                      Upload ID Card (Aadhaar / PAN)
                      <span className="tooltip-icon" title="Upload a clear image of your ID card for automatic data extraction">
                        ℹ️
                      </span>
                    </Label>
                    <div className="upload-container">
                      <input
                        id="file-upload"
                        data-testid="file-upload-input"
                        type="file"
                        accept="image/*"
                        onChange={handleFileUpload}
                        className="hidden"
                      />
                      <label htmlFor="file-upload" className="upload-label">
                        {ocrLoading ? (
                          <div className="upload-loading">
                            <Loader2 className="animate-spin" size={40} />
                            <p>Extracting data...</p>
                          </div>
                        ) : previewUrl ? (
                          <div className="upload-preview">
                            <img src={previewUrl} alt="ID Card Preview" className="preview-image" />
                            <p className="upload-change-text">Click to change image</p>
                          </div>
                        ) : (
                          <div className="upload-placeholder">
                            <Upload size={48} />
                            <p className="upload-text">Click to upload ID card</p>
                            <p className="upload-subtext">Supported: JPG, PNG (Max 10MB)</p>
                          </div>
                        )}
                      </label>
                    </div>
                  </div>

                  {/* Form Fields */}
                  <div className="form-grid">
                    {/* Full Name */}
                    <div className="form-field">
                      <Label htmlFor="full_name" className="form-label">
                        <User size={18} />
                        Full Name *
                      </Label>
                      <Input
                        id="full_name"
                        data-testid="full-name-input"
                        name="full_name"
                        value={formData.full_name}
                        onChange={handleInputChange}
                        placeholder="Enter your full name"
                        required
                        className="form-input"
                      />
                    </div>

                    {/* Date of Birth */}
                    <div className="form-field">
                      <Label htmlFor="date_of_birth" className="form-label">
                        <Calendar size={18} />
                        Date of Birth *
                        <span className="tooltip-icon" title="Format: DD/MM/YYYY or DD-MM-YYYY">
                          ℹ️
                        </span>
                      </Label>
                      <Input
                        id="date_of_birth"
                        data-testid="dob-input"
                        name="date_of_birth"
                        value={formData.date_of_birth}
                        onChange={handleInputChange}
                        placeholder="DD/MM/YYYY"
                        required
                        className="form-input"
                      />
                      {ageError && (
                        <p className="error-text" data-testid="age-error-message">
                          <AlertCircle size={16} />
                          {ageError}
                        </p>
                      )}
                    </div>

                    {/* ID Type */}
                    <div className="form-field">
                      <Label htmlFor="id_type" className="form-label">
                        <CreditCard size={18} />
                        ID Type
                      </Label>
                      <select
                        id="id_type"
                        data-testid="id-type-select"
                        name="id_type"
                        value={formData.id_type}
                        onChange={handleInputChange}
                        className="form-select"
                      >
                        <option value="Aadhaar">Aadhaar Card</option>
                        <option value="PAN">PAN Card</option>
                        <option value="Other">Other</option>
                      </select>
                    </div>

                    {/* ID Number */}
                    <div className="form-field">
                      <Label htmlFor="id_number" className="form-label">
                        <CreditCard size={18} />
                        ID Number *
                      </Label>
                      <Input
                        id="id_number"
                        data-testid="id-number-input"
                        name="id_number"
                        value={formData.id_number}
                        onChange={handleInputChange}
                        placeholder="Enter ID number"
                        required
                        className="form-input"
                      />
                    </div>
                  </div>

                  {/* Address */}
                  <div className="form-field">
                    <Label htmlFor="address" className="form-label">
                      <MapPin size={18} />
                      Address *
                    </Label>
                    <Textarea
                      id="address"
                      data-testid="address-input"
                      name="address"
                      value={formData.address}
                      onChange={handleInputChange}
                      placeholder="Enter your complete address"
                      required
                      rows={4}
                      className="form-textarea"
                    />
                  </div>

                  {/* Submit Button */}
                  <Button
                    data-testid="submit-registration-btn"
                    type="submit"
                    disabled={loading || ocrLoading}
                    className="submit-button"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="animate-spin mr-2" size={20} />
                        Processing...
                      </>
                    ) : (
                      'Complete Registration'
                    )}
                  </Button>
                </form>
              </CardContent>
            </Card>
          ) : (
            <Card className="success-card" data-testid="success-card">
              <CardContent className="success-content">
                <div className="success-animation">
                  <CheckCircle2 className="success-icon" size={80} />
                </div>
                <h2 className="success-title">Registration Successful!</h2>
                <p className="success-description">Your registration has been completed successfully.</p>
                <div className="registration-id-box" data-testid="registration-id-display">
                  <p className="registration-id-label">Your Registration ID:</p>
                  <p className="registration-id">{registrationId}</p>
                </div>
                <p className="success-note">Please save this ID for future reference.</p>
                <Button
                  data-testid="new-registration-btn"
                  onClick={resetForm}
                  className="new-registration-button"
                >
                  Register Another Person
                </Button>
              </CardContent>
            </Card>
          )}
        </main>

        {/* Footer */}
        <footer className="footer">
          <p>© 2025 Senior Citizen Registration Portal. Designed for ease and accessibility.</p>
        </footer>
      </div>
    </div>
  );
}

export default App;