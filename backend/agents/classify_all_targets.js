// Credentials: all keys come from env vars. See .env.example for names.
// Vercel injects these at runtime. Local dev: copy .env.example to .env

const { createClient } = require('@supabase/supabase-js');
const path = require('path');
const fs = require('fs');
require('dotenv').config({ path: '/Users/clawdbot/.openclaw/workspace/.env' });

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

// ---------------------------------------------------------------------------
// Config-driven classification keywords — loaded from vertical configs + shared_keywords
// ---------------------------------------------------------------------------
const configDir = path.resolve(__dirname, '../../lib/config');

function loadJson(filePath) {
  try { return JSON.parse(fs.readFileSync(filePath, 'utf8')); }
  catch (e) { return null; }
}

const sharedKeywords = loadJson(path.join(configDir, 'shared_keywords.json')) || {};
const homeServicesConfig = loadJson(path.join(configDir, 'verticals/home_services.json'));
const healthcareEnergyConfig = loadJson(path.join(configDir, 'verticals/healthcare_energy.json'));
const saasRecruitingConfig = loadJson(path.join(configDir, 'verticals/saas_recruiting.json'));

// Intent keywords from shared_keywords.json
const INTENT_HIRING = sharedKeywords.intent_hiring || [];
const INTENT_TRANSACTION = sharedKeywords.intent_transaction || [];
const INTENT_CAPITAL = sharedKeywords.intent_capital || [];

// Industry keywords from vertical configs
const TRADES_KEYWORDS = (homeServicesConfig?.classification_keywords?.industry) || [];
const HEALTHCARE_ENERGY_KEYWORDS = (healthcareEnergyConfig?.classification_keywords?.industry) || [];
const SAAS_KEYWORDS = (saasRecruitingConfig?.classification_keywords?.industry) || [];
const FINANCIAL_KEYWORDS = (healthcareEnergyConfig?.classification_keywords?.lp_keywords) || [];

if (!supabaseUrl || !supabaseServiceKey) {
  console.error('Missing Supabase credentials in .env file');
  process.exit(1);
}

const supabase = createClient(supabaseUrl, supabaseServiceKey);

