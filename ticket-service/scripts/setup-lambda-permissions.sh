#!/bin/bash
set -e

echo "🔐 Setting up Lambda permissions..."

ROLE_NAME="YallaBalagan-TicketService-Lambda-Role"

# 1. S3 permissions for site bucket
echo "📝 Adding S3 permissions..."
cat > /tmp/s3-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:GetObject"
      ],
      "Resource": [
        "arn:aws:s3:::yallabalagan-tickets-frontend",
        "arn:aws:s3:::yallabalagan-tickets-frontend/*"
      ]
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name S3-SiteRegenerator-Policy \
  --policy-document file:///tmp/s3-policy.json

# 2. Lambda invoke permissions
echo "📝 Adding Lambda invoke permissions..."
cat > /tmp/lambda-invoke-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:eu-north-1:982534389905:function:yallabalagan-site-regenerator"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name Lambda-Invoke-SiteRegenerator \
  --policy-document file:///tmp/lambda-invoke-policy.json

# Cleanup
rm /tmp/s3-policy.json /tmp/lambda-invoke-policy.json

echo "✅ Permissions configured!"
