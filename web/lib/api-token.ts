export interface MintApiTokenInput {
  sub: string;
  email: string;
  name?: string | null;
  picture?: string | null;
}

async function base64UrlEncode(buffer: Uint8Array): Promise<string> {
  let str = "";
  for (let i = 0; i < buffer.length; i++) {
    str += String.fromCharCode(buffer[i]);
  }
  return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

async function signHS256(payload: string, secret: string): Promise<string> {
  const encoder = new TextEncoder();
  const keyData = encoder.encode(secret);
  const key = await crypto.subtle.importKey(
    "raw",
    keyData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(payload));
  return base64UrlEncode(new Uint8Array(signature));
}

export async function mintApiToken(input: MintApiTokenInput): Promise<string> {
  const secret = process.env.AUTH_JWT_SECRET!;
  const audience = process.env.AUTH_JWT_AUDIENCE || "metis-api";
  const now = Math.floor(Date.now() / 1000);
  const exp = now + 5 * 60; // 5 minutes

  const header = { alg: "HS256", typ: "JWT" };
  const payload = {
    sub: input.sub,
    email: input.email,
    name: input.name,
    picture: input.picture,
    aud: audience,
    iat: now,
    exp,
  };

  const encodedHeader = await base64UrlEncode(
    new TextEncoder().encode(JSON.stringify(header))
  );
  const encodedPayload = await base64UrlEncode(
    new TextEncoder().encode(JSON.stringify(payload))
  );
  const signingInput = `${encodedHeader}.${encodedPayload}`;
  const signature = await signHS256(signingInput, secret);

  return `${signingInput}.${signature}`;
}