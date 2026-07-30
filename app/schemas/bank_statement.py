from typing import Optional, Literal, List
from pydantic import BaseModel, Field


class TransactionItem(BaseModel):
    date: Optional[str] = Field(None, description="Transaction date")
    description: Optional[str] = Field(None, description="Transaction details / description")
    amount: Optional[str] = Field(None, description="Transaction amount")
    type: Optional[str] = Field(None, description="Type of transaction (credit/debit)")


class BankStatementFields(BaseModel):
    bank_name: Optional[str] = Field(None, description="Name of the bank")
    account_holder: Optional[str] = Field(None, description="Account holder full name")
    account_number: Optional[str] = Field(None, description="Account number")
    iban: Optional[str] = Field(None, description="IBAN identifier")
    statement_period: Optional[str] = Field(None, description="Statement duration period")
    opening_balance: Optional[str] = Field(None, description="Opening balance amount")
    closing_balance: Optional[str] = Field(None, description="Closing balance amount")
    transactions: List[TransactionItem] = Field(
        default_factory=list, description="List of transaction records"
    )


class BankStatementSchema(BaseModel):
    document_type: Literal["bank_statement"] = "bank_statement"
    fields: BankStatementFields
