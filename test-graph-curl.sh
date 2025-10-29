#!/bin/bash

# Microsoft Graph API Test Script (curl)
# Test calendar read and email send functionality

# Set environment variables (replace with actual values)
export MS_TENANT_ID="156ac674-e455-4115-8c54-a0f13eec48c7"
export MS_CLIENT_ID="9a129d47-0d4e-4f0d-9c3d-9974a50dcf72"
export MS_CLIENT_SECRET="<secret from Tabush>"
export MS_USER_EMAIL="sorum.crofts@rpck.com"

echo "🔐 Getting access token..."
TOKEN=$(curl -s \
  -X POST "https://login.microsoftonline.com/$MS_TENANT_ID/oauth2/v2.0/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=$MS_CLIENT_ID&client_secret=$MS_CLIENT_SECRET&grant_type=client_credentials&scope=https%3A%2F%2Fgraph.microsoft.com%2F.default" \
  | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
    echo "❌ Failed to get access token"
    exit 1
fi

echo "✅ Token acquired successfully"

echo ""
echo "📅 Testing calendar read (top 5 events for $MS_USER_EMAIL)..."
curl -i -X GET "https://graph.microsoft.com/v1.0/users/$MS_USER_EMAIL/events?\$top=5" \
  -H "Authorization: Bearer $TOKEN"

echo ""
echo ""
echo "📧 Testing email send (as gary-asst@rpck.com)..."
curl -i -X POST "https://graph.microsoft.com/v1.0/users/gary-asst@rpck.com/sendMail" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "subject": "Gary-Asst Graph test",
      "body": { "contentType": "Text", "content": "This is a Graph Mail.Send (Application) test." },
      "toRecipients": [{ "emailAddress": { "address": "'"$MS_USER_EMAIL"'" } }]
    },
    "saveToSentItems": true
  }'

echo ""
echo "✅ Test completed. Check the responses above for success indicators:"
echo "   - Calendar: HTTP 200 with JSON list of events"
echo "   - Send: HTTP 202 (Accepted)"
