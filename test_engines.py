"""Test the letter and meeting engines with 2 companies."""

import sys
sys.path.insert(0, './lib')

from letter_engine import LetterEngine
from meeting_engine_v2 import MeetingEngineV2
from datetime import date

# Mock Supabase client for testing
class MockSupabaseClient:
    def __init__(self):
        pass
    
    def table(self, name):
        return self

# Initialize engines
sb = MockSupabaseClient()
letter_engine = LetterEngine(sb)
meeting_engine = MeetingEngineV2(sb)

print("=" * 70)
print("TESTING LETTER ENGINE")
print("=" * 70)

# Test 1: AquaScience letter
print("\n1. AquaScience — Letter Render")
try:
    letter_html = letter_engine.render('aquascience', variant=1)
    print(f"   ✅ Letter rendered: {len(letter_html)} chars")
except Exception as e:
    print(f"   ⚠️ {type(e).__name__}: {e}")

# Test 2: Springer Floor letter
print("\n2. Springer Floor — Letter Render")
try:
    letter_html = letter_engine.render('springer_floor', variant=1)
    print(f"   ✅ Letter rendered: {len(letter_html)} chars")
except Exception as e:
    print(f"   ⚠️ {type(e).__name__}: {e}")

print("\n" + "=" * 70)
print("TESTING MEETING ENGINE V2")
print("=" * 70)

# Test 3: AquaScience meeting
print("\n3. AquaScience — Meeting Page Render")
try:
    meeting_html = meeting_engine.render('aquascience', '2026-03-30', 'discovery')
    print(f"   ✅ Meeting page rendered: {len(meeting_html)} chars")
except Exception as e:
    print(f"   ⚠️ {type(e).__name__}: {e}")

# Test 4: Springer Floor meeting
print("\n4. Springer Floor — Meeting Page Render")
try:
    meeting_html = meeting_engine.render('springer_floor', '2026-03-30', 'discovery')
    print(f"   ✅ Meeting page rendered: {len(meeting_html)} chars")
except Exception as e:
    print(f"   ⚠️ {type(e).__name__}: {e}")

print("\n" + "=" * 70)
print("✅ TESTS COMPLETE")
print("=" * 70)
