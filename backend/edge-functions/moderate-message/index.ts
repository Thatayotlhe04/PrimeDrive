// Supabase Edge Function: moderate-message
// Optional companion to DB trigger; frontend calls this for pre-send UX warnings.

import { serve } from 'https://deno.land/std@0.224.0/http/server.ts';

interface ModerationRequest {
  conversation_id?: string;
  sender_id?: string;
  body?: string;
}

serve(async (req) => {
  if (req.method !== 'POST') {
    return new Response('Method not allowed', { status: 405 });
  }

  const payload = (await req.json()) as ModerationRequest;
  const text = (payload.body || '').trim();

  const phoneHits = (text.match(/(?:\+?\d[\d\s().-]{6,}\d)/g) || []).length;
  const linkHits = (
    text.match(/(https?:\/\/|www\.|wa\.me\/|t\.me\/|telegram|instagram\.com|facebook\.com|discord\.gg|@\w+)/gi) || []
  ).length;
  const intentHits = (
    text.match(/(call me|text me|whatsapp me|dm me|email me|reach me on|send your number)/gi) || []
  ).length;

  const shouldBlock = phoneHits > 0 || linkHits > 0;
  const shouldWarn = !shouldBlock && intentHits > 0;

  return Response.json({
    shouldBlock,
    shouldWarn,
    phoneHits,
    linkHits,
    intentHits,
    policy: {
      block: 'Phone numbers and external contact links are blocked in in-app chat.',
      warn: 'Off-platform intent warnings are shown to preserve in-app protections.'
    }
  });
});
