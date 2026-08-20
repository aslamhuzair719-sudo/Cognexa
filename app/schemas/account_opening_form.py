from typing import Literal, Optional

from pydantic import BaseModel, Field


class AccountOpeningFormFields(BaseModel):
    title: Optional[str] = Field(None, description="Title such as Mr, Mrs, Miss, Ms")
    surname: Optional[str] = Field(None, description="Applicant surname / family name")
    forenames: Optional[str] = Field(None, description="Applicant forenames / given names")
    applicant_name: Optional[str] = Field(
        None, description="Full applicant name (title + forenames + surname)"
    )
    age: Optional[str] = Field(None, description="Applicant age")
    father_name: Optional[str] = Field(None, description="Father's name")
    cnic_number: Optional[str] = Field(None, description="CNIC number")
    date_of_birth: Optional[str] = Field(None, description="Date of birth")
    gender: Optional[str] = Field(None, description="Gender")
    current_address: Optional[str] = Field(None, description="Current residential address")
    postcode: Optional[str] = Field(None, description="Post code / ZIP")
    last_address: Optional[str] = Field(None, description="Previous address if listed")
    date_of_entry_to_address: Optional[str] = Field(
        None, description="Date the applicant moved into the current address"
    )
    country_to_stay: Optional[str] = Field(None, description="Country of residence / stay")
    nationality: Optional[str] = Field(None, description="Nationality")
    home_phone: Optional[str] = Field(None, description="Home phone number")
    mobile_number: Optional[str] = Field(None, description="Mobile number")
    email: Optional[str] = Field(None, description="Email address")
    usa_residence: Optional[str] = Field(None, description="Yes/No: residence in the USA")
    usa_green_card: Optional[str] = Field(None, description="Yes/No: ever held a USA green card")
    tax_residence_country: Optional[str] = Field(
        None, description="Country of residence for tax purposes"
    )
    tin: Optional[str] = Field(None, description="Tax identification number (TIN)")
    company_name: Optional[str] = Field(None, description="Company name")
    designation: Optional[str] = Field(None, description="Designation")
    monthly_income: Optional[str] = Field(None, description="Monthly income")
    employee_id: Optional[str] = Field(None, description="Employee ID")


class AccountOpeningFormSchema(BaseModel):
    document_type: Literal["account_opening_form"] = "account_opening_form"
    fields: AccountOpeningFormFields
