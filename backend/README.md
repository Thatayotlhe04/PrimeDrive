# PrimeDrive Backend

Python + FastAPI + Supabase backend for PrimeDrive car marketplace with subscription tiers.

## Features

- **User Authentication** with Supabase Auth
- **Subscription Tiers**: Free (1 listing), Basic (3 listings, P25/mo), Standard (10 listings, P60/mo), Premium (unlimited, P100/mo)
- **Orange Money / MyZaka** payment integration
- **Car Listings** with tier-based limits
- **RESTful API** with FastAPI

## Setup Instructions

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Set Up Supabase

1. Go to [supabase.com](https://supabase.com) and create a new project
2. In the SQL Editor, run the SQL from `database.sql`
3. Go to Settings > API to get your:
   - Project URL
   - anon/public key
   - service_role key

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and add your credentials:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_anon_key_here
SUPABASE_SERVICE_KEY=your_service_role_key_here

ORANGE_MONEY_API_KEY=your_key
ORANGE_MONEY_MERCHANT_ID=your_merchant_id

SECRET_KEY=your_random_secret_key_for_jwt
```

### 4. Run the Server

```bash
python main.py
```

API will be available at: `http://localhost:8000`
API Docs (Swagger): `http://localhost:8000/docs`

## API Endpoints

### Authentication
- `POST /auth/signup` - Register new user
- `POST /auth/login` - Login user
- `GET /auth/me` - Get current user profile

### Subscriptions & Payments
- `GET /tiers` - Get all subscription tiers
- `GET /subscriptions/status` - Get current subscription status (with auto-expiry enforcement)
- `POST /subscriptions/initiate` - Start subscription payment (Orange Money, MyZaka, or manual)
- `POST /subscriptions/confirm` - User confirms manual payment with receipt reference
- `GET /subscriptions/transactions` - Get payment transaction history
- `GET /subscriptions/check-payment/{id}` - Check payment status (polls Orange Money in real-time)

### Listings
- `GET /listings` - Get all active listings (with filters)
- `POST /listings` - Create new listing (requires auth, enforces tier limits)
- `GET /listings/my` - Get my listings (requires auth)
- `PATCH /listings/{id}` - Update listing (requires auth)
- `DELETE /listings/{id}` - Delete listing (requires auth)

### Admin
- `GET /admin/payments/pending` - View all pending/awaiting payments
- `POST /admin/payments/approve` - Approve a manual payment & activate subscription
- `POST /admin/payments/reject` - Reject a payment

### Cron / Maintenance
- `POST /cron/expire-payments` - Expire stale pending payments (>24h old)
- `POST /cron/downgrade-subscriptions` - Auto-downgrade expired subscriptions to free

### Webhooks
- `POST /webhooks/orange-money` - Orange Money payment callback (server-to-server)

## Subscription Tiers

| Tier | Price | Listing Limit |
|------|-------|--------------|
| Free | P0 | 1 listing |
| Basic | P25/month | 3 listings |
| Standard | P60/month | 10 listings |
| Premium | P100/month | Unlimited |

All listings last 90 days before expiring.

## Orange Money Integration

The Orange Money webhook endpoint is at `/webhooks/orange-money`.

**Payment Flow:**
1. User selects a tier and payment method on the frontend
2. Frontend calls `POST /subscriptions/initiate` with tier + method
3. **Orange Money**: User is redirected to the Orange Money payment URL. On success, Orange sends a callback to `/webhooks/orange-money` which auto-activates the subscription.
4. **MyZaka / Manual**: User sends payment externally, then calls `POST /subscriptions/confirm` with their receipt reference. Admin approves via `POST /admin/payments/approve`.
5. Frontend can poll `GET /subscriptions/check-payment/{id}` for real-time status.

**Setup:**
- Register the webhook URL with Orange Money and get API credentials
- Set `ORANGE_MONEY_API_KEY` and `ORANGE_MONEY_MERCHANT_ID` in `.env`
- For testing, you can use the admin approve endpoint to simulate payment completion

## Development

```bash
# Run with auto-reload
uvicorn main:app --reload

# Run tests (when added)
pytest
```

## Next Steps

1. Set up Supabase project and run database.sql
2. Get Orange Money API credentials
3. Update frontend to use this API
4. Deploy to production (Railway, Fly.io, or Render)

## Security Notes

- Never commit `.env` file
- Use service_role key only in secure backend
- In production, update CORS origins to your actual domain
- Enable RLS policies in Supabase for extra security
