-- PrimeDrive Database Schema for Supabase
-- Run this SQL in your Supabase SQL Editor

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Subscription Tiers Table
CREATE TABLE subscription_tiers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(50) NOT NULL UNIQUE,
    price_pula INTEGER NOT NULL,
    listing_limit INTEGER, -- NULL means unlimited
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Insert default tiers
INSERT INTO subscription_tiers (name, price_pula, listing_limit) VALUES
('free', 0, 1),
('basic', 25, 3),
('standard', 60, 10),
('premium', 100, NULL); -- NULL = unlimited

-- Users Table (extends Supabase auth.users)
CREATE TABLE users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    phone VARCHAR(20),
    whatsapp VARCHAR(20),
    is_admin BOOLEAN DEFAULT FALSE,
    current_tier_id UUID REFERENCES subscription_tiers(id) DEFAULT (SELECT id FROM subscription_tiers WHERE name = 'free'),
    subscription_expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Car Listings Table
CREATE TABLE car_listings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,

    -- Car Details
    brand VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    year INTEGER NOT NULL,
    mileage INTEGER NOT NULL,
    transmission VARCHAR(20) NOT NULL,
    condition VARCHAR(50) NOT NULL,
    price INTEGER NOT NULL,
    location VARCHAR(100) NOT NULL,
    notes TEXT,

    -- Listing Type
    listing_type VARCHAR(20) NOT NULL CHECK (listing_type IN ('sale', 'rent')),
    daily_rate INTEGER, -- For rentals
    seats INTEGER, -- For rentals

    -- Media
    images TEXT[], -- Array of image URLs

    -- Status
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'expired', 'removed')),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '90 days')
);

-- Payment Transactions Table
CREATE TABLE payment_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    tier_id UUID REFERENCES subscription_tiers(id),

    -- Payment Details
    amount_pula INTEGER NOT NULL,
    payment_method VARCHAR(50) NOT NULL, -- 'orange_money', 'myzaka', 'manual'
    transaction_reference VARCHAR(255) UNIQUE,
    user_payment_reference VARCHAR(255), -- Reference provided by user from their receipt

    -- Orange Money specific fields
    orange_money_order_id VARCHAR(255),
    orange_money_pay_token VARCHAR(255),
    orange_money_transaction_id VARCHAR(255),
    orange_money_status VARCHAR(50),

    -- Admin fields
    admin_notes TEXT,

    -- Status: pending -> awaiting_verification -> completed/failed/refunded
    status VARCHAR(30) DEFAULT 'pending' CHECK (status IN ('pending', 'awaiting_verification', 'completed', 'failed', 'refunded')),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Assistant Threads Table
CREATE TABLE assistant_threads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(160) NOT NULL,
    status VARCHAR(30) DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    source VARCHAR(50) DEFAULT 'in_app_assistant',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_message_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Assistant Messages Table
