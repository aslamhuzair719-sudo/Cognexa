from typing import Optional, Literal
from pydantic import BaseModel, Field


class PayslipFields(BaseModel):
    company_name: Optional[str] = Field(None, description="Name of the employing company")
    employee_name: Optional[str] = Field(None, description="Full name of the employee")
    employee_id: Optional[str] = Field(None, description="Employee ID / Number")
    designation: Optional[str] = Field(None, description="Job title / designation")
    email: Optional[str] = Field(None, description="Email address of the employee")
    phone: Optional[str] = Field(None, description="Phone number of the employee")
    payslip_number: Optional[str] = Field(None, description="Payslip reference number")
    period_start: Optional[str] = Field(None, description="Start date of pay period")
    period_end: Optional[str] = Field(None, description="End date of pay period")
    payslip_period: Optional[str] = Field(None, description="Payslip period as a single string")
    gross_salary: Optional[str] = Field(None, description="Gross salary amount")
    net_pay: Optional[str] = Field(None, description="Net pay amount")
    net_salary: Optional[str] = Field(None, description="Alias for net salary")
    deductions: Optional[str] = Field(None, description="Total deductions amount")
    overtime: Optional[str] = Field(None, description="Overtime payment amount")


class PayslipSchema(BaseModel):
    document_type: Literal["payslip"] = "payslip"
    fields: PayslipFields