// Classification logic from Entity Classification Guide
function classifyTarget(target) {
  const companyName = target.company_name || '';
  const vertical = target.vertical || '';
  const researchJson = target.research_json || {};
  const notes = target.notes || '';
  
  // Combine text for analysis
  const combinedText = `${companyName} ${vertical} ${JSON.stringify(researchJson)} ${notes}`.toLowerCase();
  
  // Classification logic
  let entity = 'unknown';
  let subType = 'unknown';
  let confidence = 0;
  let reason = '';
  let method = 'deterministic_decision_tree';
  
  // Check for explicit intent first (keywords from shared_keywords.json)
  const hasHiringIntent = INTENT_HIRING.some(keyword => combinedText.includes(keyword));
  const hasTransactionIntent = INTENT_TRANSACTION.some(keyword => combinedText.includes(keyword));
  const hasCapitalIntent = INTENT_CAPITAL.some(keyword => combinedText.includes(keyword));
  
  // Step 1: Hiring intent (RevsUp)
  if (hasHiringIntent) {
    entity = 'revsup';
    subType = 'recruiting';
    confidence = 2.0;
    reason = 'Explicit hiring/recruiting intent detected';
  }
  // Step 2: Transaction intent (Next Chapter)
  else if (hasTransactionIntent) {
    entity = 'next_chapter';
    // Check if sell-side or buy-side
    const sellKeywords = ['sell my business', 'seller', 'exit', 'succession', 'retirement'];
    const buyKeywords = ['buyer', 'acquisition', 'roll-up', 'acquire'];
    const isSellSide = sellKeywords.some(keyword => combinedText.includes(keyword));
    const isBuySide = buyKeywords.some(keyword => combinedText.includes(keyword));
    
    if (isSellSide) {
      subType = 'sell-side';
      reason = 'Explicit sell-side transaction intent detected';
    } else if (isBuySide) {
      subType = 'buy-side';
      reason = 'Explicit buy-side transaction intent detected';
    } else {
      subType = 'transaction';
      reason = 'Transaction intent detected (buying/selling business)';
    }
    confidence = 2.0;
  }
  // Step 3: Capital intent (AND Capital)
  else if (hasCapitalIntent) {
    entity = 'and_capital';
    // Determine if LP side or investment side
    const lpKeywords = ['lp', 'family office', 'ria', 'institutional', 'fundraising', 'allocator'];
    const investmentKeywords = ['hospital', 'medical', 'health', 'energy', 'asset', 'investment target'];
    const isLPSide = lpKeywords.some(keyword => combinedText.includes(keyword));
    const isInvestmentSide = investmentKeywords.some(keyword => combinedText.includes(keyword));
    
    if (isLPSide) {
      subType = 'lp';
      reason = 'Explicit LP/capital raising intent detected';
    } else if (isInvestmentSide) {
      subType = 'investment';
      reason = 'Explicit investment target intent detected';
    } else {
      subType = 'capital';
      reason = 'Capital/investment intent detected';
    }
    confidence = 2.0;
  }
  // Step 4: Company-Type Fallback (no explicit intent)
  else {
    // Check company type (keywords from vertical config files)
    const vertLower = vertical.toLowerCase();
    const isTrades = TRADES_KEYWORDS.some(keyword => combinedText.includes(keyword)) ||
                    TRADES_KEYWORDS.some(keyword => vertLower.includes(keyword));

    const isHealthcareOrEnergy = HEALTHCARE_ENERGY_KEYWORDS.some(keyword => combinedText.includes(keyword));
    const isHealthcare = ['hospital', 'medical', 'health', 'wellness', 'longevity', 'bio-tech', 'med-tech'].some(k => combinedText.includes(k));
    const isSaaS = SAAS_KEYWORDS.some(keyword => combinedText.includes(keyword));
    const isFinancial = FINANCIAL_KEYWORDS.some(keyword => combinedText.includes(keyword));
    
    if (isTrades) {
      entity = 'next_chapter';
      subType = 'trades';
      confidence = 1.0;
      reason = 'Trades/home services company detected (company-type fallback)';
    } else if (isHealthcareOrEnergy) {
      entity = 'and_capital';
      subType = isHealthcare ? 'healthcare' : 'energy';
      confidence = 1.0;
      reason = `${isHealthcare ? 'Healthcare' : 'Energy'} company detected (company-type fallback)`;
    } else if (isFinancial) {
      entity = 'and_capital';
      subType = 'financial';
      confidence = 1.0;
      reason = 'Financial entity detected (company-type fallback)';
    } else if (isSaaS) {
      // SaaS without hiring intent gets no tag
      entity = 'unknown';
      subType = 'unknown';
      confidence = 0;
      reason = 'SaaS company detected but no hiring intent';
    } else {
      entity = 'unknown';
      subType = 'unknown';
      confidence = 0;
      reason = 'No classification signals detected';
    }
  }
  
  // For pipeline targets, we tag even with confidence 1.0
  if (confidence < 1.0) {
    entity = 'unknown';
    subType = 'unknown';
    reason = `${reason} (confidence too low)`;
  }
  
  return {
    entity,
    entity_sub_type: subType,
    classification_confidence: confidence,
    classification_reason: reason,
    classification_method: method
  };
}

