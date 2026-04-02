-- Debbie Buyer Review Feedback Table
-- Stores both top-level buyer verdicts and per-section content feedback.
-- Every row carries BOTH top_verdict (the buyer-level "north star") and
-- section_verdict (the section-level quality assessment) so each row is
-- a complete record queryable from either direction.

CREATE TABLE IF NOT EXISTS debbie_buyer_review_feedback (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  buyer_slug                text NOT NULL,
  buyer_name                text NOT NULL,
  section_key               text NOT NULL,
  -- Top-level verdict (stored on EVERY row, updated in batch when changed)
  top_verdict               text CHECK (top_verdict IS NULL OR top_verdict IN (
                              'tier_1_target','good_target',
                              'remove_personal','remove_no_business_fit',
                              'remove_company_health','remove_other'
                            )),
  top_verdict_custom_label  text,
  top_comment               text,
  -- Section-level feedback
  section_verdict           text CHECK (section_verdict IS NULL OR section_verdict IN (
                              'accurate_relevant_valuable',
                              'accurate_not_relevant',
                              'remove_altogether'
                            )),
  section_comment           text,
  -- Per-product sub-feedback (for market_reputation__product_slug keys)
  product_verdict           text CHECK (product_verdict IS NULL OR product_verdict IN (
                              'keep','remove_irrelevant','remove_inaccurate'
                            )),
  -- Meta
  reviewer_name             text NOT NULL DEFAULT 'Debbie',
  entity                    text NOT NULL DEFAULT 'next_chapter',
  created_at                timestamptz NOT NULL DEFAULT now(),
  updated_at                timestamptz NOT NULL DEFAULT now(),
  UNIQUE(buyer_slug, section_key, reviewer_name)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_dbrf_buyer ON debbie_buyer_review_feedback(buyer_slug);
CREATE INDEX IF NOT EXISTS idx_dbrf_section ON debbie_buyer_review_feedback(section_key, section_verdict);
CREATE INDEX IF NOT EXISTS idx_dbrf_verdict ON debbie_buyer_review_feedback(top_verdict);
CREATE INDEX IF NOT EXISTS idx_dbrf_entity ON debbie_buyer_review_feedback(entity);

-- Feedback export snapshots — stores point-in-time summaries pushed from the page
CREATE TABLE IF NOT EXISTS debbie_review_exports (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  export_type       text NOT NULL DEFAULT 'summary',
  buyer_count       int,
  reviewed_count    int,
  payload           jsonb NOT NULL,
  exported_by       text NOT NULL DEFAULT 'Debbie',
  entity            text NOT NULL DEFAULT 'next_chapter',
  created_at        timestamptz NOT NULL DEFAULT now()
);

-- Section value rollup view — shows which sections Debbie finds valuable across all buyers
CREATE OR REPLACE VIEW debbie_section_value_rollup AS
SELECT
  section_key,
  COUNT(*) FILTER (WHERE section_verdict = 'accurate_relevant_valuable') AS valuable_count,
  COUNT(*) FILTER (WHERE section_verdict = 'accurate_not_relevant') AS not_relevant_count,
  COUNT(*) FILTER (WHERE section_verdict = 'remove_altogether') AS remove_count,
  COUNT(*) AS total_reviews,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE section_verdict = 'remove_altogether') / NULLIF(COUNT(*), 0),
    1
  ) AS removal_pct
FROM debbie_buyer_review_feedback
WHERE section_key != 'top_level'
  AND section_verdict IS NOT NULL
GROUP BY section_key
ORDER BY removal_pct DESC;
