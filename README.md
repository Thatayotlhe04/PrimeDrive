# PrimeDrive Botswana

**Botswana's trusted car marketplace — Buy, Rent & Sell quality vehicles.**

PrimeDrive is a full-stack web application for buying, renting, and selling pre-owned cars in Botswana. Built with a modern single-page frontend and a FastAPI + Supabase backend with Orange Money payment integration.

![Status](https://img.shields.io/badge/status-in%20development-yellow)
![License](https://img.shields.io/badge/license-MIT-blue)

---

##Features

- **Car Listings** — Browse, search, and filter vehicles by make, model, price, and location
- **User Authentication** — Secure sign-up and login via Supabase Auth
- **Subscription Tiers** — Free, Basic (P25/mo), Standard (P60/mo), Premium (P100/mo)
- **Orange Money & MyZaka Payments** — Integrated mobile money payments for subscriptions
- **Admin Dashboard** — Manage users, approve payments, and moderate listings
- **Responsive Design** — Fully mobile-friendly UI
- **Dark/Light Mode** — Theme toggle support
- **SEO Optimized** — Meta tags, Open Graph, and semantic HTML

##Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | HTML, CSS (custom design system), Vanilla JavaScript |
| **Backend** | Python, FastAPI, Uvicorn |
| **Database** | Supabase (PostgreSQL) |
| **Auth** | Supabase Auth |
| **Payments** | Orange Money Web Pay API |
| **Hosting** | Deployable to Render, Railway, Fly.io, or Vercel |

##Project Structure

```
PrimeDrive/
├── index.html              # Frontend SPA (single-page app)
├── README.md               # This file
├── .gitignore              # Git ignore rules
└── backend/
    ├── main.py             # FastAPI application & routes
    ├── config.py           # App settings (env-based)
    ├── models.py           # Pydantic models / schemas
    ├── database.sql        # Supabase database schema
    ├── requirements.txt    # Python dependencies
    ├── .env.example        # Environment variable template
    ├── .gitignore          # Backend-specific ignores
    └── README.md           # Backend-specific docs
```

##Getting Started

### Prerequisites

- **Python 3.9+**
- **Supabase account** — [supabase.com](https://supabase.com)
- **Git**

### 1. Clone the Repository

```bash
git clone https://github.com/Thatayotlhe04/PrimeDrive.git
cd PrimeDrive
```

### 2. Set Up the Backend

```bash
cd backend
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_role_key
SECRET_KEY=your_random_secret
ORANGE_MONEY_API_KEY=your_key
ORANGE_MONEY_MERCHANT_ID=your_merchant_id
FRONTEND_URL=http://localhost:3000
```

### 4. Set Up the Database

1. Create a new project on [Supabase](https://supabase.com)
2. Open the **SQL Editor**
3. Paste and run the contents of `backend/database.sql`

### 5. Run the Backend

```bash
python main.py
```

- API: `http://localhost:8000`
- Swagger Docs: `http://localhost:8000/docs`

### 6. Open the Frontend

Open `index.html` in your browser, or serve it with any static file server:

```bash
# Using Python
python -m http.server 3000

# Or use VS Code Live Server extension
```

## API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/auth/signup` | Register a new user |
| `POST` | `/auth/login` | Login |
| `GET` | `/auth/me` | Get current user profile |
| `GET` | `/tiers` | List subscription tiers |
| `GET` | `/subscriptions/status` | Check subscription status |
| `POST` | `/subscriptions/initiate` | Start a payment |
| `POST` | `/subscriptions/confirm` | Confirm manual payment |
| `GET` | `/listings` | Browse all listings |
| `POST` | `/listings` | Create a listing |
| `GET` | `/listings/my` | Get your listings |
| `PATCH` | `/listings/{id}` | Update a listing |
| `DELETE` | `/listings/{id}` | Delete a listing |

> See full API documentation at `/docs` when the server is running.

##Subscription Tiers

| Tier | Price | Listings |
|------|-------|----------|
| Free | P0 | 1 |
| Basic | P25/month | 3 |
| Standard | P60/month | 10 |
| Premium | P100/month | Unlimited |

##Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "Add your feature"`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Contact

- **WhatsApp**: +267 77 625 997
- **Location**: Gaborone, Botswana

---

*Built with love for the Botswana car market.*
