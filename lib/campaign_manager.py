"""
Campaign Manager: 250/150 Throttle Rule
Governs letter mailing: send max 250 per batch, don't send next batch until 150 of previous batch called 5x each.
"""

from datetime import datetime
from typing import Dict, List, Optional

class CampaignManager:
    """
    Manages letter campaigns with 250/150 throttle.
    
    RULE:
    - Send up to 250 letters per batch
    - After 250 sent → STOP
    - Wait until 150 of those 250 have been called 5+ times in Salesfinity
    - When threshold met → unlock next batch of 250
    - Telegram notification on each milestone
    """
    
    BATCH_SIZE = 250
    CALL_THRESHOLD = 150  # How many of the 250 must reach 5 calls
    CALLS_REQUIRED = 5
    
    def __init__(self, supabase_client, telegram_client=None):
        self.supabase = supabase_client
        self.telegram = telegram_client
    
    def create_campaign(self, name: str, company_ids: List[str], vertical: str = None) -> Dict:
        """
        Create a new campaign. Returns campaign_id.
        Slices company_ids into batches of 250.
        """
        batches = [
            company_ids[i:i+self.BATCH_SIZE]
            for i in range(0, len(company_ids), self.BATCH_SIZE)
        ]
        
        campaign = {
            'name': name,
            'vertical': vertical,
            'created_at': datetime.utcnow().isoformat(),
            'status': 'planning',  # planning -> batch_1_ready -> batch_1_sent -> waiting_calls -> batch_2_ready
            'total_batches': len(batches),
            'current_batch': 1,
            'batches': batches
        }
        
        # Store in Supabase campaigns table
        resp = self.supabase.table('letter_campaigns').insert(campaign).execute()
        campaign_id = resp.data[0]['id']
        
        msg = f"📧 Campaign '{name}': {len(batches)} batches planned. Batch 1: {len(batches[0])} recipients."
        self._notify(msg)
        
        return {'campaign_id': campaign_id, 'total_recipients': len(company_ids), 'batches': len(batches)}
    
    def send_batch(self, campaign_id: str, batch_num: int) -> Dict:
        """
        Send all 250 letters in this batch.
        Returns list of letter_ids sent.
        """
        campaign = self.supabase.table('letter_campaigns').select('*').eq('id', campaign_id).execute().data[0]
        batch = campaign['batches'][batch_num - 1]
        
        letters_sent = []
        for company_id in batch:
            # Render HTML
            letter_html = self._render_letter(company_id)
            # Send via Lob
            letter = self._send_lob(letter_html, company_id, campaign_id)
            letters_sent.append(letter['letter_id'])
        
        # Update campaign in Supabase
        self.supabase.table('letter_campaigns').update({
            'status': f'batch_{batch_num}_sent',
            'current_batch': batch_num,
            'letters_sent': len(letters_sent)
        }).eq('id', campaign_id).execute()
        
        msg = f"✉️ Batch {batch_num}: {len(letters_sent)} letters sent. Waiting for calls..."
        self._notify(msg)
        
        return {'letters_sent': letters_sent, 'batch_num': batch_num}
    
    def check_threshold(self, campaign_id: str) -> Dict:
        """
        Check if 150 of the current batch have been called 5+ times.
        If yes, unlock next batch.
        Returns: {status, calls_tracked, threshold_met, ready_for_next_batch}
        """
        campaign = self.supabase.table('letter_campaigns').select('*').eq('id', campaign_id).execute().data[0]
        batch_num = campaign['current_batch']
        batch_recipients = campaign['batches'][batch_num - 1]
        
        # Query Salesfinity for call outcomes on these recipients
        call_counts = {}
        for company_id in batch_recipients:
            calls = self.supabase.table('call_log').select('id').eq('company_id', company_id).gte('called_at', campaign['created_at']).execute()
            call_counts[company_id] = len(calls.data)
        
        # How many have 5+ calls?
        threshold_met_count = sum(1 for c in call_counts.values() if c >= self.CALLS_REQUIRED)
        threshold_hit = threshold_met_count >= self.CALL_THRESHOLD
        
        status_msg = f"Batch {batch_num}: {threshold_met_count}/{self.CALL_THRESHOLD} recipients called 5+ times. " \
                     f"Need {self.CALL_THRESHOLD - threshold_met_count} more."
        
        if threshold_hit and batch_num < campaign['total_batches']:
            self.supabase.table('letter_campaigns').update({
                'status': f'batch_{batch_num+1}_ready'
            }).eq('id', campaign_id).execute()
            
            status_msg += f" ✅ Threshold hit! Batch {batch_num+1} unlocked."
            self._notify(status_msg)
        else:
            self._notify(status_msg)
        
        return {
            'batch_num': batch_num,
            'calls_tracked': threshold_met_count,
            'threshold': self.CALL_THRESHOLD,
            'ready_for_next_batch': threshold_hit and batch_num < campaign['total_batches']
        }
    
    def _render_letter(self, company_id: str) -> str:
        """Render letter HTML for company (stub — calls letter_engine)."""
        # In production: from lib.letter_engine import LetterEngine; return LetterEngine(supabase).render(company_id)
        return f"<html><!-- Letter for company {company_id} --></html>"
    
    def _send_lob(self, html: str, company_id: str, campaign_id: str) -> Dict:
        """Send letter via Lob API (stub — calls lob_client)."""
        # In production: from lib.lob_client import LobClient; lob = LobClient(); return lob.send_letter(...)
        return {'letter_id': f'lob_{company_id}_{campaign_id}'}
    
    def _notify(self, message: str):
        """Send Telegram notification."""
        if self.telegram:
            self.telegram.send(message)
        else:
            print(f"[CAMPAIGN] {message}")

# Example usage:
# mgr = CampaignManager(supabase_client, telegram_client)
# mgr.create_campaign(
#     'Northeast HVAC',
#     company_ids=['co1', 'co2', ..., 'co500'],
#     vertical='hvac'
# )
# mgr.send_batch(campaign_id='camp_1', batch_num=1)
# # ... wait for calls ...
# mgr.check_threshold(campaign_id='camp_1')  # -> unlocks batch 2 when 150 of 250 called 5x
