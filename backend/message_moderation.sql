-- Message moderation + leakage risk metrics for in-app conversations.
-- Apply in Supabase SQL editor after core messaging tables exist.

CREATE TABLE IF NOT EXISTS conversation_moderation_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    message_id UUID,
    sender_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (action IN ('ALLOW', 'WARN', 'BLOCK')),
    reason TEXT,
    phone_hits INTEGER NOT NULL DEFAULT 0,
    link_hits INTEGER NOT NULL DEFAULT 0,
    intent_score INTEGER NOT NULL DEFAULT 0,
    matched_tokens TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mod_events_conversation ON conversation_moderation_events(conversation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mod_events_action ON conversation_moderation_events(action, created_at DESC);

CREATE OR REPLACE FUNCTION moderate_message_content()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_body TEXT := COALESCE(NEW.body, '');
    v_phone_hits INTEGER := 0;
    v_link_hits INTEGER := 0;
    v_intent_score INTEGER := 0;
    v_action TEXT := 'ALLOW';
    v_reason TEXT := 'Message accepted.';
BEGIN
    v_phone_hits := COALESCE((SELECT COUNT(*) FROM regexp_matches(v_body, '(?:\+?\d[\d\s().-]{6,}\d)', 'g')), 0);
    v_link_hits := COALESCE((SELECT COUNT(*) FROM regexp_matches(lower(v_body), '(https?://|www\.|wa\.me/|t\.me/|telegram|instagram\.com|facebook\.com|discord\.gg|@\w+)', 'g')), 0);
    v_intent_score := COALESCE((SELECT COUNT(*) FROM regexp_matches(lower(v_body), '(call me|text me|whatsapp me|dm me|email me|reach me on|send your number)', 'g')), 0);

    IF v_phone_hits > 0 OR v_link_hits > 0 THEN
        v_action := 'BLOCK';
        v_reason := 'External phone/link sharing is not allowed.';
    ELSIF v_intent_score > 0 THEN
        v_action := 'WARN';
        v_reason := 'Potential off-platform intent detected.';
    END IF;

    INSERT INTO conversation_moderation_events (
        conversation_id,
        message_id,
        sender_id,
        action,
        reason,
        phone_hits,
        link_hits,
        intent_score
    ) VALUES (
        NEW.conversation_id,
        NEW.id,
        NEW.sender_id,
        v_action,
        v_reason,
        v_phone_hits,
        v_link_hits,
        v_intent_score
    );

    IF v_action = 'BLOCK' THEN
        RAISE EXCEPTION 'Message blocked by PrimeDrive policy: remove phone numbers/external contact links.';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_moderate_messages ON messages;
CREATE TRIGGER trg_moderate_messages
BEFORE INSERT ON messages
FOR EACH ROW
EXECUTE FUNCTION moderate_message_content();
