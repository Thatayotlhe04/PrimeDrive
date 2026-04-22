from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
import requests
import uuid
import hmac
import hashlib
import base64
import json
import logging

from config import get_settings, Settings
from models import *

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("primedrive")

app = FastAPI(title="PrimeDrive API", version="1.0.0")
settings = get_settings()
security = HTTPBearer()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5500", "*"],  # Update in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase client
supabase: Client = create_client(settings.supabase_url, settings.supabase_key)


# ========================================
# Orange Money Integration Helper
# ========================================
class OrangeMoneyClient:
    """Handles Orange Money Web Pay API integration for Botswana"""

    def __init__(self, api_key: str, merchant_id: str, api_url: str):
        self.api_key = api_key
        self.merchant_id = merchant_id
        self.api_url = api_url.rstrip("/")
        self._access_token = None
        self._token_expires_at = None

    def _get_access_token(self) -> str:
        """Get or refresh the OAuth2 access token from Orange API"""
        now = datetime.now(timezone.utc)
        if self._access_token and self._token_expires_at and now < self._token_expires_at:
            return self._access_token

        try:
            auth_header = base64.b64encode(self.api_key.encode()).decode()
            resp = requests.post(
                "https://api.orange.com/oauth/v3/token",
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expires_at = now + timedelta(seconds=data.get("expires_in", 3500))
            return self._access_token
        except Exception as e:
            logger.error(f"Orange Money token error: {e}")
            raise HTTPException(status_code=502, detail="Payment service unavailable")

    def initiate_payment(
        self, order_id: str, amount: int, currency: str = "BWP",
        notify_url: str = "", return_url: str = "", cancel_url: str = ""
    ) -> dict:
        """Initiate a web payment session with Orange Money"""
        token = self._get_access_token()
        payload = {
            "merchant_key": self.merchant_id,
            "currency": currency,
            "order_id": order_id,
            "amount": amount,
            "return_url": return_url or f"{settings.frontend_url}/payment/success",
            "cancel_url": cancel_url or f"{settings.frontend_url}/payment/cancel",
            "notif_url": notify_url or f"{settings.frontend_url}/api/webhooks/orange-money",
            "lang": "en",
        }
        try:
            resp = requests.post(
                f"{self.api_url}/webpayment",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Orange Money initiate error: {e}")
            raise HTTPException(status_code=502, detail="Could not initiate payment with Orange Money")

    def check_transaction_status(self, order_id: str, amount: int) -> dict:
        """Poll the transaction status for a given order"""
        token = self._get_access_token()
        try:
            resp = requests.post(
                f"{self.api_url}/transactionstatus",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "order_id": order_id,
                    "amount": amount,
                    "pay_token": "",  # Orange fills this
                },
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Orange Money status check error: {e}")
            return {"status": "UNKNOWN"}


# Instantiate Orange Money client
orange_money = OrangeMoneyClient(
    api_key=settings.orange_money_api_key,
    merchant_id=settings.orange_money_merchant_id,
    api_url=settings.orange_money_api_url,
)


# ========================================
# Auth Helpers
# ========================================
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token and return user"""
    try:
        token = credentials.credentials
        # Verify token with Supabase
        user_response = supabase.auth.get_user(token)

        if not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )

        return user_response.user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )


async def get_user_profile(user_id: str) -> UserProfile:
    """Get full user profile with tier info"""
    result = supabase.from_("users") \
        .select("*, subscription_tiers!current_tier_id(*)") \
        .eq("id", user_id) \
        .single() \
        .execute()

    user_data = result.data

    # Count active listings
    listings_count = supabase.from_("car_listings") \
        .select("*", count="exact") \
        .eq("user_id", user_id) \
        .eq("status", "active") \
        .execute()

    return UserProfile(
        id=user_data["id"],
        email=user_data.get("email", ""),
        phone=user_data.get("phone"),
        whatsapp=user_data.get("whatsapp"),
        current_tier=user_data["subscription_tiers"]["name"],
        subscription_expires_at=user_data.get("subscription_expires_at"),
        listing_count=listings_count.count or 0,
        listing_limit=user_data["subscription_tiers"]["listing_limit"],
        created_at=user_data["created_at"]
    )


async def check_and_enforce_subscription(user_id: str) -> dict:
    """
    Check if user's subscription is still valid.
    If expired, auto-downgrade to free tier and return updated info.
    Returns dict with tier info and active status.
    """
    result = supabase.from_("users") \
        .select("*, subscription_tiers!current_tier_id(*)") \
        .eq("id", user_id) \
        .single() \
        .execute()

    user_data = result.data
    tier = user_data["subscription_tiers"]
    expires_at = user_data.get("subscription_expires_at")

    # Free tier never expires
    if tier["name"] == "free":
        return {
            "tier": tier,
            "is_active": True,
            "expires_at": None,
            "was_downgraded": False
        }

    # Check expiry for paid tiers
    if expires_at:
        expiry_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)

        if now > expiry_dt:
            # Subscription expired — downgrade to free
            free_tier = supabase.from_("subscription_tiers") \
                .select("*") \
                .eq("name", "free") \
                .single() \
                .execute()

            supabase.from_("users").update({
                "current_tier_id": free_tier.data["id"],
                "subscription_expires_at": None
            }).eq("id", user_id).execute()

            logger.info(f"User {user_id} downgraded from {tier['name']} to free (expired)")

            return {
                "tier": free_tier.data,
                "is_active": True,
                "expires_at": None,
                "was_downgraded": True,
                "previous_tier": tier["name"]
            }

    return {
        "tier": tier,
        "is_active": True,
        "expires_at": expires_at,
        "was_downgraded": False
    }


async def activate_subscription(user_id: str, tier_id: str, duration_days: int = 30):
    """Activate or renew a subscription for a user"""
    now = datetime.now(timezone.utc)

    # Check if user has an active non-expired subscription for stacking
    user_result = supabase.from_("users") \
        .select("subscription_expires_at") \
        .eq("id", user_id) \
        .single() \
        .execute()

    current_expires = user_result.data.get("subscription_expires_at")
    if current_expires:
        current_expires_dt = datetime.fromisoformat(current_expires.replace("Z", "+00:00"))
        # If still active, extend from current expiry
        if current_expires_dt > now:
            new_expires = current_expires_dt + timedelta(days=duration_days)
        else:
            new_expires = now + timedelta(days=duration_days)
    else:
        new_expires = now + timedelta(days=duration_days)

    supabase.from_("users").update({
        "current_tier_id": tier_id,
        "subscription_expires_at": new_expires.isoformat()
    }).eq("id", user_id).execute()

    logger.info(f"User {user_id} subscription activated, tier={tier_id}, expires={new_expires.isoformat()}")


# ========================================
# Auth Endpoints
# ========================================
@app.post("/auth/signup", response_model=AuthResponse)
async def signup(user_data: UserSignup):
    """Register a new user"""
    try:
        # Sign up with Supabase Auth
        auth_response = supabase.auth.sign_up({
            "email": user_data.email,
            "password": user_data.password
        })

        if not auth_response.user:
            raise HTTPException(status_code=400, detail="Signup failed")

        # Create user profile in users table
        supabase.from_("users").insert({
            "id": auth_response.user.id,
            "phone": user_data.phone,
            "whatsapp": user_data.whatsapp,
        }).execute()

        # Get full profile
        profile = await get_user_profile(auth_response.user.id)

        return AuthResponse(
            access_token=auth_response.session.access_token,
            user=profile
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/auth/login", response_model=AuthResponse)
async def login(credentials: UserLogin):
    """Login user"""
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })

        if not auth_response.session:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        profile = await get_user_profile(auth_response.user.id)

        return AuthResponse(
            access_token=auth_response.session.access_token,
            user=profile
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")


@app.get("/auth/me", response_model=UserProfile)
async def get_me(user=Depends(get_current_user)):
    """Get current user profile"""
    return await get_user_profile(user.id)


# ========================================
# Subscription Endpoints
# ========================================
@app.get("/tiers", response_model=List[TierInfo])
async def get_tiers():
    """Get all subscription tiers"""
    result = supabase.from_("subscription_tiers").select("*").order("price_pula").execute()

    tier_features = {
        "free": ["1 active listing", "90-day duration", "In-app support"],
        "basic": ["3 active listings", "90-day duration", "Priority in-app support", "Edit listings"],
        "standard": ["10 active listings", "90-day duration", "Priority support", "Featured badge"],
        "premium": ["Unlimited listings", "90-day duration", "Top placement", "Verified badge", "24/7 support"]
    }

    return [
        TierInfo(
            name=tier["name"],
            price_pula=tier["price_pula"],
            listing_limit=tier["listing_limit"],
            features=tier_features.get(tier["name"], [])
        )
        for tier in result.data
    ]


@app.get("/subscriptions/status", response_model=SubscriptionStatusResponse)
async def get_subscription_status(user=Depends(get_current_user)):
    """Get current user's subscription status with expiry enforcement"""
    sub_info = await check_and_enforce_subscription(user.id)
    tier = sub_info["tier"]

    # Count active listings
    listings_count = supabase.from_("car_listings") \
        .select("*", count="exact") \
        .eq("user_id", user.id) \
        .eq("status", "active") \
        .execute()

    listing_count = listings_count.count or 0
    listing_limit = tier["listing_limit"]

    # Calculate days remaining
    days_remaining = None
    if sub_info["expires_at"]:
        expiry_dt = datetime.fromisoformat(sub_info["expires_at"].replace("Z", "+00:00"))
        days_remaining = max(0, (expiry_dt - datetime.now(timezone.utc)).days)

    # Can create listing?
    can_create = listing_limit is None or listing_count < listing_limit

    return SubscriptionStatusResponse(
        current_tier=tier["name"],
        price_pula=tier["price_pula"],
        listing_limit=listing_limit,
        listing_count=listing_count,
        is_active=sub_info["is_active"],
        expires_at=sub_info["expires_at"],
        days_remaining=days_remaining,
        can_create_listing=can_create,
    )


@app.post("/subscriptions/initiate", response_model=PaymentInitResponse)
async def initiate_subscription(
    subscription: InitiateSubscription,
    user=Depends(get_current_user)
):
    """Initiate subscription payment via Orange Money or manual transfer"""
    # Get tier info
    tier_result = supabase.from_("subscription_tiers") \
        .select("*") \
        .eq("name", subscription.tier.value) \
        .single() \
        .execute()

    tier = tier_result.data

    if tier["price_pula"] == 0:
        raise HTTPException(status_code=400, detail="Free tier doesn't require payment")

    # Check for existing pending transaction for same tier (prevent duplicates)
    existing = supabase.from_("payment_transactions") \
        .select("*") \
        .eq("user_id", user.id) \
        .eq("tier_id", tier["id"]) \
        .eq("status", "pending") \
        .execute()

    if existing.data:
        # Return existing pending transaction instead of creating new
        txn = existing.data[0]
        return PaymentInitResponse(
            payment_url=txn.get("orange_money_pay_url"),
            transaction_id=txn["id"],
            status="pending",
            message=f"You already have a pending payment for {tier['name']} tier. Complete your existing payment or wait for it to expire."
        )

    # Create transaction record
    transaction_id = str(uuid.uuid4())
    txn_ref = f"PD-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{transaction_id[:8].upper()}"

    txn_data = {
        "id": transaction_id,
        "user_id": user.id,
        "tier_id": tier["id"],
        "amount_pula": tier["price_pula"],
        "payment_method": subscription.payment_method,
        "transaction_reference": txn_ref,
        "status": "pending"
    }

    payment_url = None
    message = ""

    if subscription.payment_method == "orange_money":
        # Initiate real Orange Money web payment
        try:
            om_response = orange_money.initiate_payment(
                order_id=txn_ref,
                amount=tier["price_pula"],
                currency="BWP",
            )
            payment_url = om_response.get("payment_url")
            pay_token = om_response.get("pay_token", "")
            txn_data["orange_money_order_id"] = txn_ref
            txn_data["orange_money_pay_token"] = pay_token
            message = "Redirecting to Orange Money for payment"
        except HTTPException:
            # If Orange Money is unavailable, fall back to manual
            message = (
                f"Orange Money is temporarily unavailable. "
                f"Please complete payment via Orange Money and keep your confirmation reference: {txn_ref}. "
                f"After payment, submit the reference in-app for activation."
            )
            txn_data["payment_method"] = "manual"
    elif subscription.payment_method == "myzaka":
        message = (
            f"Send P{tier['price_pula']} via MyZaka. "
            f"Use reference: {txn_ref}. "
            f"After payment, confirm in-app with your MyZaka receipt reference."
        )
    else:
        message = (
            f"Send P{tier['price_pula']} using your selected payment channel. "
            f"Use reference: {txn_ref}. "
            f"Submit proof of payment in-app for activation."
        )

    supabase.from_("payment_transactions").insert(txn_data).execute()

    return PaymentInitResponse(
        payment_url=payment_url,
        transaction_id=transaction_id,
        status="pending",
        message=message
    )


@app.post("/subscriptions/confirm", response_model=PaymentStatusResponse)
async def confirm_payment(
    confirmation: ConfirmPaymentRequest,
    user=Depends(get_current_user)
):
    """User confirms a manual/MyZaka payment by providing their receipt reference"""
    # Find the user's pending transaction
    result = supabase.from_("payment_transactions") \
        .select("*, subscription_tiers!tier_id(name)") \
        .eq("id", confirmation.transaction_id) \
        .eq("user_id", user.id) \
        .eq("status", "pending") \
        .single() \
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Pending transaction not found")

    txn = result.data

    # Store the user-provided reference and mark as awaiting_verification
    supabase.from_("payment_transactions").update({
        "user_payment_reference": confirmation.payment_reference,
        "status": "awaiting_verification",
    }).eq("id", txn["id"]).execute()

    tier_name = txn.get("subscription_tiers", {}).get("name", "unknown")

    return PaymentStatusResponse(
        transaction_id=txn["id"],
        status="awaiting_verification",
        tier_name=tier_name,
        amount_pula=txn["amount_pula"],
        message=(
            f"Payment reference received. Your {tier_name} tier upgrade will be activated "
            f"once we verify the payment. This usually takes a few minutes during business hours."
        ),
    )


@app.get("/subscriptions/transactions", response_model=List[TransactionResponse])
async def get_transactions(user=Depends(get_current_user)):
    """Get current user's payment transaction history"""
    result = supabase.from_("payment_transactions") \
        .select("*, subscription_tiers!tier_id(name)") \
        .eq("user_id", user.id) \
        .order("created_at", desc=True) \
        .limit(50) \
        .execute()

    return [
        TransactionResponse(
            id=txn["id"],
            amount_pula=txn["amount_pula"],
            payment_method=txn["payment_method"],
            transaction_reference=txn.get("transaction_reference"),
            status=txn["status"],
            tier_name=txn.get("subscription_tiers", {}).get("name"),
            created_at=txn["created_at"],
            completed_at=txn.get("completed_at"),
        )
        for txn in result.data
    ]


@app.get("/subscriptions/check-payment/{transaction_id}", response_model=PaymentStatusResponse)
async def check_payment_status(transaction_id: str, user=Depends(get_current_user)):
    """
    Check status of a specific payment. For Orange Money payments, also
    polls the Orange Money API for real-time status updates.
    """
    result = supabase.from_("payment_transactions") \
        .select("*, subscription_tiers!tier_id(name)") \
        .eq("id", transaction_id) \
        .eq("user_id", user.id) \
        .single() \
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Transaction not found")

    txn = result.data
    tier_name = txn.get("subscription_tiers", {}).get("name", "unknown")

    # If Orange Money and still pending, poll their API for status
    if txn["payment_method"] == "orange_money" and txn["status"] == "pending":
        om_order_id = txn.get("orange_money_order_id")
        if om_order_id:
            om_status = orange_money.check_transaction_status(om_order_id, txn["amount_pula"])
            remote_status = om_status.get("status", "").upper()

            if remote_status == "SUCCESS":
                # Auto-complete
                supabase.from_("payment_transactions").update({
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "orange_money_status": "SUCCESS",
                }).eq("id", txn["id"]).execute()

                await activate_subscription(user.id, txn["tier_id"])

                return PaymentStatusResponse(
                    transaction_id=txn["id"],
                    status="completed",
                    tier_name=tier_name,
                    amount_pula=txn["amount_pula"],
                    message=f"Payment confirmed! Your {tier_name} tier is now active.",
                )

            elif remote_status in ("FAILED", "EXPIRED", "CANCELLED"):
                supabase.from_("payment_transactions").update({
                    "status": "failed",
                    "orange_money_status": remote_status,
                }).eq("id", txn["id"]).execute()

                return PaymentStatusResponse(
                    transaction_id=txn["id"],
                    status="failed",
                    tier_name=tier_name,
                    amount_pula=txn["amount_pula"],
                    message=f"Payment {remote_status.lower()}. Please try again.",
                )

    # Default: return current DB status
    status_messages = {
        "pending": f"Payment pending. Complete your P{txn['amount_pula']} payment to activate {tier_name} tier.",
        "awaiting_verification": f"Payment submitted. Waiting for verification of your {tier_name} tier upgrade.",
        "completed": f"Payment complete! Your {tier_name} tier is active.",
        "failed": "Payment failed. Please try again or contact support.",
        "refunded": "This payment has been refunded.",
    }

    return PaymentStatusResponse(
        transaction_id=txn["id"],
        status=txn["status"],
        tier_name=tier_name,
        amount_pula=txn["amount_pula"],
        message=status_messages.get(txn["status"], "Unknown status"),
    )


# ========================================
# Webhooks
# ========================================
@app.post("/webhooks/orange-money")
async def orange_money_webhook(callback_data: OrangeMoneyCallback):
    """Handle Orange Money payment callback (server-to-server notification)"""
    logger.info(f"Orange Money webhook received: order_id={callback_data.order_id}, status={callback_data.status}")

    # Find transaction by order_id
    result = supabase.from_("payment_transactions") \
        .select("*") \
        .eq("orange_money_order_id", callback_data.order_id) \
        .single() \
        .execute()

    if not result.data:
        logger.warning(f"Webhook: transaction not found for order_id={callback_data.order_id}")
        raise HTTPException(status_code=404, detail="Transaction not found")

    transaction = result.data

    # Prevent double-processing
    if transaction["status"] in ("completed", "failed", "refunded"):
        logger.info(f"Webhook: transaction {transaction['id']} already {transaction['status']}, skipping")
        return {"status": "already_processed"}

    # Verify amount matches
    if callback_data.amount != transaction["amount_pula"]:
        logger.warning(
            f"Webhook: amount mismatch for {transaction['id']}: "
            f"expected {transaction['amount_pula']}, got {callback_data.amount}"
        )
        supabase.from_("payment_transactions").update({
            "status": "failed",
            "orange_money_status": "AMOUNT_MISMATCH",
        }).eq("id", transaction["id"]).execute()
        return {"status": "amount_mismatch"}

    # Process based on status
    if callback_data.status.upper() in ("SUCCESS", "SUCCESSFULL"):
        supabase.from_("payment_transactions").update({
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "orange_money_status": callback_data.status,
            "orange_money_transaction_id": callback_data.transaction_id,
        }).eq("id", transaction["id"]).execute()

        # Activate subscription
        await activate_subscription(transaction["user_id"], transaction["tier_id"])
        logger.info(f"Webhook: subscription activated for user {transaction['user_id']}")
    else:
        supabase.from_("payment_transactions").update({
            "status": "failed",
            "orange_money_status": callback_data.status,
        }).eq("id", transaction["id"]).execute()
        logger.info(f"Webhook: payment failed for transaction {transaction['id']}")

    return {"status": "processed"}


# ========================================
# Admin Endpoints (service-role auth)
# ========================================
async def verify_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify that the request comes from an admin (using service role key or admin user)"""
    try:
        token = credentials.credentials
        # Check if it's the service role key (for server-to-server)
        if token == settings.supabase_service_key:
            return {"role": "service"}

        # Otherwise verify as normal user and check admin flag
        user_response = supabase.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Unauthorized")

        # Check if user is admin in our users table
        admin_check = supabase.from_("users") \
            .select("is_admin") \
            .eq("id", user_response.user.id) \
            .single() \
            .execute()

        if not admin_check.data or not admin_check.data.get("is_admin", False):
            raise HTTPException(status_code=403, detail="Admin access required")

        return {"role": "admin", "user_id": user_response.user.id}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/admin/payments/approve", response_model=PaymentStatusResponse)
async def admin_approve_payment(
    approval: AdminApprovePayment,
    admin=Depends(verify_admin)
):
    """Admin approves a manual/MyZaka payment and activates the subscription"""
    result = supabase.from_("payment_transactions") \
        .select("*, subscription_tiers!tier_id(name)") \
        .eq("id", approval.transaction_id) \
        .in_("status", ["pending", "awaiting_verification"]) \
        .single() \
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Pending transaction not found")

    txn = result.data
    tier_name = txn.get("subscription_tiers", {}).get("name", "unknown")

    # Mark as completed
    update_data = {
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if approval.admin_notes:
        update_data["admin_notes"] = approval.admin_notes

    supabase.from_("payment_transactions").update(update_data).eq("id", txn["id"]).execute()

    # Activate subscription
    await activate_subscription(txn["user_id"], txn["tier_id"])

    logger.info(f"Admin approved payment {txn['id']} for user {txn['user_id']} -> {tier_name}")

    return PaymentStatusResponse(
        transaction_id=txn["id"],
        status="completed",
        tier_name=tier_name,
        amount_pula=txn["amount_pula"],
        message=f"Payment approved. User upgraded to {tier_name} tier.",
    )


@app.post("/admin/payments/reject", response_model=PaymentStatusResponse)
async def admin_reject_payment(
    approval: AdminApprovePayment,
    admin=Depends(verify_admin)
):
    """Admin rejects a payment"""
    result = supabase.from_("payment_transactions") \
        .select("*, subscription_tiers!tier_id(name)") \
        .eq("id", approval.transaction_id) \
        .in_("status", ["pending", "awaiting_verification"]) \
        .single() \
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Pending transaction not found")

    txn = result.data
    tier_name = txn.get("subscription_tiers", {}).get("name", "unknown")

    update_data = {"status": "failed"}
    if approval.admin_notes:
        update_data["admin_notes"] = approval.admin_notes

    supabase.from_("payment_transactions").update(update_data).eq("id", txn["id"]).execute()

    logger.info(f"Admin rejected payment {txn['id']}")

    return PaymentStatusResponse(
        transaction_id=txn["id"],
        status="failed",
        tier_name=tier_name,
        amount_pula=txn["amount_pula"],
        message=f"Payment rejected.{' Reason: ' + approval.admin_notes if approval.admin_notes else ''}",
    )


@app.get("/admin/payments/pending", response_model=List[TransactionResponse])
async def admin_get_pending_payments(admin=Depends(verify_admin)):
    """Admin view: all payments awaiting verification"""
    result = supabase.from_("payment_transactions") \
        .select("*, subscription_tiers!tier_id(name)") \
        .in_("status", ["pending", "awaiting_verification"]) \
        .order("created_at", desc=True) \
        .execute()

    return [
        TransactionResponse(
            id=txn["id"],
            amount_pula=txn["amount_pula"],
            payment_method=txn["payment_method"],
            transaction_reference=txn.get("transaction_reference"),
            status=txn["status"],
            tier_name=txn.get("subscription_tiers", {}).get("name"),
            created_at=txn["created_at"],
            completed_at=txn.get("completed_at"),
        )
        for txn in result.data
    ]


# ========================================
# Listings Endpoints
# ========================================
@app.get("/listings", response_model=List[ListingResponse])
async def get_listings(
    listing_type: Optional[ListingType] = None,
    brand: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    location: Optional[str] = None
):
    """Get all active listings with optional filters"""
    query = supabase.from_("car_listings").select("*").eq("status", "active")

    if listing_type:
        query = query.eq("listing_type", listing_type.value)
    if brand:
        query = query.eq("brand", brand)
    if min_price:
        query = query.gte("price", min_price)
    if max_price:
        query = query.lte("price", max_price)
    if location:
        query = query.eq("location", location)

    result = query.order("created_at", desc=True).execute()
    return result.data


@app.post("/listings", response_model=ListingResponse, status_code=status.HTTP_201_CREATED)
async def create_listing(listing: CreateListing, user=Depends(get_current_user)):
    """Create a new listing (respects tier limits with subscription enforcement)"""
    # Enforce subscription expiry first
    sub_info = await check_and_enforce_subscription(user.id)
    tier = sub_info["tier"]

    if sub_info.get("was_downgraded"):
        # User was just downgraded, inform them
        pass  # Still proceed with check below using new tier limits

    # Count active listings
    listings_count = supabase.from_("car_listings") \
        .select("*", count="exact") \
        .eq("user_id", user.id) \
        .eq("status", "active") \
        .execute()

    current_count = listings_count.count or 0
    listing_limit = tier["listing_limit"]

    if listing_limit is not None and current_count >= listing_limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "You've reached your listing limit. Upgrade your subscription to list more cars.",
                "current_tier": tier["name"],
                "listing_count": current_count,
                "listing_limit": listing_limit,
                "upgrade_required": True,
            }
        )

    # Create listing
    listing_data = listing.dict()
    listing_data["user_id"] = user.id
    listing_data["status"] = "active"  # Auto-approve for now

    result = supabase.from_("car_listings").insert(listing_data).execute()
    return result.data[0]


@app.get("/listings/my", response_model=List[ListingResponse])
async def get_my_listings(user=Depends(get_current_user)):
    """Get current user's listings"""
    result = supabase.from_("car_listings") \
        .select("*") \
        .eq("user_id", user.id) \
        .order("created_at", desc=True) \
        .execute()

    return result.data


@app.patch("/listings/{listing_id}", response_model=ListingResponse)
async def update_listing(
    listing_id: str,
    updates: UpdateListing,
    user=Depends(get_current_user)
):
    """Update a listing"""
    # Verify ownership
    existing = supabase.from_("car_listings") \
        .select("*") \
        .eq("id", listing_id) \
        .eq("user_id", user.id) \
        .single() \
        .execute()

    if not existing.data:
        raise HTTPException(status_code=404, detail="Listing not found")

    # Update
    update_data = {k: v for k, v in updates.dict().items() if v is not None}
    result = supabase.from_("car_listings") \
        .update(update_data) \
        .eq("id", listing_id) \
        .execute()

    return result.data[0]


@app.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listing(listing_id: str, user=Depends(get_current_user)):
    """Delete a listing"""
    # Mark as removed instead of actually deleting
    result = supabase.from_("car_listings") \
        .update({"status": "removed"}) \
        .eq("id", listing_id) \
        .eq("user_id", user.id) \
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Listing not found")

    return None


# ========================================
# AI Assistant Endpoints
# ========================================
PREMIUM_ASSISTANT_TIERS = {"premium"}


def _assistant_upgrade_gate(current_tier: str, required_tier: str = "premium") -> AssistantEntitlementGate:
    return AssistantEntitlementGate(
        requires_upgrade=True,
        current_tier=current_tier,
        required_tier=required_tier,
        message="This AI feature is available on Premium. Upgrade to unlock advanced assistant actions.",
        upgrade_cta="Upgrade to Premium"
    )


async def _get_user_tier(user_id: str) -> str:
    sub_info = await check_and_enforce_subscription(user_id)
    return sub_info["tier"]["name"]


def _save_assistant_message(thread_id: str, user_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    msg_id = str(uuid.uuid4())
    supabase.from_("assistant_messages").insert({
        "id": msg_id,
        "thread_id": thread_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        "metadata": metadata or {},
    }).execute()
    return msg_id


def _save_assistant_action(thread_id: str, user_id: str, action: AssistantAction, metadata: Optional[Dict[str, Any]] = None):
    supabase.from_("assistant_actions").insert({
        "id": str(uuid.uuid4()),
        "thread_id": thread_id,
        "user_id": user_id,
        "action_type": action.action_type,
        "title": action.title,
        "description": action.description,
        "target_route": action.target_route,
        "target_id": action.target_id,
        "metadata": metadata or {},
    }).execute()


def _get_or_create_assistant_thread(user_id: str, thread_id: Optional[str], title_seed: str) -> str:
    if thread_id:
        existing = supabase.from_("assistant_threads")             .select("id")             .eq("id", thread_id)             .eq("user_id", user_id)             .single()             .execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Assistant thread not found")
        return thread_id

    new_thread_id = str(uuid.uuid4())
    supabase.from_("assistant_threads").insert({
        "id": new_thread_id,
        "user_id": user_id,
        "title": title_seed[:120],
        "status": "active",
        "source": "in_app_assistant",
    }).execute()
    return new_thread_id


def _touch_assistant_thread(thread_id: str):
    supabase.from_("assistant_threads").update({
        "last_message_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", thread_id).execute()


def _build_assistant_query_response(message: str, listing_id: Optional[str]) -> Tuple[str, List[AssistantAction], List[AssistantToolOutput]]:
    """Rule-based assistant response engine for demo use before LLM/API integration."""
    text = message.lower().strip()
    actions: List[AssistantAction] = []
    tools: List[AssistantToolOutput] = []

    def has_any(*keywords: str) -> bool:
        return any(k in text for k in keywords)

    if has_any("hi", "hello", "hey", "good morning", "good afternoon"):
        response = (
            "Hi! I'm the PrimeDrive assistant. I can help with buying tips, selling tips, subscription plans, "
            "checkout guidance, disputes, and next steps."
        )
        actions.extend([
            AssistantAction(
                action_type="browse_listings",
                title="Browse Listings",
                description="See active cars for sale or rent.",
                target_route="buy",
            ),
            AssistantAction(
                action_type="view_plans",
                title="View Plans",
                description="Compare Free, Basic, Standard, and Premium tiers.",
                target_route="dashboard",
            ),
        ])
    elif has_any("price", "pricing", "plan", "tier", "subscription"):
        response = (
            "Current plans are: Free (P0, 1 listing), Basic (P25/month, 3 listings), "
            "Standard (P60/month, 10 listings), and Premium (P100/month, unlimited listings)."
        )
        actions.append(AssistantAction(
            action_type="upgrade",
            title="Manage Subscription",
            description="Open dashboard to review or change your plan.",
            target_route="dashboard",
        ))
    elif has_any("buy", "checkout", "pay", "purchase"):
        response = (
            "Before checkout, verify the seller profile, mileage, service history, and vehicle documents. "
            "When ready, continue to checkout for secure payment flow."
        )
        actions.extend([
            AssistantAction(
                action_type="buy_now",
                title="Go to Checkout",
                description="Proceed to secure checkout for this listing.",
                target_route="checkout",
                target_id=listing_id,
            ),
            AssistantAction(
                action_type="message_seller",
                title="Message Seller",
                description="Ask for documents, inspection history, and final condition details.",
                target_route="messages",
                target_id=listing_id,
            ),
        ])
    elif has_any("sell", "listing", "post car"):
        response = (
            "For faster sales, add at least 6 clear photos, mention service history, be transparent about condition, "
            "and set a realistic price for your market."
        )
        actions.append(AssistantAction(
            action_type="manage_listing",
            title="View My Listings",
            description="Open your listings to add or edit a car.",
            target_route="mylistings",
            target_id=listing_id,
        ))
    elif has_any("rent", "rental", "daily rate"):
        response = (
            "For rentals, include daily rate, seats, fuel policy, mileage limits, and pickup location. "
            "Clear rental terms usually improve booking confidence."
        )
        actions.append(AssistantAction(
            action_type="manage_listing",
            title="Edit Rental Listing",
            description="Update rental details and availability.",
            target_route="mylistings",
            target_id=listing_id,
        ))
    elif has_any("dispute", "refund", "scam", "problem", "issue"):
        response = (
            "I can help you open a dispute. Keep screenshots, payment proof, seller chat, and listing details ready "
            "before submitting your case."
        )
        actions.append(AssistantAction(
            action_type="open_dispute",
            title="Open Dispute",
            description="Start a dispute flow with your transaction details.",
            target_route="disputes",
            target_id=listing_id,
        ))
    elif has_any("contact", "support", "help"):
        response = "For support, use in-app messaging from the listing page so your context is attached automatically."
        actions.append(AssistantAction(
            action_type="message_support",
            title="Open Messages",
            description="Contact seller or support with listing context.",
            target_route="messages",
            target_id=listing_id,
        ))
    else:
        response = (
            "I can help with buying, selling, renting, checkout, disputes, and subscription plans. "
            "Try asking: 'How do I buy safely?', 'What plan should I choose?', or 'How can I sell faster?'."
        )
        actions.extend([
            AssistantAction(
                action_type="message_seller",
                title="Message Seller",
                description="Open messaging to ask questions before buying.",
                target_route="messages",
                target_id=listing_id,
            ),
            AssistantAction(
                action_type="upgrade",
                title="Upgrade Plan",
                description="Unlock premium AI workflows and higher listing limits.",
                target_route="dashboard",
            ),
        ])

    tools.append(AssistantToolOutput(
        tool_name="assistant_router",
        success=True,
        payload={"intent": "rule_based_demo", "listing_id": listing_id}
    ))
    return response, actions, tools


@app.post("/assistant/query", response_model=AssistantQueryResponse)
async def assistant_query(payload: AssistantQueryRequest, user=Depends(get_current_user)):
    thread_id = _get_or_create_assistant_thread(user.id, payload.thread_id, payload.message)
    current_tier = await _get_user_tier(user.id)
    entitlement = AssistantEntitlementGate(requires_upgrade=False, current_tier=current_tier)

    _save_assistant_message(thread_id, user.id, AssistantMessageRole.USER.value, payload.message, payload.context)
    response_text, actions, tools = _build_assistant_query_response(payload.message, payload.listing_id)

    assistant_msg_id = _save_assistant_message(
        thread_id,
        user.id,
        AssistantMessageRole.ASSISTANT.value,
        response_text,
        {"actions": [a.dict() for a in actions], "tools": [t.dict() for t in tools]}
    )

    for action in actions:
        _save_assistant_action(thread_id, user.id, action, {"trigger": "assistant_query"})

    _touch_assistant_thread(thread_id)

    return AssistantQueryResponse(
        thread_id=thread_id,
        message_id=assistant_msg_id,
        response=response_text,
        actions=actions,
        tools=tools,
        entitlement=entitlement,
    )


@app.post("/assistant/suggest-next-step", response_model=AssistantSuggestNextStepResponse)
async def assistant_suggest_next_step(payload: AssistantSuggestNextStepRequest, user=Depends(get_current_user)):
    thread_id = _get_or_create_assistant_thread(user.id, payload.thread_id, payload.goal)
    current_tier = await _get_user_tier(user.id)

    _save_assistant_message(thread_id, user.id, AssistantMessageRole.USER.value, payload.goal, payload.context)

    if current_tier not in PREMIUM_ASSISTANT_TIERS:
        gate = _assistant_upgrade_gate(current_tier)
        message = "Upgrade to Premium to receive personalized next-step recommendations based on your account activity."
        msg_id = _save_assistant_message(thread_id, user.id, AssistantMessageRole.ASSISTANT.value, message, gate.dict())
        _touch_assistant_thread(thread_id)
        return AssistantSuggestNextStepResponse(
            thread_id=thread_id,
            message_id=msg_id,
            suggested_action=AssistantAction(
                action_type="upgrade",
                title="Upgrade to Premium",
                description="Unlock intelligent next-step suggestions.",
                target_route="dashboard",
            ),
            reason=message,
            tools=[AssistantToolOutput(tool_name="entitlement_check", payload={"passed": False})],
            entitlement=gate,
        )

    goal = payload.goal.lower()
    if "buy" in goal or "offer" in goal:
        action = AssistantAction(
            action_type="message_seller",
            title="Message Seller",
            description="Confirm history, paperwork, and inspection before paying.",
            target_route="messages",
            target_id=payload.listing_id,
        )
        reason = "Messaging the seller first usually reduces disputes and improves purchase confidence."
    elif "sell" in goal or "faster" in goal:
        action = AssistantAction(
            action_type="boost_listing",
            title="Upgrade Listing Plan",
            description="Move higher in search and reach more buyers.",
            target_route="dashboard",
            target_id=payload.listing_id,
        )
        reason = "Upgrading your plan gives visibility boosts and premium buyer trust signals."
    else:
        action = AssistantAction(
            action_type="buy_now",
            title="Buy Now",
            description="Proceed to checkout when you are satisfied with listing details.",
            target_route="checkout",
            target_id=payload.listing_id,
        )
        reason = "Checkout is the fastest path once due diligence is complete."

    msg_id = _save_assistant_message(thread_id, user.id, AssistantMessageRole.ASSISTANT.value, reason, {"action": action.dict()})
    _save_assistant_action(thread_id, user.id, action, {"trigger": "assistant_suggest_next_step"})
    _touch_assistant_thread(thread_id)

    return AssistantSuggestNextStepResponse(
        thread_id=thread_id,
        message_id=msg_id,
        suggested_action=action,
        reason=reason,
        tools=[AssistantToolOutput(tool_name="next_step_planner", payload={"goal": payload.goal})],
        entitlement=AssistantEntitlementGate(requires_upgrade=False, current_tier=current_tier),
    )


@app.post("/assistant/listing-review", response_model=AssistantListingReviewResponse)
async def assistant_listing_review(payload: AssistantListingReviewRequest, user=Depends(get_current_user)):
    thread_id = _get_or_create_assistant_thread(user.id, payload.thread_id, f"Listing review: {payload.brand} {payload.model}")
    current_tier = await _get_user_tier(user.id)

    review_prompt = f"Review listing {payload.brand} {payload.model} {payload.year} at P{payload.price}."
    _save_assistant_message(thread_id, user.id, AssistantMessageRole.USER.value, review_prompt, payload.dict())

    if current_tier not in PREMIUM_ASSISTANT_TIERS:
        gate = _assistant_upgrade_gate(current_tier)
        summary = "AI listing reviews are Premium-only. Upgrade to receive pricing and conversion optimization guidance."
        msg_id = _save_assistant_message(thread_id, user.id, AssistantMessageRole.ASSISTANT.value, summary, gate.dict())
        _touch_assistant_thread(thread_id)
        return AssistantListingReviewResponse(
            thread_id=thread_id,
            message_id=msg_id,
            score=0,
            summary=summary,
            suggestions=["Upgrade to Premium to unlock listing quality analysis."],
            tools=[AssistantToolOutput(tool_name="entitlement_check", payload={"passed": False})],
            entitlement=gate,
        )

    score = 70
    suggestions = []
    if payload.notes and len(payload.notes) >= 80:
        score += 10
    else:
        suggestions.append("Add a richer description (service history, ownership, and known issues).")

    if payload.mileage < 120000:
        score += 10
    else:
        suggestions.append("If mileage is high, justify price with maintenance records and recent repairs.")

    if payload.price <= 0:
        score = max(0, score - 30)
        suggestions.append("Set a realistic asking price for better visibility.")

    score = max(0, min(score, 100))
    if not suggestions:
        suggestions = ["Great listing. Consider upgrading your tier to boost exposure and trust signals."]

    summary = f"Your listing quality score is {score}/100. Improve detail clarity and pricing confidence to increase buyer conversion."
    msg_id = _save_assistant_message(
        thread_id,
        user.id,
        AssistantMessageRole.ASSISTANT.value,
        summary,
        {"score": score, "suggestions": suggestions}
    )
    _save_assistant_action(
        thread_id,
        user.id,
        AssistantAction(
            action_type="edit_listing",
            title="Edit Listing",
            description="Apply the assistant suggestions to improve conversion.",
            target_route="mylistings",
            target_id=payload.listing_id,
        ),
        {"trigger": "assistant_listing_review", "score": score}
    )
    _touch_assistant_thread(thread_id)

    return AssistantListingReviewResponse(
        thread_id=thread_id,
        message_id=msg_id,
        score=score,
        summary=summary,
        suggestions=suggestions,
        tools=[AssistantToolOutput(tool_name="listing_quality", payload={"score": score})],
        entitlement=AssistantEntitlementGate(requires_upgrade=False, current_tier=current_tier),
    )


# ========================================
# Scheduled Tasks / Cron Endpoints
# ========================================
@app.post("/cron/expire-payments")
async def cron_expire_stale_payments(admin=Depends(verify_admin)):
    """Expire pending payments older than 24h. Call via cron job or manually."""
    result = supabase.rpc("expire_stale_payments").execute()
    count = result.data or 0
    logger.info(f"Cron: expired {count} stale payments")
    return {"expired_count": count}


@app.post("/cron/downgrade-subscriptions")
async def cron_downgrade_expired(admin=Depends(verify_admin)):
    """Downgrade users with expired subscriptions to free. Call via cron job or manually."""
    result = supabase.rpc("downgrade_expired_subscriptions").execute()
    count = result.data or 0
    logger.info(f"Cron: downgraded {count} expired subscriptions")
    return {"downgraded_count": count}


# ========================================
# Health Check
# ========================================
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
