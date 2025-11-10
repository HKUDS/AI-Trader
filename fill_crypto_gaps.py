#!/usr/bin/env python3
"""
Script to fill missing timeslots in crypto_hourly_merged.jsonl using Forward Fill methodology.
Missing gaps larger than 4 hours will be reported to the user.

Usage: python fill_crypto_gaps.py
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import sys

def load_crypto_data(input_file):
    """Load cryptocurrency data from JSONL file"""
    crypto_data = {}

    print(f"Loading data from {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f):
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                # Extract crypto symbol from Meta Data
                if 'Meta Data' in doc and '3. Digital Currency Name' in doc['Meta Data']:
                    crypto_name = doc['Meta Data']['3. Digital Currency Name']

                    # Find all Time Series data for this crypto
                    for key, value in doc.items():
                        if key.startswith('Time Series') and isinstance(value, dict):
                            crypto_data[crypto_name] = {
                                'metadata': doc.get('Meta Data', {}),
                                'time_series': dict(value)  # Convert to regular dict
                            }
                            break
            except Exception as e:
                print(f"Error parsing line {line_num}: {e}")
                continue

    print(f"Loaded data for {len(crypto_data)} cryptocurrencies")
    return crypto_data

def analyze_gaps(crypto_data):
    """Analyze gaps for each cryptocurrency"""
    gap_analysis = {}

    for crypto_name, data in crypto_data.items():
        time_series = data['time_series']
        if not time_series:
            continue

        # Parse and sort timestamps
        timestamps = sorted([datetime.strptime(ts, '%Y-%m-%d %H:%M:%S') for ts in time_series.keys()])

        # Find gaps
        gaps = []
        for i in range(1, len(timestamps)):
            diff = timestamps[i] - timestamps[i-1]
            if diff > timedelta(hours=1):
                missing_hours = (diff.total_seconds() // 3600) - 1
                gaps.append({
                    'start': timestamps[i-1],
                    'end': timestamps[i],
                    'missing_hours': missing_hours
                })

        gap_analysis[crypto_name] = {
            'total_gaps': len(gaps),
            'total_missing_hours': sum(g['missing_hours'] for g in gaps),
            'gaps': gaps,
            'data_points': len(timestamps)
        }

    return gap_analysis

def forward_fill_time_series(time_series_data, crypto_name):
    """Apply forward fill to missing timestamps"""
    if not time_series_data:
        return {}

    # Parse and sort existing timestamps
    existing_data = {}
    for ts_str, data in time_series_data.items():
        existing_data[datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')] = (ts_str, data)

    timestamps = sorted(existing_data.keys())
    if not timestamps:
        return {}

    # Determine the full range
    start_time = timestamps[0]
    end_time = timestamps[-1]

    # Generate complete timeline
    current_time = start_time
    filled_time_series = {}
    large_gaps = []

    # Keep track of the last known data point
    last_data = None
    last_timestamp = None

    while current_time <= end_time:
        current_str = current_time.strftime('%Y-%m-%d %H:%M:%S')

        if current_time in existing_data:
            # Use existing data
            ts_str, data = existing_data[current_time]
            filled_time_series[current_str] = data
            last_data = data
            last_timestamp = ts_str
        else:
            # Forward fill using last known data
            if last_data:
                filled_time_series[current_str] = last_data.copy()
            else:
                # No previous data available (shouldn't happen with proper data)
                print(f"Warning: No previous data available for {crypto_name} at {current_str}")

        current_time += timedelta(hours=1)

    # Check for large gaps in original data
    for i in range(1, len(timestamps)):
        diff = timestamps[i] - timestamps[i-1]
        if diff > timedelta(hours=5):  # More than 4 hours missing (since we count gaps between existing points)
            missing_hours = (diff.total_seconds() // 3600) - 1
            large_gaps.append({
                'start': timestamps[i-1].strftime('%Y-%m-%d %H:%M:%S'),
                'end': timestamps[i].strftime('%Y-%m-%d %H:%M:%S'),
                'missing_hours': missing_hours
            })

    return filled_time_series, large_gaps

def process_crypto_data(crypto_data, gap_analysis):
    """Process all cryptocurrency data with forward fill"""
    processed_data = {}
    all_large_gaps = {}

    for crypto_name, data in crypto_data.items():
        print(f"\nProcessing {crypto_name}...")

        # Apply forward fill
        filled_time_series, large_gaps = forward_fill_time_series(data['time_series'], crypto_name)

        # Update metadata to reflect the changes
        new_metadata = data['metadata'].copy()
        original_count = len(data['time_series'])
        filled_count = len(filled_time_series)

        # Update the "Last Refreshed" and "Output Size" in metadata
        new_metadata['4. Last Refreshed'] = max(filled_time_series.keys()) if filled_time_series else new_metadata.get('4. Last Refreshed')
        new_metadata['6. Output Size'] = 'Full size (filled)'

        processed_data[crypto_name] = {
            'metadata': new_metadata,
            'time_series': filled_time_series,
            'original_count': original_count,
            'filled_count': filled_count,
            'added_points': filled_count - original_count
        }

        if large_gaps:
            all_large_gaps[crypto_name] = large_gaps

        print(f"  Original data points: {original_count}")
        print(f"  After forward fill: {filled_count}")
        print(f"  Added {filled_count - original_count} data points")

        if large_gaps:
            print(f"  ⚠️  {len(large_gaps)} large gaps found (>4 hours):")
            for gap in large_gaps:
                print(f"    - {gap['start']} to {gap['end']} ({gap['missing_hours']} hours missing)")

    return processed_data, all_large_gaps

def write_filled_data(processed_data, output_file):
    """Write the filled data to new JSONL file"""
    print(f"\nWriting filled data to {output_file}...")

    with open(output_file, 'w', encoding='utf-8') as f:
        for crypto_name, data in processed_data.items():
            # Create the document structure
            doc = {
                "Meta Data": data['metadata'],
                "Time Series (60min)": data['time_series']
            }

            # Write as JSON line
            f.write(json.dumps(doc, ensure_ascii=False) + '\n')

    print(f"Successfully wrote {len(processed_data)} cryptocurrencies to {output_file}")

def main():
    """Main function to process crypto data gaps"""
    input_file = Path(__file__).parent / "data" / "crypto" / "crypto_hourly_merged.jsonl"
    output_file = Path(__file__).parent / "data" / "crypto" / "crypto_hourly_merged_filled.jsonl"

    if not input_file.exists():
        print(f"Error: Input file {input_file} does not exist!")
        sys.exit(1)

    print("=" * 60)
    print("CRYPTOCURRENCY DATA GAP FILLER")
    print("Forward Fill Methodology")
    print("=" * 60)

    # Load existing data
    crypto_data = load_crypto_data(input_file)

    # Analyze gaps before filling
    print("\nAnalyzing gaps before filling...")
    gap_analysis = analyze_gaps(crypto_data)

    print(f"\nGap Analysis Summary:")
    for crypto_name, analysis in gap_analysis.items():
        if analysis['total_gaps'] > 0:
            print(f"  {crypto_name}: {analysis['total_gaps']} gaps, {analysis['total_missing_hours']} hours missing")
        else:
            print(f"  {crypto_name}: No gaps")

    # Process with forward fill
    print("\n" + "=" * 60)
    print("APPLYING FORWARD FILL")
    print("=" * 60)

    processed_data, large_gaps = process_crypto_data(crypto_data, gap_analysis)

    # Report large gaps
    if large_gaps:
        print("\n" + "⚠️" * 20)
        print("LARGE GAPS WARNING (>4 hours)")
        print("⚠️" * 20)
        for crypto_name, gaps in large_gaps.items():
            print(f"\n{crypto_name}:")
            total_missing = sum(g['missing_hours'] for g in gaps)
            print(f"  Total missing hours: {total_missing}")
            for gap in gaps:
                print(f"    - {gap['start']} to {gap['end']} ({gap['missing_hours']} hours)")
    else:
        print("\n✅ No gaps larger than 4 hours found!")

    # Write filled data
    print("\n" + "=" * 60)
    write_filled_data(processed_data, output_file)

    # Final summary
    print("\n" + "=" * 60)
    print("PROCESSING COMPLETE")
    print("=" * 60)

    total_original = sum(data['original_count'] for data in processed_data.values())
    total_filled = sum(data['filled_count'] for data in processed_data.values())

    print(f"Total original data points: {total_original}")
    print(f"Total data points after filling: {total_filled}")
    print(f"Added {total_filled - total_original} data points")
    print(f"Output file: {output_file}")

    # Verify no gaps remaining
    print("\nVerifying no gaps remain...")
    # Reload the filled data and verify
    filled_crypto_data = load_crypto_data(output_file)
    filled_gap_analysis = analyze_gaps(filled_crypto_data)

    remaining_gaps = sum(analysis['total_gaps'] for analysis in filled_gap_analysis.values())
    if remaining_gaps == 0:
        print("✅ Success! No gaps remaining in the filled data.")
    else:
        print(f"⚠️  Warning: {remaining_gaps} gaps still remain.")

if __name__ == "__main__":
    main()