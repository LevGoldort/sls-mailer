#!/usr/bin/env python3
"""
Quick script to add specific contacts to newsletter
"""

import boto3
from datetime import datetime

# Configuration
TABLE_NAME = 'yallabalagan-newsletter-contacts'
REGION = 'eu-north-1'

# Contacts to add
contacts = [
    {
        'email': 'user@example.com',
        'name': 'Example User',
        'tags': ['stand-up', 'tel-aviv', 'vip'],
        'status': 'active',
    },
    {
        'email': 'user2@example.com',
        'name': 'Another User',
        'tags': ['stand-up', 'tel-aviv'],
        'status': 'active',
    },
    {
        'email': 'test-improv@example.com',
        'name': 'Improv Fan',
        'tags': ['improv', 'tel-aviv'],
        'status': 'active',
    },
    {
        'email': 'test-vip-only@example.com',
        'name': 'VIP Only',
        'tags': ['vip'],
        'status': 'active',
    },
    {
        'email': 'test-all-tags@example.com',
        'name': 'All Tags',
        'tags': ['stand-up', 'improv', 'tel-aviv', 'vip'],
        'status': 'active',
    }
]

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table(TABLE_NAME)

print(f"Adding {len(contacts)} contacts to {TABLE_NAME}...\n")

for contact in contacts:
    # Add timestamp
    contact['created_at'] = int(datetime.utcnow().timestamp())

    # Add to DynamoDB
    try:
        table.put_item(Item=contact)
        print(f"✅ Added: {contact['name']} ({contact['email']})")
        print(f"   Tags: {', '.join(contact['tags'])}\n")
    except Exception as e:
        print(f"❌ Error adding {contact['email']}: {e}\n")

print("✅ Done!")
