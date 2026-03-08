from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime
import re


class UserCreate(BaseModel):
    name: str = Field(..., min_length=3)
    cpf_cnpj: str = Field(..., min_length=11)
    email: EmailStr
    password: str = Field(..., min_length=6)

    @field_validator('cpf_cnpj')
    @classmethod
    def validate_cpf_cnpj(cls, v: str) -> str:
        return re.sub(r'\D', '', v)


class UserLogin(BaseModel):
    cpf_cnpj: str
    password: str

    @field_validator('cpf_cnpj')
    @classmethod
    def validate_cpf_cnpj(cls, v: str) -> str:
        return re.sub(r'\D', '', v)


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    cpf_cnpj: str


class DepositRequest(BaseModel):
    amount: float = Field(..., gt=0, le=1000000, description="Deposit amount in BRL")
    description: str = Field(default="Deposit", max_length=200)


class DepositResponse(BaseModel):
    user_id: str
    amount: float
    previous_balance: float
    new_balance: float
    description: str
    timestamp: datetime


class BalanceResponse(BaseModel):
    user_id: str
    balance: float
    credit_limit: float
    available_credit: float
