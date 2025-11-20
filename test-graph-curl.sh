#!/bin/bash

# Microsoft Graph API Test Script (curl)
# Test calendar read and email send functionality
# Uses canonical environment variable names

# Load environment variables from .env file (if present)
# Or set them directly here:
# export AZURE_TENANT_ID="156ac674-e455-4115-8c54-a0f13eec48c7"
# export AZURE_CLIENT_ID="9a129d47-0d4e-4f0d-9c3d-9974a50dcf72"
# export AZURE_CLIENT_SECRET="Gyi8QkDGX2DcHbon1PgmOz._mCdn3LHFRD.dvo"
# export MS_CALENDAR_USER="sorum.crofts@rpck.com"
# export MS_SENDER_USER="gary-asst@rpck.com"

echo "🔐 Getting access token..."
TOKEN=$(curl -s \
  -X POST "https://login.microsoftonline.com/$AZURE_TENANT_ID/oauth2/v2.0/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=$AZURE_CLIENT_ID&client_secret=$AZURE_CLIENT_SECRET&grant_type=client_credentials&scope=https%3A%2F%2Fgraph.microsoft.com%2F.default" \
  | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
    echo "❌ Failed to get access token"
    exit 1
fi

echo "✅ Token acquired successfully"

echo ""
echo "📅 Testing calendar read (top 5 events for $MS_CALENDAR_USER)..."
curl -i -X GET "https://graph.microsoft.com/v1.0/users/$MS_CALENDAR_USER/events?\$top=5" \
  -H "Authorization: Bearer $TOKEN"

echo ""
echo ""
echo "📧 Testing email send (as $MS_SENDER_USER)..."
curl -i -X POST "https://graph.microsoft.com/v1.0/users/$MS_SENDER_USER/sendMail" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "subject": "Gary-Asst Graph test",
      "body": { "contentType": "Text", "content": "Graph Mail.Send (Application) test." },
      "toRecipients": [{ "emailAddress": { "address": "'"$MS_CALENDAR_USER"'" } }]
    },
    "saveToSentItems": true
  }'

echo ""
echo "✅ Test completed. Check the responses above for success indicators:"
echo "   - Calendar: HTTP 200 with JSON list of events"
echo "   - Send: HTTP 202 (Accepted)"
