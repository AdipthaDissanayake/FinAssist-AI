import { OAuth2Client } from "google-auth-library";

const clientId = process.argv[2];
const chunks = [];

process.stdin.on("data", (chunk) => chunks.push(chunk));
process.stdin.on("end", async () => {
  try {
    const idToken = Buffer.concat(chunks).toString("utf8").trim();
    if (!clientId || !idToken) throw new Error("Missing Google credentials");

    const ticket = await new OAuth2Client(clientId).verifyIdToken({
      idToken,
      audience: clientId,
    });
    const payload = ticket.getPayload();
    if (!payload?.sub || !payload.email || payload.email_verified !== true) {
      throw new Error("Google account email is not verified");
    }

    process.stdout.write(JSON.stringify({
      sub: payload.sub,
      email: payload.email,
      email_verified: payload.email_verified,
      given_name: payload.given_name || "",
      family_name: payload.family_name || "",
      name: payload.name || "",
    }));
  } catch {
    process.exitCode = 1;
  }
});
