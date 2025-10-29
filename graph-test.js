import fetch from "node-fetch"; // Node 18+ has global fetch; keep for compatibility
import dotenv from "dotenv";
dotenv.config();

const {
  MS_TENANT_ID,
  MS_CLIENT_ID,
  MS_CLIENT_SECRET,
  MS_USER_EMAIL,
} = process.env;

const tokenEndpoint = `https://login.microsoftonline.com/${MS_TENANT_ID}/oauth2/v2.0/token`;

async function getToken() {
  const body = new URLSearchParams({
    client_id: MS_CLIENT_ID,
    client_secret: MS_CLIENT_SECRET,
    grant_type: "client_credentials",
    scope: "https://graph.microsoft.com/.default",
  });

  const res = await fetch(tokenEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Token error ${res.status}: ${text}`);
  }
  const json = await res.json();
  return json.access_token;
}

async function graphGet(url, token) {
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`GET ${url} -> ${res.status}: ${text}`);
  }
  return res.json();
}

async function graphPost(url, token, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok && res.status !== 202) {
    const text = await res.text();
    throw new Error(`POST ${url} -> ${res.status}: ${text}`);
  }
  return res.status; // 202 expected
}

async function main() {
  console.log("🔐 Getting app-only token…");
  const token = await getToken();
  console.log("✅ Token acquired.");

  // 1) Calendar read
  const eventsUrl = `https://graph.microsoft.com/v1.0/users/${encodeURIComponent(MS_USER_EMAIL)}/events?$top=5`;
  console.log(`📅 Reading events for ${MS_USER_EMAIL}…`);
  const events = await graphGet(eventsUrl, token);
  console.log(`✅ Got ${events.value?.length ?? 0} events`);
  (events.value || []).forEach((e, i) => {
    console.log(
      `   ${i + 1}. ${e.subject || "(no subject)"} | ${e.start?.dateTime} -> ${e.end?.dateTime}`
    );
  });

  // 2) Send mail
  const sendUrl = `https://graph.microsoft.com/v1.0/users/${encodeURIComponent("gary-asst@rpck.com")}/sendMail`;
  const mail = {
    message: {
      subject: "Gary-Asst Graph test",
      body: { contentType: "Text", content: "This is a Graph Mail.Send (Application) test." },
      toRecipients: [{ emailAddress: { address: MS_USER_EMAIL } }],
    },
    saveToSentItems: true,
  };
  console.log("📧 Sending test email from gary-asst@rpck.com…");
  const status = await graphPost(sendUrl, token, mail);
  console.log(`✅ sendMail returned HTTP ${status} (202 expected).`);

  console.log("");
  console.log("🎉 All tests completed successfully!");
  console.log("   - Calendar read: ✅");
  console.log("   - Email send: ✅");
  console.log("");
  console.log("📋 Next steps:");
  console.log("   1. Check Sorum's inbox for the test email");
  console.log("   2. Check gary-asst@rpck.com Sent Items for the sent message");
  console.log("   3. Verify auth + permissions are fully working");
}

main().catch((err) => {
  console.error("❌ Test failed:", err.message);
  process.exit(1);
});
