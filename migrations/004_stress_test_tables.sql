-- ============================================================
-- STRESS TEST TABLES — Agent Tournament & Benchmark System
-- Migration 004 — 2026-03-31
-- ============================================================

-- 1. Execution tracking with live budget counter
CREATE TABLE IF NOT EXISTS stress_test_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_name TEXT NOT NULL,
  status TEXT DEFAULT 'running' CHECK (status IN ('running','completed','failed','aborted')),
  budget_total NUMERIC(10,2) DEFAULT 100.00,
  budget_spent NUMERIC(10,4) DEFAULT 0,
  budget_remaining NUMERIC(10,4) DEFAULT 100.00,
  total_buyers_scored INTEGER DEFAULT 0,
  total_buyers_re_enriched INTEGER DEFAULT 0,
  total_agent_calls INTEGER DEFAULT 0,
  total_exa_searches INTEGER DEFAULT 0,
  phases_completed TEXT[] DEFAULT '{}',
  config JSONB DEFAULT '{}',
  started_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  error_log TEXT
);

-- 2. Quality scores for all 68 buyer pages (6 dimensions)
CREATE TABLE IF NOT EXISTS benchmark_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID REFERENCES stress_test_runs(id),
  buyer_slug TEXT NOT NULL,
  buyer_name TEXT NOT NULL,
  html_file TEXT NOT NULL,
  page_line_count INTEGER,
  score_narrative_quality NUMERIC(3,1),
  score_strategic_depth NUMERIC(3,1),
  score_evidence_density NUMERIC(3,1),
  score_actionability NUMERIC(3,1),
  score_completeness NUMERIC(3,1),
  score_structure NUMERIC(3,1),
  score_overall NUMERIC(4,2),
  quality_tier TEXT CHECK (quality_tier IN ('gold','good','incomplete','empty')),
  gap_narrative TEXT,
  gap_structure TEXT,
  gap_tone TEXT,
  scoring_agent TEXT,
  scoring_model TEXT,
  raw_agent_response JSONB,
  scored_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(run_id, buyer_slug)
);
CREATE INDEX IF NOT EXISTS idx_benchmark_tier ON benchmark_scores(quality_tier);
CREATE INDEX IF NOT EXISTS idx_benchmark_score ON benchmark_scores(score_overall);

-- 3. Every agent call logged — the core performance table
CREATE TABLE IF NOT EXISTS agent_performance_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID REFERENCES stress_test_runs(id),
  agent_id TEXT NOT NULL,
  agent_model TEXT NOT NULL,
  task_type TEXT NOT NULL,
  task_id TEXT,
  input_size_chars INTEGER,
  output_size_chars INTEGER,
  output_quality_score NUMERIC(4,2),
  output_quality_notes TEXT,
  output_usable BOOLEAN DEFAULT TRUE,
  cost_usd NUMERIC(10,6) DEFAULT 0,
  duration_seconds INTEGER,
  exa_searches_used INTEGER DEFAULT 0,
  tournament_group TEXT,
  tournament_rank INTEGER,
  was_swapped BOOLEAN DEFAULT FALSE,
  swap_reason TEXT,
  prompt_variant TEXT,
  retry_count INTEGER DEFAULT 0,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_apl_agent ON agent_performance_log(agent_id);
CREATE INDEX IF NOT EXISTS idx_apl_task ON agent_performance_log(task_type);
CREATE INDEX IF NOT EXISTS idx_apl_tournament ON agent_performance_log(tournament_group);

-- 4. Scraped quality attributes from debbiedealroom.com
CREATE TABLE IF NOT EXISTS lovable_benchmark (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID REFERENCES stress_test_runs(id),
  page_name TEXT NOT NULL,
  page_url TEXT,
  tone_keywords TEXT[],
  structure_elements TEXT[],
  narrative_style TEXT,
  specificity_level TEXT,
  section_count INTEGER,
  word_count INTEGER,
  scraped_text TEXT,
  scraped_structure JSONB,
  rubric JSONB,
  scraped_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Tournament results — up to 3 agents competing per buyer
CREATE TABLE IF NOT EXISTS re_enrichment_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID REFERENCES stress_test_runs(id),
  buyer_slug TEXT NOT NULL,
  buyer_name TEXT NOT NULL,
  original_score NUMERIC(4,2),
  agent_1_id TEXT, agent_1_model TEXT, agent_1_output JSONB, agent_1_score NUMERIC(4,2), agent_1_cost NUMERIC(10,6), agent_1_duration INTEGER,
  agent_2_id TEXT, agent_2_model TEXT, agent_2_output JSONB, agent_2_score NUMERIC(4,2), agent_2_cost NUMERIC(10,6), agent_2_duration INTEGER,
  agent_3_id TEXT, agent_3_model TEXT, agent_3_output JSONB, agent_3_score NUMERIC(4,2), agent_3_cost NUMERIC(10,6), agent_3_duration INTEGER,
  winning_agent TEXT,
  winning_score NUMERIC(4,2),
  score_improvement NUMERIC(4,2),
  exa_searches_used INTEGER DEFAULT 0,
  total_cost NUMERIC(10,4),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(run_id, buyer_slug)
);

-- Views
CREATE OR REPLACE VIEW agent_leaderboard AS
SELECT
  agent_id, agent_model, task_type,
  COUNT(*) as total_calls,
  ROUND(AVG(output_quality_score),2) as avg_quality,
  ROUND(AVG(cost_usd),6) as avg_cost,
  ROUND(AVG(duration_seconds),0) as avg_duration_sec,
  SUM(CASE WHEN tournament_rank = 1 THEN 1 ELSE 0 END) as tournament_wins,
  SUM(CASE WHEN was_swapped THEN 1 ELSE 0 END) as times_swapped_out,
  SUM(CASE WHEN output_usable THEN 1 ELSE 0 END) as usable_outputs,
  ROUND(SUM(cost_usd),4) as total_cost
FROM agent_performance_log
GROUP BY agent_id, agent_model, task_type
ORDER BY avg_quality DESC;

CREATE OR REPLACE VIEW budget_tracker AS
SELECT
  run_id,
  COUNT(*) as total_calls,
  SUM(exa_searches_used) as total_exa,
  ROUND(SUM(cost_usd),4) as total_spent,
  ROUND(100.00 - SUM(cost_usd),4) as remaining
FROM agent_performance_log
GROUP BY run_id;