async function classifyAllTargets() {
  console.log('Starting batch classification of all unclassified targets...');
  
  try {
    // 1. Get all targets without entity classification
    console.log('\n1. Fetching unclassified targets...');
    const { data: targets, error: targetsError } = await supabase
      .from('targets')
      .select('*')
      .or('notes.not.ilike.%ENTITY:%,notes.not.ilike.%Entity=%')
      .limit(50); // Start with 50 to test
    
    if (targetsError) {
      console.error('Error fetching targets:', targetsError);
      throw targetsError;
    }
    
    console.log(`Found ${targets.length} unclassified targets`);
    
    // 2. Classify each target
    console.log('\n2. Classifying targets...');
    let processed = 0;
    let errors = 0;
    
    for (const target of targets) {
      try {
        console.log(`\nProcessing: ${target.company_name} (${target.vertical})`);
        
        // Classify
        const classification = classifyTarget(target);
        
        console.log(`  → Entity: ${classification.entity}, Confidence: ${classification.classification_confidence}`);
        
        // Update target notes
        const currentNotes = target.notes || '';
        const newNotes = `CLASSIFIED ${new Date().toISOString().split('T')[0]}: Entity=${classification.entity}, Sub-type=${classification.entity_sub_type}, Confidence=${classification.classification_confidence}, Reason=${classification.classification_reason}. ${currentNotes}`;
        
        const { error: updateError } = await supabase
          .from('targets')
          .update({
            notes: newNotes,
            updated_at: new Date().toISOString()
          })
          .eq('id', target.id);
          
        if (updateError) {
          console.error(`  Error updating target: ${updateError.message}`);
          errors++;
          continue;
        }
        
        // Log to pipeline_log
        const { error: logError } = await supabase
          .from('pipeline_log')
          .insert({
            agent: 'controller',
            action: 'batch_classification',
            target_id: target.id,
            target_name: target.company_name,
            details: {
              classification,
              target_vertical: target.vertical,
              timestamp: new Date().toISOString()
            },
            created_at: new Date().toISOString()
          });
          
        if (logError) {
          console.error(`  Error logging: ${logError.message}`);
          errors++;
        } else {
          processed++;
          console.log(`  ✅ Classified as ${classification.entity}`);
        }
        
        // Small delay to avoid rate limiting
        await new Promise(resolve => setTimeout(resolve, 100));
        
      } catch (error) {
        console.error(`  Error processing ${target.company_name}:`, error.message);
        errors++;
      }
    }
    
    // 3. Summary
    console.log('\n3. Classification summary:');
    console.log(`   Total processed: ${processed + errors}`);
    console.log(`   Successfully classified: ${processed}`);
    console.log(`   Errors: ${errors}`);
    
    // 4. Update queue items
    console.log('\n4. Updating queue items...');
    
    // Mark READY queue items for classified targets as DONE
    const targetIds = targets.map(t => t.id);
    
    const { data: queueItems, error: queueError } = await supabase
      .from('dialer_queue')
      .select('*')
      .in('target_id', targetIds)
      .eq('status', 'READY');
      
    if (queueError) {
      console.error('Error fetching queue items:', queueError);
    } else {
      console.log(`Found ${queueItems.length} READY queue items for these targets`);
      
      if (queueItems.length > 0) {
        // Update them to DONE
        const { error: updateQueueError } = await supabase
          .from('dialer_queue')
          .update({
            status: 'done',
            updated_at: new Date().toISOString()
          })
          .in('id', queueItems.map(q => q.id));
          
        if (updateQueueError) {
          console.error('Error updating queue items:', updateQueueError);
        } else {
          console.log(`✅ Updated ${queueItems.length} queue items to DONE`);
        }
      }
    }
    
    console.log('\n🎉 Batch classification completed!');
    return {
      success: true,
      processed,
      errors,
      queueItemsUpdated: queueItems?.length || 0
    };
    
  } catch (error) {
    console.error('Error in batch classification:', error);
    throw error;
  }
}

// Run batch classification
classifyAllTargets()
  .then(result => {
    console.log('\nBatch classification task completed');
    console.log(JSON.stringify(result, null, 2));
    process.exit(0);
  })
  .catch(error => {
    console.error('\nBatch classification task failed:', error);
    process.exit(1);
  });