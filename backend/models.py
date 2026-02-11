from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class SubscriptionTier(str, Enum):
    FREE = "free"
    BASIC = "basic"
    STANDARD = "standard"
    PREMIUM = "premium"


class ListingType(str, Enum):
    SALE = "sale"
    RENT = "rent"


class ListingStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REMOVED = "removed"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


# Request Models
class UserSignup(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    phone: Optional[str] = None
    whatsapp: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class CreateListing(BaseModel):
    brand: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=1990, le=2030)
    mileage: int = Field(ge=0)
    transmission: str = Field(pattern="^(Automatic|Manual)$")
    condition: str
    price: int = Field(ge=0)
    location: str
    notes: Optional[str] = None
    listing_type: ListingType
    daily_rate: Optional[int] = Field(default=None, ge=0)  # For rentals
    seats: Optional[int] = Field(default=None, ge=1, le=12)  # For rentals
    images: Optional[List[str]] = []


class UpdateListing(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    mileage: Optional[int] = None
    transmission: Optional[str] = None
    condition: Optional[str] = None
    price: Optional[int] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    daily_rate: Optional[int] = None
    seats: Optional[int] = None
    status: Optional[ListingStatus] = None


class InitiateSubscription(BaseModel):
    tier: SubscriptionTier
    payment_method: str = "orange_money"  # orange_money, myzaka, manual


class OrangeMoneyCallback(BaseModel):
    order_id: str
    status: str
    transaction_id: str
    amount: float
    currency: str


# Response Models
class UserProfile(BaseModel):
    id: str
    email: str
    phone: Optional[str]
    whatsapp: Optional[str]
    current_tier: str
    subscription_expires_at: Optional[datetime]
    listing_count: int
    listing_limit: Optional[int]  # None means unlimited
    created_at: datetime


class ListingResponse(BaseModel):
    id: str
    user_id: str
    brand: str
    model: str
    year: int
    mileage: int
    transmission: str
    condition: str
    price: int
    location: str
    notes: Optional[str]
    listing_type: ListingType
    daily_rate: Optional[int]
    seats: Optional[int]
    images: List[str]
    status: ListingStatus
    created_at: datetime
    expires_at: datetime


class TierInfo(BaseModel):
    name: str
    price_pula: int
    listing_limit: Optional[int]
    features: List[str]


class PaymentInitResponse(BaseModel):
    payment_url: Optional[str]  # URL to redirect user for Orange Money
    transaction_id: str
    status: str
    message: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile


class SubscriptionStatusResponse(BaseModel):
    current_tier: str
    price_pula: int
    listing_limit: Optional[int]
    listing_count: int
    is_active: bool
    expires_at: Optional[datetime]
    days_remaining: Optional[int]
    can_create_listing: bool


class TransactionResponse(BaseModel):
    id: str
    amount_pula: int
    payment_method: str
    transaction_reference: Optional[str]
    status: str
    tier_name: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime]


class ConfirmPaymentRequest(BaseModel):
    transaction_id: str
    payment_reference: str  # User-provided reference from their mobile money receipt


class AdminApprovePayment(BaseModel):
    transaction_id: str
    admin_notes: Optional[str] = None


class SubscriptionDowngradeResponse(BaseModel):
    message: str
    previous_tier: str
    new_tier: str


class PaymentStatusResponse(BaseModel):
    transaction_id: str
    status: str
    tier_name: Optional[str]
    amount_pula: int
    message: str
