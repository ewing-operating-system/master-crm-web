#!/usr/bin/env node
// Credentials: all keys come from env vars. See .env.example for names.
// Vercel injects these at runtime. Local dev: copy .env.example to .env

const { createClient } = require('@supabase/supabase-js');
const path = require('path');
const fs = require('fs');
require('dotenv').config({ path: '/Users/clawdbot/.openclaw/workspace/.env' });

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

// Config-driven classification keywords from vertical configs
const configDir = path.resolve(__dirname, '../../lib/config/verticals');
function loadJson(p) { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return null; } }

const verticalConfigs = [
  { config: loadJson(path.join(configDir, 'home_services.json')), entity: null },
  { config: loadJson(path.join(configDir, 'healthcare_energy.json')), entity: null },
  { config: loadJson(path.join(configDir, 'saas_recruiting.json')), entity: null },
].filter(v => v.config);

// Build entity lookup from vertical configs: keyword → entity
function classifyByVerticalKeywords(verticalStr) {
  const v = verticalStr.toLowerCase();
  for (const { config } of verticalConfigs) {
    const keywords = config.classification_keywords?.industry || [];
    if (keywords.some(kw => v.includes(kw))) {
      return config.entity_defaults?.entity || 'unknown';
    }
  }
  return 'unknown';
}

if (!supabaseUrl || !supabaseServiceKey) {
  console.error('Missing Supabase credentials');
  process.exit(1);
}

const supabase = createClient(supabaseUrl, supabaseServiceKey);

async function classifyRemaining() {
  console.log('Classifying remaining unclassified targets...');
  
  // Get count of unclassified targets
  const { data: targets, error } = await supabase
    .from('targets')
    .select('id, company_name, vertical, notes')
    .or('notes.not.ilike.%ENTITY:%,notes.not.ilike.%Entity=%')
    .limit(100);
    
  if (error) {
    console.error('Error:', error);
    return;
  }
  
  console.log(`Found ${targets.length} unclassified targets`);
  
  if (targets.length === 0) {
    console.log('✅ All targets are classified!');
    return;
  }
  
  console.log('Starting classification...');
  // Simple classification logic
  for (const target of targets) {
    const vertical = target.vertical?.toLowerCase() || '';
    let entity = classifyByVerticalKeywords(vertical);
    
    const newNotes = `${target.notes || ''}\nCLASSIFIED ${new Date().toISOString().split('T')[0]}: Entity=${entity}`;
    
    await supabase
      .from('targets')
      .update({ notes: newNotes, updated_at: new Date().toISOString() })
      .eq('id', target.id);
      
    console.log(`✓ ${target.company_name}: ${entity}`);
  }
  
  console.log('✅ Classification complete');
}

classifyRemaining().catch(console.error);
