"""
Lob API integration for physical letter mailing.
Production-ready client for rendering + mailing letters via Lob.
"""

import os
import requests
from typing import Dict, Optional

class LobClient:
    """Lob API wrapper for letter mailing."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('LOB_API_KEY')
        if not self.api_key:
            raise ValueError("LOB_API_KEY not set in environment")
        self.base_url = "https://api.lob.com/v1"
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
    
    def send_letter(
        self,
        html: str,
        to_address: Dict[str, str],
        from_address: Dict[str, str] = None,
        campaign_id: str = None,
        metadata: Dict = None
    ) -> Dict:
        """
        Send a physical letter via Lob.
        
        Args:
            html: Rendered letter HTML (must be 8.5x11, Lob-compliant)
            to_address: {name, email, address_line1, address_line2, city, state, zip}
            from_address: {name, email, address_line1, city, state, zip} (company letterhead)
            campaign_id: Track which campaign this letter belongs to
            metadata: Custom metadata to track alongside letter_id
        
        Returns:
            {letter_id, status, postage, expected_delivery_date, tracking_url}
        """
        
        default_from = {
            'name': 'Next Chapter Capital',
            'address_line1': '123 Main Street',
            'city': 'New York',
            'state': 'NY',
            'zip': '10001'
        }
        
        from_address = from_address or default_from
        
        payload = {
            'file': html,
            'to': to_address,
            'from': from_address,
            'color': False,
            'metadata': {
                'campaign_id': campaign_id,
                **(metadata or {})
            }
        }
        
        response = requests.post(
            f"{self.base_url}/letters",
            auth=(self.api_key, ''),
            data=payload
        )
        
        if response.status_code != 200:
            raise Exception(f"Lob API error: {response.status_code} - {response.text}")
        
        data = response.json()
        return {
            'letter_id': data.get('id'),
            'status': data.get('status'),  # processed, cancelled, sent
            'postage': data.get('postage'),  # cents
            'expected_delivery_date': data.get('expected_delivery_date'),
            'tracking_url': data.get('url')
        }
    
    def get_letter_status(self, letter_id: str) -> Dict:
        """Check status of a sent letter."""
        response = requests.get(
            f"{self.base_url}/letters/{letter_id}",
            auth=(self.api_key, '')
        )
        if response.status_code != 200:
            raise Exception(f"Letter not found: {letter_id}")
        data = response.json()
        return {
            'letter_id': data.get('id'),
            'status': data.get('status'),
            'sent_date': data.get('sent_date'),
            'expected_delivery_date': data.get('expected_delivery_date')
        }

# Example usage:
# lob = LobClient()
# letter = lob.send_letter(
#     html=rendered_html,
#     to_address={
#         'name': 'Larry Casey',
#         'address_line1': '456 Elm Street',
#         'city': 'Cheyenne',
#         'state': 'WY',
#         'zip': '82001'
#     },
#     campaign_id='batch_1',
#     metadata={'vertical': 'water_treatment'}
# )
# print(f"Letter {letter['letter_id']} mailed. Tracking: {letter['tracking_url']}")
