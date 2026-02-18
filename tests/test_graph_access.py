#!/usr/bin/env python3
"""
Test script to validate Microsoft Graph app-only access.

This script tests:
1. Calendar read access for chintan.panchal@rpck.com
2. Email send capability for gary-asst@rpck.com

Run with: python tests/test_graph_access.py
"""
import os
import sys
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def get_access_token() -> str:
    """
    Get Microsoft Graph access token using client credentials flow.
    
    Uses the same authentication flow as production code.
    
    Returns:
        Access token string
        
    Raises:
        SystemExit: If authentication fails
    """
    # Support both MS_* and AZURE_* naming conventions (same as production code)
    tenant_id = (os.getenv("MS_TENANT_ID") or os.getenv("AZURE_TENANT_ID") or "").strip()
    client_id = (os.getenv("MS_CLIENT_ID") or os.getenv("AZURE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("MS_CLIENT_SECRET") or os.getenv("AZURE_CLIENT_SECRET") or "").strip()
    
    if not all([tenant_id, client_id, client_secret]):
        print("ERROR: Missing required environment variables:")
        if not tenant_id:
            print("  - MS_TENANT_ID or AZURE_TENANT_ID")
        if not client_id:
            print("  - MS_CLIENT_ID or AZURE_CLIENT_ID")
        if not client_secret:
            print("  - MS_CLIENT_SECRET or AZURE_CLIENT_SECRET")
        sys.exit(1)
    
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials"
    }
    
    print(f"Requesting access token from: {token_url}")
    print(f"Client ID: {client_id[:8]}...{client_id[-8:]}")
    
    try:
        response = requests.post(token_url, data=data, timeout=10)
        
        if response.status_code != 200:
            print(f"\nERROR: Token request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            sys.exit(1)
        
        token_data = response.json()
        access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        
        print(f"[OK] Access token acquired (expires in {expires_in} seconds)")
        return access_token
        
    except requests.exceptions.RequestException as e:
        print(f"\nERROR: Failed to request access token: {e}")
        sys.exit(1)


def test_calendar_access(access_token: str) -> bool:
    """
    Test 1: Read Chintan's calendar events.
    
    Args:
        access_token: Microsoft Graph access token
        
    Returns:
        True if test passed, False otherwise
    """
    print("\n" + "-" * 50)
    print("TEST 1 — CALENDAR ACCESS")
    print("-" * 50)
    
    url = "https://graph.microsoft.com/v1.0/users/chintan.panchal@rpck.com/events"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    params = {
        "$top": 5
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        print(f"\nStatus: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            events = data.get("value", [])
            event_count = len(events)
            
            print(f"Events found: {event_count}")
            
            if event_count > 0:
                for i, event in enumerate(events, 1):
                    subject = event.get("subject", "No subject")
                    start = event.get("start", {})
                    start_time = start.get("dateTime", "No start time")
                    print(f"\nEvent {i}:")
                    print(f"  Subject: {subject}")
                    print(f"  Start: {start_time}")
            
            return True
        else:
            print(f"\nResponse body: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"\nERROR: Request failed: {e}")
        return False


def test_send_email(access_token: str) -> bool:
    """
    Test 2: Send email as Gary-Asst.
    
    Args:
        access_token: Microsoft Graph access token
        
    Returns:
        True if test passed, False otherwise
    """
    print("\n" + "-" * 50)
    print("TEST 2 — SEND EMAIL")
    print("-" * 50)
    
    url = "https://graph.microsoft.com/v1.0/users/gary-asst@rpck.com/sendMail"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    body = {
        "message": {
            "subject": "Gary-Asst test email",
            "body": {
                "contentType": "Text",
                "content": "This is a test email from Gary-Asst validating Microsoft Graph Mail.Send permission."
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": "svpanchal@gmail.com"
                    }
                }
            ]
        },
        "saveToSentItems": True
    }
    
    try:
        response = requests.post(url, headers=headers, json=body, timeout=15)
        
        print(f"\nStatus: {response.status_code}")
        
        if response.status_code == 202:
            print("Email sent successfully")
            return True
        else:
            print(f"\nResponse body: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"\nERROR: Request failed: {e}")
        return False


def main():
    """Main test execution."""
    print("=" * 50)
    print("Microsoft Graph Access Validation")
    print("=" * 50)
    print("\nThis script validates app-only Microsoft Graph access")
    print("for Gary-Asst using client credentials authentication.\n")
    
    # Get access token
    access_token = get_access_token()
    
    # Run tests
    test1_passed = test_calendar_access(access_token)
    test2_passed = test_send_email(access_token)
    
    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    print(f"Test 1 (Calendar Access): {'PASSED' if test1_passed else 'FAILED'}")
    print(f"Test 2 (Send Email): {'PASSED' if test2_passed else 'FAILED'}")
    
    if test1_passed and test2_passed:
        print("\n[OK] All tests passed! Microsoft Graph access is configured correctly.")
        sys.exit(0)
    else:
        print("\n[FAILED] Some tests failed. Please check the error messages above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
