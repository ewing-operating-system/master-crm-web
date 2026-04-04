#!/usr/bin/env python3
"""
Build debbie-buyers-manifest.json and debbie-buyer-research.json from per-buyer JSONs.

Run this after a batch of traced_buyer_run.py calls completes (all parallel runs done).
It globs public/data/debbie-research-*.json, reads each file, and writes:
  - public/data/debbie-buyers-manifest.json  (sorted by -fit_score, then name)
  - public/data/debbie-buyer-research.json   (combined, with total_buyers = actual count)

Does NOT do git operations — commit and deploy manually after verifying output.

Usage:
  python3 scripts/build_debbie_manifest.py
  python3 scripts/build_debbie_manifest.py --company "HR.com Ltd"
"""

import argparse
import glob
import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
PUBLIC_DATA_DIR = os.path.join(REPO_ROOT, 'public', 'data')


def main():
    parser = argparse.ArgumentParser(description='Build Debbie manifest from per-buyer JSONs')
    parser.add_argument('--company', default='HR.com Ltd',
                        help='Company name for combined JSON header (default: HR.com Ltd)')
    args = parser.parse_args()

    pattern = os.path.join(PUBLIC_DATA_DIR, 'debbie-research-*.json')
    per_buyer_files = sorted(glob.glob(pattern))

    if not per_buyer_files:
        print(f"No files matched: {pattern}")
        return

    print(f"Found {len(per_buyer_files)} per-buyer files:")
    for f in per_buyer_files:
        print(f"  {os.path.basename(f)}")

    manifest = []
    buyers_combined = {}
    errors = []

    for fpath in per_buyer_files:
        try:
            with open(fpath) as f:
                data = json.load(f)
        except Exception as e:
            errors.append(f"  ERROR reading {os.path.basename(fpath)}: {e}")
            continue

        slug = data.get('buyer_slug', '')
        name = data.get('buyer_name', '')

        if not slug or not name:
            errors.append(f"  SKIP {os.path.basename(fpath)}: missing buyer_name or buyer_slug")
            continue

        # Extract manifest fields
        manifest.append({
            "name": name,
            "slug": slug,
            "fit_score": data.get('fit_score', 0),
            "buyer_type": data.get('buyer_type', ''),
            "buyer_city": data.get('buyer_city', ''),
            "buyer_state": data.get('buyer_state', ''),
            "logo_domain": data.get('logo_domain', ''),
            "ticker": data.get('ticker', ''),
        })

        buyers_combined[slug] = data

    if errors:
        print("\nWarnings:")
        for e in errors:
            print(e)

    # Sort manifest: -fit_score, then name
    manifest.sort(key=lambda m: (-m.get('fit_score', 0), m.get('name', '')))

    # Write manifest
    manifest_path = os.path.join(PUBLIC_DATA_DIR, 'debbie-buyers-manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"\nWrote manifest ({len(manifest)} buyers): {manifest_path}")

    # Write combined
    combined = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "company": args.company,
        "total_buyers": len(buyers_combined),
        "buyers": buyers_combined,
    }
    combined_path = os.path.join(PUBLIC_DATA_DIR, 'debbie-buyer-research.json')
    with open(combined_path, 'w') as f:
        json.dump(combined, f, indent=2)
    print(f"Wrote combined  ({len(buyers_combined)} buyers): {combined_path}")

    print("\nManifest entries:")
    for m in manifest:
        print(f"  {m['fit_score']:2d}  {m['name']:<30s}  {m['slug']}")


if __name__ == '__main__':
    main()
