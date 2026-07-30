"""Customer account-opening application form schemas."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class PersonalInfo(BaseModel):
    full_name: str = Field(..., min_length=2, description="Customer's full name")
    age: str = Field(..., min_length=1, description="Customer's age")
    email: EmailStr
    mobile_number: str = Field(..., min_length=10, description="Phone / mobile number")


class CnicInfo(BaseModel):
    full_name: str = Field(..., min_length=2, description="Full name as printed on CNIC")
    father_name: str = Field(..., min_length=2, description="Father's name")
    cnic_number: str = Field(..., description="CNIC in format XXXXX-XXXXXXX-X")
    date_of_birth: str = Field(..., description="Date of birth as on CNIC")
    issue_date: str = Field(..., description="CNIC issue date")
    expiry_date: str = Field(..., description="CNIC expiry date")
    country_to_stay: str = Field(..., min_length=2, description="Country of stay")
    gender: str = Field(..., min_length=1, description="Gender")


class EmploymentInfo(BaseModel):
    company_name: str = Field(..., min_length=2)
    designation: str = Field(..., min_length=2)
    monthly_income: str = Field(..., description="Declared monthly salary")
    employee_id: str = Field(..., min_length=1)


class ApplicationForm(BaseModel):
    """Multi-phase digital account opening application payload."""

    personal: PersonalInfo
    cnic: CnicInfo
    employment: EmploymentInfo
