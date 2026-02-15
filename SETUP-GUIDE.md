# PrimeDrive — Supabase Backend Setup

## Step 1: Create a Supabase project (free)

1. Go to **https://supabase.com** and sign up (GitHub login works)
2. Click **"New Project"**
3. Give it a name like `primedrive`
4. Set a database password (save it somewhere)
5. Choose a region close to you (any works fine)
6. Wait ~2 minutes for it to set up

## Step 2: Get your API keys

1. In your Supabase project, go to **Settings > API**
2. Copy two things:
   - **Project URL** — looks like `https://abcdefgh.supabase.co`
   - **anon public key** — a long string starting with `eyJ...`
3. Open `index.html` and find these lines near the top of the `<script>`:

```js
const SUPABASE_URL = 'https://YOUR_PROJECT_ID.supabase.co';
const SUPABASE_ANON_KEY = 'YOUR_ANON_KEY_HERE';
```

4. Replace them with your actual values

## Step 3: Create the database tables

1. In Supabase, go to **SQL Editor** (left sidebar)
2. Click **"New Query"**
3. Paste the entire contents of `supabase-setup.sql`
4. Click **"Run"** — you should see "Success" messages

## Step 4: Disable email confirmation (recommended for testing)

By default Supabase requires email confirmation before users can sign in.
To turn this off for now:

1. Go to **Authentication > Providers > Email**
2. Turn OFF "Confirm email"
3. Click **Save**

You can turn this back on later when you're ready for production.

## Step 5: Sign up and make yourself admin

1. Open your site and click **Login > Create Account**
2. Sign up with your email
3. Go back to Supabase **SQL Editor** and run:

```sql
UPDATE profiles SET is_admin = true, current_tier = 'premium', listing_limit = NULL WHERE email = 'your-email@example.com';
```

4. Log out and log back in — you should now see the Admin Panel

## Step 6: Add your site URL to Supabase

1. Go to **Authentication > URL Configuration**
2. Set **Site URL** to your Netlify URL (e.g. `https://primedrive.netlify.app`)
3. Add your custom domain too if you have one

## That's it!

Your auth system is now live. Users can sign up, log in, and their
sessions persist across page reloads. You can manage everything
from the admin dashboard.

### How payments work

1. User picks a plan and clicks Upgrade
2. A WhatsApp message is generated with a payment reference
3. User pays via Orange Money / MyZaka and messages you
4. You log into the admin dashboard and click Approve
5. Their subscription activates immediately

### Costs

Supabase free tier includes:
- 50,000 monthly active users
- 500 MB database
- Unlimited API requests
- Built-in auth

More than enough for PrimeDrive to grow well beyond launch.
