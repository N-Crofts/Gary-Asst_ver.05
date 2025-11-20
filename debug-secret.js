import dotenv from "dotenv";
dotenv.config();

const secret = process.env.AZURE_CLIENT_SECRET || "";
console.log("Secret length:", secret.length);
console.log("Has leading/trailing whitespace:", secret !== secret.trim());
console.log("Starts with quote:", secret.startsWith('"') || secret.startsWith("'"));
console.log("Ends with quote:", secret.endsWith('"') || secret.endsWith("'"));
console.log("First 3 chars:", secret.substring(0, 3));
console.log("Last 3 chars:", secret.substring(Math.max(0, secret.length - 3)));


