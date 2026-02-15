-- =============================================
-- PrimeDrive Botswana — Full Marketplace Schema v2
-- =============================================
-- Run this ENTIRE file in Supabase SQL Editor
-- If upgrading from v1, this is safe to re-run
-- =============================================

-- 1. PROFILES
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    full_name TEXT,
    phone TEXT,
    whatsapp TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    current_tier TEXT NOT NULL DEFAULT 'free',
    listing_count INTEGER NOT NULL DEFAULT 0,
    listing_limit INTEGER DEFAULT 1,
    is_admin BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
DO $$ BEGIN
    ALTER TABLE profiles ADD COLUMN IF NOT EXISTS full_name TEXT;
    ALTER TABLE profiles ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';
EXCEPTION WHEN others THEN NULL;
END $$;

-- 2. LISTINGS
CREATE TABLE IF NOT EXISTS listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    seller_type TEXT NOT NULL DEFAULT 'individual',
    title TEXT NOT NULL,
    make TEXT NOT NULL,
    model TEXT NOT NULL,
    year INTEGER NOT NULL,
    mileage INTEGER,
    transmission TEXT,
    condition TEXT,
    fuel_type TEXT,
    price NUMERIC NOT NULL,
    location TEXT NOT NULL DEFAULT 'Gaborone',
    description TEXT,
    status TEXT NOT NULL DEFAULT 'unverified',
    views INTEGER NOT NULL DEFAULT 0,
    whatsapp_clicks INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. LISTING PHOTOS
CREATE TABLE IF NOT EXISTS listing_photos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    photo_url TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4. LEADS
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_code TEXT UNIQUE NOT NULL,
    listing_id UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    buyer_id UUID REFERENCES profiles(id),
    seller_id UUID NOT NULL REFERENCES profiles(id),
    lead_type TEXT NOT NULL DEFAULT 'whatsapp_seller',
    status TEXT NOT NULL DEFAULT 'open',
    deposit_amount NUMERIC,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 5. TRANSACTIONS
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

-- 6. INDEXES
CREATE INDEX IF NOT EXISTS idx_listings_user_id ON listings(user_id);
CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status);
CREATE INDEX IF NOT EXISTS idx_listings_make ON listings(make);
CREATE INDEX IF NOT EXISTS idx_listing_photos_listing ON listing_photos(listing_id);
CREATE INDEX IF NOT EXISTS idx_leads_listing ON leads(listing_id);
CREATE INDEX IF NOT EXISTS idx_leads_seller ON leads(seller_id);
CREATE INDEX IF NOT EXISTS idx_leads_code ON leads(lead_code);
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_profiles_email ON profiles(email);

-- 7. AUTO-CREATE PROFILE ON SIGNUP
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP FUNCTION IF EXISTS public.handle_new_user();
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name, phone, whatsapp, role)
    VALUES (
        NEW.id, NEW.email,
        COALESCE(NEW.raw_user_meta_data ->> 'full_name', ''),
        NEW.raw_user_meta_data ->> 'phone',
        NEW.raw_user_meta_data ->> 'whatsapp',
        COALESCE(NEW.raw_user_meta_data ->> 'role', 'user')
    );
    RETURN NEW;
END;
$$;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 8. AUTO updated_at
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

DROP TRIGGER IF EXISTS profiles_updated_at ON profiles;
CREATE TRIGGER profiles_updated_at BEFORE UPDATE ON profiles FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
DROP TRIGGER IF EXISTS listings_updated_at ON listings;
CREATE TRIGGER listings_updated_at BEFORE UPDATE ON listings FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
DROP TRIGGER IF EXISTS leads_updated_at ON leads;
CREATE TRIGGER leads_updated_at BEFORE UPDATE ON leads FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- 9. ROW LEVEL SECURITY
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE listing_photos ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

-- Profiles
DROP POLICY IF EXISTS "Users read own profile" ON profiles;
CREATE POLICY "Users read own profile" ON profiles FOR SELECT USING (auth.uid() = id);
DROP POLICY IF EXISTS "Users update own profile" ON profiles;
CREATE POLICY "Users update own profile" ON profiles FOR UPDATE USING (auth.uid() = id);
DROP POLICY IF EXISTS "Admins read all profiles" ON profiles;
CREATE POLICY "Admins read all profiles" ON profiles FOR SELECT USING (
    EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND is_admin = true)
);
-- Allow anyone to read seller contact info (for WhatsApp Seller button)
DROP POLICY IF EXISTS "Anyone can read seller contact" ON profiles;
CREATE POLICY "Anyone can read seller contact" ON profiles FOR SELECT
    USING (
        id IN (SELECT user_id FROM listings WHERE status IN ('unverified', 'verified'))
    );

