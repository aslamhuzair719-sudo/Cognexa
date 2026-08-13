from typing import Literal, Optional

from pydantic import BaseModel, Field


class AccountOpeningFormFields(BaseModel):
    applicant_name: Optional[str] = Field(None, description="Applicant full name")
    age: Optional[str] = Field(None, description="Applicant age")
    father_name: Optional[str] = Field(None, description="Father's name")
    cnic_number: Optional[str] = Field(None, description="CNIC number")
    date_of_birth: Optional[str] = Field(None, description="Date of birth")
    gender: Optional[str] = Field(None, description="Gender")
    country_to_stay: Optional[str] = Field(None, description="Country of stay")
    mobile_number: Optional[str] = Field(None, description="Mobile number")
    email: Optional[str] = Field(None, description="Email address")
    company_name: Optional[str] = Field(None, description="Company name")
    designation: Optional[str] = Field(None, description="Designation")
    monthly_income: Optional[str] = Field(None, description="Monthly income")
    employee_id: Optional[str] = Field(None, description="Employee ID")


class AccountOpeningFormSchema(BaseModel):
    document_type: Literal["account_opening_form"] = "account_opening_form"
    fields: AccountOpeningFormFields
