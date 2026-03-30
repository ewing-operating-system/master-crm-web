-- =============================================================================
-- MANDATORY TABLES — Run in Supabase SQL Editor
-- =============================================================================

-- 1. Meeting notes (meeting page v2 auto-save)
CREATE TABLE IF NOT EXISTS meeting_notes (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  meeting_id text NOT NULL,
  field_name text NOT NULL,
  field_value text,
  captured_at timestamptz DEFAULT now(),
  UNIQUE(meeting_id, field_name)
);

-- 2. Campaign batches (250/150 governor)
CREATE TABLE IF NOT EXISTS campaign_batches (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  batch_number integer NOT NULL,
  entity text NOT NULL DEFAULT 'next_chapter',
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'MAILING', 'CALLING', 'COMPLETE', 'PAUSED')),
  letter_count integer NOT NULL DEFAULT 0 CHECK (letter_count <= 250),
  call_target integer NOT NULL DEFAULT 150,
  calls_completed integer NOT NULL DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  locked_at timestamptz,
  completed_at timestamptz
);

-- Only one active batch at a time
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_batch
  ON campaign_batches (entity)
  WHERE status IN ('MAILING', 'CALLING');

-- 3. Call outcomes (Salesfinity tracking)
CREATE TABLE IF NOT EXISTS call_outcomes (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  batch_id uuid REFERENCES campaign_batches(id),
  target_id uuid REFERENCES targets(id),
  contact_name text,
  phone text,
  attempt_number integer NOT NULL DEFAULT 1 CHECK (attempt_number <= 5),
  outcome text CHECK (outcome IN ('CONNECTED', 'VOICEMAIL', 'NO_ANSWER', 'WRONG_NUMBER', 'CALLBACK', 'NOT_INTERESTED', 'INTERESTED')),
  notes text,
  called_at timestamptz DEFAULT now()
);

-- 4. Letter campaigns (Lob tracking)
CREATE TABLE IF NOT EXISTS letter_campaigns (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  batch_id uuid REFERENCES campaign_batches(id),
  target_id uuid REFERENCES targets(id),
  lob_letter_id text,
  variant text CHECK (variant IN ('touch_1', 'touch_2', 'touch_3')),
  status text DEFAULT 'QUEUED' CHECK (status IN ('QUEUED', 'SENT', 'DELIVERED', 'RETURNED')),
  sent_at timestamptz,
  delivered_at timestamptz,
  created_at timestamptz DEFAULT now()
);

-- 5. Add RESEARCHED to pipeline_status enum (if it's an enum)
DO $$ BEGIN
  ALTER TYPE pipeline_status ADD VALUE IF NOT EXISTS 'RESEARCHED';
EXCEPTION WHEN others THEN
  RAISE NOTICE 'pipeline_status is not an enum or RESEARCHED already exists — skipping';
END $$;

-- 6. Index for regeneration scripts
CREATE INDEX IF NOT EXISTS idx_targets_pipeline_status ON targets(pipeline_status);
CREATE INDEX IF NOT EXISTS idx_targets_research_completed ON targets(research_completed_at) WHERE research_completed_at IS NOT NULL;