-- Listings (public read for active, owner write)
DROP POLICY IF EXISTS "Anyone can read active listings" ON listings;
CREATE POLICY "Anyone can read active listings" ON listings FOR SELECT USING (status IN ('unverified','verified'));
DROP POLICY IF EXISTS "Users read own listings" ON listings;
CREATE POLICY "Users read own listings" ON listings FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "Users create own listings" ON listings;
CREATE POLICY "Users create own listings" ON listings FOR INSERT WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS "Users update own listings" ON listings;
CREATE POLICY "Users update own listings" ON listings FOR UPDATE USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "Users delete own listings" ON listings;
CREATE POLICY "Users delete own listings" ON listings FOR DELETE USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "Admins manage all listings" ON listings;
CREATE POLICY "Admins manage all listings" ON listings FOR ALL USING (
    EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND is_admin = true)
);

-- Listing photos (public read)
DROP POLICY IF EXISTS "Anyone can read listing photos" ON listing_photos;
CREATE POLICY "Anyone can read listing photos" ON listing_photos FOR SELECT USING (true);
DROP POLICY IF EXISTS "Owners insert listing photos" ON listing_photos;
CREATE POLICY "Owners insert listing photos" ON listing_photos FOR INSERT WITH CHECK (
    EXISTS (SELECT 1 FROM listings WHERE id = listing_id AND user_id = auth.uid())
);
DROP POLICY IF EXISTS "Owners delete listing photos" ON listing_photos;
CREATE POLICY "Owners delete listing photos" ON listing_photos FOR DELETE USING (
    EXISTS (SELECT 1 FROM listings WHERE id = listing_id AND user_id = auth.uid())
);

-- Leads
DROP POLICY IF EXISTS "Sellers read their leads" ON leads;
CREATE POLICY "Sellers read their leads" ON leads FOR SELECT USING (auth.uid() = seller_id);
DROP POLICY IF EXISTS "Buyers read their leads" ON leads;
CREATE POLICY "Buyers read their leads" ON leads FOR SELECT USING (auth.uid() = buyer_id);
DROP POLICY IF EXISTS "Anyone can create leads" ON leads;
CREATE POLICY "Anyone can create leads" ON leads FOR INSERT WITH CHECK (true);
DROP POLICY IF EXISTS "Admins manage all leads" ON leads;
CREATE POLICY "Admins manage all leads" ON leads FOR ALL USING (
    EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND is_admin = true)
);

-- Transactions
DROP POLICY IF EXISTS "Users read own transactions" ON transactions;
CREATE POLICY "Users read own transactions" ON transactions FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "Users create own transactions" ON transactions;
CREATE POLICY "Users create own transactions" ON transactions FOR INSERT WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS "Admins read all transactions" ON transactions;
CREATE POLICY "Admins read all transactions" ON transactions FOR SELECT USING (
    EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND is_admin = true)
);
DROP POLICY IF EXISTS "Admins update transactions" ON transactions;
CREATE POLICY "Admins update transactions" ON transactions FOR UPDATE USING (
    EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND is_admin = true)
);

-- 10. STORAGE BUCKET
INSERT INTO storage.buckets (id, name, public)
VALUES ('listing-photos', 'listing-photos', true)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS "Public read listing photos" ON storage.objects;
CREATE POLICY "Public read listing photos" ON storage.objects FOR SELECT USING (bucket_id = 'listing-photos');
DROP POLICY IF EXISTS "Auth users upload listing photos" ON storage.objects;
CREATE POLICY "Auth users upload listing photos" ON storage.objects FOR INSERT WITH CHECK (bucket_id = 'listing-photos' AND auth.role() = 'authenticated');
DROP POLICY IF EXISTS "Users delete own listing photos" ON storage.objects;
CREATE POLICY "Users delete own listing photos" ON storage.objects FOR DELETE USING (bucket_id = 'listing-photos' AND auth.uid()::text = (storage.foldername(name))[1]);

-- 11. INCREMENT LISTING VIEW (RPC function callable from frontend)
CREATE OR REPLACE FUNCTION public.increment_listing_views(listing_uuid UUID)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    UPDATE listings SET views = views + 1 WHERE id = listing_uuid;
END;
$$;

CREATE OR REPLACE FUNCTION public.increment_whatsapp_clicks(listing_uuid UUID)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    UPDATE listings SET whatsapp_clicks = whatsapp_clicks + 1 WHERE id = listing_uuid;
END;
$$;

-- =============================================
-- MAKE YOURSELF ADMIN (run after first signup):
-- UPDATE profiles SET is_admin = true, role = 'admin', current_tier = 'premium', listing_limit = NULL WHERE email = 'YOUR_EMAIL@example.com';
-- =============================================
