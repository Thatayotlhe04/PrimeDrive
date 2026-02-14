-- =============================================
-- PrimeDrive Botswana — Supabase Database Setup
-- =============================================
-- Run this in your Supabase SQL Editor (supabase.com > your project > SQL Editor)
--
-- IMPORTANT: Replace 'YOUR_EMAIL@example.com' at the bottom with your actual email
-- =============================================


-- 1. PROFILES TABLE
-- Stores user info linked to Supabase Auth
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    phone TEXT,
    whatsapp TEXT,
    current_tier TEXT NOT NULL DEFAULT 'free',
    listing_count INTEGER NOT NULL DEFAULT 0,
    listing_limit INTEGER DEFAULT 1,
    is_admin BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. TRANSACTIONS TABLE
-- Stores subscription payment records
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    tier_name TEXT NOT NULL,
    amount_pula INTEGER NOT NULL DEFAULT 0,
    payment_method TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'pending',
    transaction_reference TEXT,
    admin_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- 3. INDEXES
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_profiles_email ON profiles(email);


-- 4. AUTO-CREATE PROFILE ON SIGNUP
-- This trigger automatically creates a profile row when a new user signs up
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.profiles (id, email, phone, whatsapp)
    VALUES (
        NEW.id,
        NEW.email,
        NEW.raw_user_meta_data ->> 'phone',
        NEW.raw_user_meta_data ->> 'whatsapp'
    );
    RETURN NEW;
END;
$$;

-- Drop trigger if exists, then create
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


-- 5. AUTO-UPDATE updated_at
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS profiles_updated_at ON profiles;
CREATE TRIGGER profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


-- 6. ROW LEVEL SECURITY (RLS)
-- Users can only see/edit their own data; admins can see everything

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

-- Profiles: users can read/update their own profile
DROP POLICY IF EXISTS "Users read own profile" ON profiles;
CREATE POLICY "Users read own profile" ON profiles
    FOR SELECT USING (auth.uid() = id);

DROP POLICY IF EXISTS "Users update own profile" ON profiles;
CREATE POLICY "Users update own profile" ON profiles
    FOR UPDATE USING (auth.uid() = id);

-- Profiles: admins can read all profiles
DROP POLICY IF EXISTS "Admins read all profiles" ON profiles;
CREATE POLICY "Admins read all profiles" ON profiles
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND is_admin = true)
    );

-- Transactions: users can read their own transactions
DROP POLICY IF EXISTS "Users read own transactions" ON transactions;
CREATE POLICY "Users read own transactions" ON transactions
    FOR SELECT USING (auth.uid() = user_id);

-- Transactions: users can create their own transactions
DROP POLICY IF EXISTS "Users create own transactions" ON transactions;
CREATE POLICY "Users create own transactions" ON transactions
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Transactions: admins can read all transactions
DROP POLICY IF EXISTS "Admins read all transactions" ON transactions;
CREATE POLICY "Admins read all transactions" ON transactions
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND is_admin = true)
    );

-- Transactions: admins can update any transaction
DROP POLICY IF EXISTS "Admins update transactions" ON transactions;
CREATE POLICY "Admins update transactions" ON transactions
    FOR UPDATE USING (
        EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND is_admin = true)
    );


-- =============================================
-- 7. SET YOUR ADMIN EMAIL
-- =============================================
-- After you sign up on the site with your email, run this to make yourself admin:
--
--   UPDATE profiles SET is_admin = true WHERE email = 'YOUR_EMAIL@example.com';
--
-- Or if you want to pre-set it (run after your first signup):
-- UPDATE profiles SET is_admin = true, current_tier = 'premium', listing_limit = NULL WHERE email = 'YOUR_EMAIL@example.com';
