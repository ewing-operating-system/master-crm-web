"""
Salesfinity Integration: Load enriched contacts + track call outcomes.
Feeds call_log back to Supabase.
"""

import os
import requests
from typing import Dict, List, Optional

class SalesffinityClient:
    """Salesfinity dialer integration."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('SALESFINITY_API_KEY')
        if not self.api_key:
            raise ValueError("SALESFINITY_API_KEY not set in environment")
        self.base_url = "https://api.salesfinity.com/v1"
    
    def create_dialer_list(self, name: str, contacts: List[Dict]) -> Dict:
        """
        Create a new dialer list in Salesfinity.
        
        Args:
            name: List name (e.g., "Northeast HVAC Batch 1")
            contacts: [{name, phone, company, enriched_data}, ...]
        
        Returns:
            {list_id, contacts_loaded, status}
        """
        payload = {
            'name': name,
            'contacts': contacts,
            'metadata': {
                'source': 'master-crm',
                'auto_generated': True
            }
        }
        
        response = requests.post(
            f"{self.base_url}/dialer/lists",
            headers={'Authorization': f'Bearer {self.api_key}'},
            json=payload
        )
        
        if response.status_code != 201:
            raise Exception(f"Salesfinity error: {response.status_code} - {response.text}")
        
        data = response.json()
        return {
            'list_id': data.get('id'),
            'contacts_loaded': len(contacts),
            'status': data.get('status')
        }
    
    def get_call_outcomes(self, list_id: str, since: str = None) -> List[Dict]:
        """
        Fetch call outcomes for a dialer list.
        
        Returns:
            [{contact_id, phone, outcome, duration, recorded_at}, ...]
            Outcomes: "connected", "voicemail", "no_answer", "callback_requested", "wrong_number"
        """
        params = {}
        if since:
            params['since'] = since
        
        response = requests.get(
            f"{self.base_url}/dialer/lists/{list_id}/outcomes",
            headers={'Authorization': f'Bearer {self.api_key}'},
            params=params
        )
        
        if response.status_code != 200:
            raise Exception(f"Salesfinity error: {response.status_code}")
        
        return response.json().get('outcomes', [])
    
    def sync_outcomes_to_supabase(self, supabase_client, list_id: str, campaign_id: str = None):
        """
        Fetch outcomes from Salesfinity and write to Supabase call_log.
        """
        outcomes = self.get_call_outcomes(list_id)
        
        for outcome in outcomes:
            # Map Salesfinity outcome to our schema
            call_record = {
                'contact_id': outcome.get('contact_id'),
                'list_id': list_id,
                'campaign_id': campaign_id,
                'outcome_category': self._map_outcome(outcome.get('outcome')),
                'duration_seconds': outcome.get('duration'),
                'called_at': outcome.get('recorded_at'),
                'raw_salesfinity_data': outcome
            }
            
            # Insert/upsert in Supabase
            supabase_client.table('call_log').upsert(call_record).execute()
        
        return {'synced_count': len(outcomes)}
    
    @staticmethod
    def _map_outcome(salesfinity_outcome: str) -> str:
        """Map Salesfinity outcomes to our call_log.outcome_category values."""
        mapping = {
            'connected': 'connected',
            'voicemail': 'voicemail',
            'no_answer': 'no_answer',
            'callback_requested': 'callback_requested',
            'wrong_number': 'wrong_number'
        }
        return mapping.get(salesfinity_outcome, 'unknown')

# Example usage:
# sf = SalesffinityClient()
# list_id = sf.create_dialer_list(
#     'Northeast HVAC Batch 1',
#     contacts=[
#         {'name': 'Bob Smith', 'phone': '+14155551234', 'company': 'Bob\'s AC'}
#     ]
# )
# # ... wait for calls ...
# sf.sync_outcomes_to_supabase(supabase, list_id, campaign_id='camp_1')
