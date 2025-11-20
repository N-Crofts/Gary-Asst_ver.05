# Gary-Asst Microsoft Graph API Testing

This directory contains test scripts to verify Microsoft Graph API integration with the provided credentials.

## Environment Setup

First, create a `.env` file with the provided credentials:

```bash
# Copy the provided values into .env (using canonical variable names)
AZURE_TENANT_ID=156ac674-e455-4115-8c54-a0f13eec48c7
AZURE_CLIENT_ID=9a129d47-0d4e-4f0d-9c3d-9974a50dcf72
AZURE_CLIENT_SECRET=<secret from Tabush>
MS_CALENDAR_USER=sorum.crofts@rpck.com
MS_SENDER_USER=gary-asst@rpck.com
```

## Test Options

### Option 1: Curl Script (Quick)

```bash
# Make the script executable
chmod +x test-graph-curl.sh

# Run the test
./test-graph-curl.sh
```

### Option 2: Node.js Script (Comprehensive)

```bash
# Install dependencies
npm install node-fetch dotenv

# Run the test
node graph-test.js
```

## Expected Results

### ✅ Success Criteria

1. **Calendar Read Test**:
   - HTTP 200 response
   - JSON list of events returned
   - Shows up to 5 events for the calendar user (`MS_CALENDAR_USER`)

2. **Email Send Test**:
   - HTTP 202 (Accepted) response
   - Email arrives in the calendar user's inbox
   - Message appears in the sender user's (`MS_SENDER_USER`) Sent Items

### ❌ Common Issues & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `401 invalid_client / AADSTS7000215` | Bad `AZURE_CLIENT_SECRET` | Re-paste exact "Value" from Tabush |
| `401 unauthorized_client / AADSTS700016` | Wrong `AZURE_CLIENT_ID` or app not found | Verify client ID in Azure Portal |
| `403 Insufficient privileges` | Missing admin consent | Verify Application permissions in Azure Portal |
| `403 Access is denied` (calendar) | Exchange Application Access Policy mismatch | Ask Tabush to re-check policy bindings |
| `404 Mailbox not found` | Typo in user principal | Ensure exact email addresses |
| `sendMail 403` | Missing send policy | Verify Mail.Send Application permission |

## Troubleshooting

If tests fail:

1. **Verify credentials** in Azure Portal
2. **Check admin consent** for Application permissions
3. **Confirm Exchange policies** match the test user
4. **Validate email addresses** are exact matches

## Next Steps

Once both tests pass:
- ✅ Auth + permissions are fully verified
- ✅ Ready for production Graph API integration
- ✅ Calendar read and email send functionality confirmed
