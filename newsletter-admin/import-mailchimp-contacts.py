#!/usr/bin/env python3
"""
Import contacts from Mailchimp CSV export to DynamoDB

Usage:
    python3 import-mailchimp-contacts.py /path/to/export/directory [--include-unsubscribed]

The script will import:
- subscribed_email_*.csv → status: active
- unsubscribed_email_*.csv → status: unsubscribed (if --include-unsubscribed flag is set)
- cleaned_email_*.csv → SKIPPED (invalid emails)
"""

import csv
import sys
import os
import boto3
from datetime import datetime
from pathlib import Path

# Configuration
TABLE_NAME = 'yallabalagan-newsletter-contacts'
REGION = 'eu-north-1'

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table(TABLE_NAME)


def parse_tags(tags_str):
    """Parse Mailchimp tags string into list"""
    if not tags_str or tags_str.strip() == '':
        return []

    # Tags are in format: "tag1","tag2","tag3"
    # Remove outer quotes and split
    tags_str = tags_str.strip().strip('"')
    if not tags_str:
        return []

    # Split by "," and clean each tag
    tags = []
    for tag in tags_str.split('","'):
        tag = tag.strip().strip('"').lower()
        if tag:
            tags.append(tag)

    return tags


def parse_timestamp(time_str):
    """Parse Mailchimp timestamp to unix timestamp"""
    if not time_str or time_str.strip() == '':
        return int(datetime.utcnow().timestamp())

    try:
        # Format: "2020-01-30 09:51:27"
        dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
        return int(dt.timestamp())
    except:
        return int(datetime.utcnow().timestamp())


def import_csv_file(csv_path, status):
    """Import contacts from a CSV file"""
    print(f"\n📄 Processing: {os.path.basename(csv_path)}")
    print(f"   Status: {status}")

    contacts_added = 0
    contacts_skipped = 0
    contacts_errors = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader, 1):
            try:
                email = row.get('Email Address', '').strip().lower()

                if not email:
                    contacts_skipped += 1
                    continue

                # Build name
                first_name = row.get('First Name', '').strip()
                last_name = row.get('Last Name', '').strip()
                name = f"{first_name} {last_name}".strip() or email.split('@')[0]

                # Parse tags
                tags = parse_tags(row.get('TAGS', ''))

                # Get subscription time
                confirm_time = row.get('CONFIRM_TIME', '')
                created_at = parse_timestamp(confirm_time)

                # Create contact record
                contact = {
                    'email': email,
                    'name': name,
                    'tags': tags,
                    'status': status,
                    'created_at': created_at,
                }

                # Add optional fields
                if row.get('City'):
                    contact['city'] = row['City'].strip()
                if row.get('REGION'):
                    contact['region'] = row['REGION'].strip()

                # Save to DynamoDB
                table.put_item(Item=contact)
                contacts_added += 1

                # Progress indicator
                if i % 100 == 0:
                    print(f"   Processed {i} rows... ({contacts_added} added, {contacts_skipped} skipped)")

            except Exception as e:
                print(f"   ❌ Error processing row {i}: {e}")
                contacts_errors += 1
                if contacts_errors > 10:
                    print("   ⚠️  Too many errors, stopping...")
                    break

    print(f"   ✅ Done: {contacts_added} added, {contacts_skipped} skipped, {contacts_errors} errors")
    return contacts_added, contacts_skipped, contacts_errors


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 import-mailchimp-contacts.py /path/to/export/directory [--include-unsubscribed]")
        print("\nExample:")
        print("  python3 import-mailchimp-contacts.py /Users/levgoldort/Downloads/audience_export_ed345947d1")
        print("  python3 import-mailchimp-contacts.py /Users/levgoldort/Downloads/audience_export_ed345947d1 --include-unsubscribed")
        sys.exit(1)

    export_dir = sys.argv[1]
    include_unsubscribed = '--include-unsubscribed' in sys.argv

    if not os.path.isdir(export_dir):
        print(f"❌ Error: Directory not found: {export_dir}")
        sys.exit(1)

    print("="*60)
    print("  Mailchimp → DynamoDB Contact Import")
    print("="*60)
    print(f"\nExport directory: {export_dir}")
    print(f"DynamoDB table: {TABLE_NAME}")
    print(f"Region: {REGION}\n")

    # Find CSV files
    subscribed_file = None
    unsubscribed_file = None

    for file in os.listdir(export_dir):
        if file.startswith('subscribed_') and file.endswith('.csv'):
            subscribed_file = os.path.join(export_dir, file)
        elif file.startswith('unsubscribed_') and file.endswith('.csv'):
            unsubscribed_file = os.path.join(export_dir, file)

    total_added = 0
    total_skipped = 0
    total_errors = 0

    # Import subscribed contacts
    if subscribed_file:
        added, skipped, errors = import_csv_file(subscribed_file, 'active')
        total_added += added
        total_skipped += skipped
        total_errors += errors
    else:
        print("⚠️  No subscribed file found")

    # Import unsubscribed contacts
    if unsubscribed_file and include_unsubscribed:
        added, skipped, errors = import_csv_file(unsubscribed_file, 'unsubscribed')
        total_added += added
        total_skipped += skipped
        total_errors += errors
    elif unsubscribed_file and not include_unsubscribed:
        print(f"\n⏭️  Skipping unsubscribed contacts (use --include-unsubscribed to import them)")

    print("\n" + "="*60)
    print("  Import Complete!")
    print("="*60)
    print(f"\n📊 Summary:")
    print(f"   Total added: {total_added}")
    print(f"   Total skipped: {total_skipped}")
    print(f"   Total errors: {total_errors}")
    print()

    # Show sample contacts
    print("📋 Sample contacts from database:")
    response = table.scan(Limit=5)
    for contact in response.get('Items', []):
        tags_str = ', '.join(contact.get('tags', [])) or 'no tags'
        print(f"   • {contact['email']} - {contact['name']} ({contact['status']}) - tags: {tags_str}")

    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Import cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
