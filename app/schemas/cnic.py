from typing import Optional, Literal
from pydantic import BaseModel, Field


class CNICFields(BaseModel):
    name: Optional[str] = Field(None, description="Full Name on CNIC")
    father_name: Optional[str] = Field(None, description="Father's Name on CNIC")
    cnic_number: Optional[str] = Field(
        None, description="13-digit CNIC in format XXXXX-XXXXXXX-X"
    )
    date_of_birth: Optional[str] = Field(None, description="Date of Birth on CNIC")
    issue_date: Optional[str] = Field(None, description="CNIC issue date")
    expiry_date: Optional[str] = Field(None, description="CNIC expiry date")
    gender: Optional[str] = Field(None, description="Gender (M or F)")
    address: Optional[str] = Field(None, description="Address on CNIC")


class CNICSchema(BaseModel):
    document_type: Literal["cnic"] = "cnic"
    fields: CNICFields
