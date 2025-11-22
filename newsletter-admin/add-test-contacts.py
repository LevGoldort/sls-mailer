#!/usr/bin/env python3
"""
Script to add test contacts to DynamoDB for newsletter system testing

Usage:
    python3 add-test-contacts.py

Requirements:
    pip install boto3
"""

import boto3
import time
from datetime import datetime

# Configuration
TABLE_NAME = 'yallabalagan-newsletter-contacts'
REGION = 'eu-north-1'

# Test contacts data
TEST_CONTACTS = [
    {
        'email': 'test1@example.com',
        'name': 'Alice Johnson',
        'tags': ['stand-up', 'tel-aviv'],
        'status': 'active',
    },
    {
        'email': 'test2@example.com',
        'name': 'Bob Smith',
        'tags': ['vip', 'tel-aviv'],
        'status': 'active',
    },
    {
        'email': 'test3@example.com',
        'name': 'Charlie Brown',
        'tags': ['stand-up', 'improv'],
        'status': 'active',
    },
    {
        'email': 'test4@example.com',
        'name': 'Diana Prince',
        'tags': ['vip', 'improv', 'tel-aviv'],
        'status': 'active',
    },
    {
        'email': 'test5@example.com',
        'name': 'Eve Williams',
        'tags': ['stand-up'],
        'status': 'unsubscribed',  # This one is unsubscribed
    },
]


def add_contacts():
    """Add test contacts to DynamoDB"""

    print(f"Connecting to DynamoDB table: {TABLE_NAME}")
    print(f"Region: {REGION}\n")

    # Initialize DynamoDB client
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    # Add timestamp
    created_at = int(datetime.utcnow().timestamp())

    print("Adding test contacts...\n")

    for i, contact in enumerate(TEST_CONTACTS, 1):
        try:
            # Add created_at timestamp
            contact['created_at'] = created_at + i

            # Add to DynamoDB
            table.put_item(Item=contact)

            status_icon = "✅" if contact['status'] == 'active' else "❌"
            print(f"{status_icon} {i}. {contact['name']} ({contact['email']})")
            print(f"   Tags: {', '.join(contact['tags'])}")
            print(f"   Status: {contact['status']}\n")

            # Small delay to avoid throttling
            time.sleep(0.1)

        except Exception as e:
            print(f"❌ Error adding {contact['email']}: {str(e)}\n")

    print("=" * 60)
    print("✅ Test contacts added successfully!")
    print("\nSummary:")
    print(f"- Total contacts: {len(TEST_CONTACTS)}")
    print(f"- Active: {sum(1 for c in TEST_CONTACTS if c['status'] == 'active')}")
    print(f"- Unsubscribed: {sum(1 for c in TEST_CONTACTS if c['status'] == 'unsubscribed')}")
    print("\nAvailable tags:", set(tag for c in TEST_CONTACTS for tag in c['tags']))
    print("\nYou can now test the newsletter system!")


if __name__ == '__main__':
    try:
        add_contacts()
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print("\nMake sure:")
        print("1. AWS CLI is configured (aws configure)")
        print("2. boto3 is installed (pip install boto3)")
        print(f"3. DynamoDB table '{TABLE_NAME}' exists in {REGION}")
        print("4. You have permissions to write to the table")