CREATE TABLE assistant_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id UUID NOT NULL REFERENCES assistant_threads(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Assistant Actions Table
CREATE TABLE assistant_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id UUID NOT NULL REFERENCES assistant_threads(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action_type VARCHAR(60) NOT NULL,
    title VARCHAR(120) NOT NULL,
    description TEXT,
    target_route VARCHAR(80),
    target_id UUID,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for better query performance
CREATE INDEX idx_users_tier ON users(current_tier_id);
CREATE INDEX idx_listings_user ON car_listings(user_id);
CREATE INDEX idx_listings_status ON car_listings(status);
CREATE INDEX idx_listings_type ON car_listings(listing_type);
CREATE INDEX idx_transactions_user ON payment_transactions(user_id);
CREATE INDEX idx_transactions_status ON payment_transactions(status);
CREATE INDEX idx_assistant_threads_user ON assistant_threads(user_id, last_message_at DESC);
CREATE INDEX idx_assistant_messages_thread ON assistant_messages(thread_id, created_at);
CREATE INDEX idx_assistant_actions_thread ON assistant_actions(thread_id, created_at DESC);

-- Row Level Security (RLS) Policies

-- Enable RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE car_listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE assistant_threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE assistant_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE assistant_actions ENABLE ROW LEVEL SECURITY;

-- Users can read their own data
CREATE POLICY "Users can view own profile" ON users
    FOR SELECT USING (auth.uid() = id);

-- Users can update their own profile
CREATE POLICY "Users can update own profile" ON users
    FOR UPDATE USING (auth.uid() = id);

-- Anyone can view active listings
CREATE POLICY "Anyone can view active listings" ON car_listings
    FOR SELECT USING (status = 'active');

-- Users can view their own listings regardless of status
CREATE POLICY "Users can view own listings" ON car_listings
    FOR SELECT USING (auth.uid() = user_id);

-- Users can create listings (enforced by app logic for tier limits)
CREATE POLICY "Users can create listings" ON car_listings
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Users can update their own listings
CREATE POLICY "Users can update own listings" ON car_listings
    FOR UPDATE USING (auth.uid() = user_id);

-- Users can view their own transactions
CREATE POLICY "Users can view own transactions" ON payment_transactions
    FOR SELECT USING (auth.uid() = user_id);

-- Users can view and manage own assistant threads
CREATE POLICY "Users can view own assistant threads" ON assistant_threads
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can create own assistant threads" ON assistant_threads
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own assistant threads" ON assistant_threads
    FOR UPDATE USING (auth.uid() = user_id);

-- Users can view and create own assistant messages
CREATE POLICY "Users can view own assistant messages" ON assistant_messages
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can create own assistant messages" ON assistant_messages
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Users can view and create own assistant actions
CREATE POLICY "Users can view own assistant actions" ON assistant_actions
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can create own assistant actions" ON assistant_actions
    FOR INSERT WITH CHECK (auth.uid() = user_id);


-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_car_listings_updated_at BEFORE UPDATE ON car_listings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_assistant_threads_updated_at BEFORE UPDATE ON assistant_threads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- Function to check if user can create listing (tier limits)
CREATE OR REPLACE FUNCTION can_create_listing(p_user_id UUID)
RETURNS BOOLEAN AS $$
DECLARE
    v_tier_limit INTEGER;
    v_current_count INTEGER;
BEGIN
    -- Get user's tier limit
    SELECT st.listing_limit INTO v_tier_limit
    FROM users u
    JOIN subscription_tiers st ON u.current_tier_id = st.id
    WHERE u.id = p_user_id;

    -- If limit is NULL (unlimited), return true
    IF v_tier_limit IS NULL THEN
        RETURN TRUE;
    END IF;

    -- Count active listings
    SELECT COUNT(*) INTO v_current_count
    FROM car_listings
    WHERE user_id = p_user_id AND status = 'active';

    -- Check if under limit
    RETURN v_current_count < v_tier_limit;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- Function to expire stale pending payments (older than 24 hours)
CREATE OR REPLACE FUNCTION expire_stale_payments()
RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    UPDATE payment_transactions
    SET status = 'failed'
    WHERE status = 'pending'
    AND created_at < NOW() - INTERVAL '24 hours';

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- Function to auto-downgrade expired subscriptions
CREATE OR REPLACE FUNCTION downgrade_expired_subscriptions()
RETURNS INTEGER AS $$
DECLARE
    v_free_tier_id UUID;
    v_count INTEGER;
BEGIN
    SELECT id INTO v_free_tier_id FROM subscription_tiers WHERE name = 'free';

    UPDATE users
    SET current_tier_id = v_free_tier_id,
        subscription_expires_at = NULL,
        updated_at = NOW()
    WHERE subscription_expires_at IS NOT NULL
    AND subscription_expires_at < NOW()
    AND current_tier_id != v_free_tier_id;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- Index on payment status for admin queries
CREATE INDEX idx_transactions_awaiting ON payment_transactions(status) WHERE status IN ('pending', 'awaiting_verification');

-- Index for subscription expiry checks
CREATE INDEX idx_users_sub_expires ON users(subscription_expires_at) WHERE subscription_expires_at IS NOT NULL;

-- Admin RLS policy: admins can read all transactions
CREATE POLICY "Admins can view all transactions" ON payment_transactions
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM users WHERE users.id = auth.uid() AND users.is_admin = TRUE)
    );

-- Admins can update transactions (approve/reject)
CREATE POLICY "Admins can update transactions" ON payment_transactions
    FOR UPDATE USING (
        EXISTS (SELECT 1 FROM users WHERE users.id = auth.uid() AND users.is_admin = TRUE)
    );

-- Service role insert policy for payment transactions
CREATE POLICY "Users can create transactions" ON payment_transactions
    FOR INSERT WITH CHECK (auth.uid() = user_id);
