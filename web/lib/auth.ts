import NextAuth from "next-auth";
import GitHub from "next-auth/providers/github";
import Google from "next-auth/providers/google";
import Email from "next-auth/providers/email";
import { mintApiToken } from "./api-token";
import "next-auth/jwt";

// Extend the session type to include apiToken
declare module "next-auth" {
  interface Session {
    apiToken?: string;
  }
}

// Extend the JWT type to include apiToken and other custom fields
declare module "next-auth/jwt" {
  interface JWT {
    apiToken?: string;
    accessToken?: string;
    provider?: string;
  }
}

const providers = [];

if (process.env.AUTH_GITHUB_ID && process.env.AUTH_GITHUB_SECRET) {
  providers.push(
    GitHub({
      clientId: process.env.AUTH_GITHUB_ID,
      clientSecret: process.env.AUTH_GITHUB_SECRET,
    })
  );
}

if (process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET) {
  providers.push(
    Google({
      clientId: process.env.AUTH_GOOGLE_ID,
      clientSecret: process.env.AUTH_GOOGLE_SECRET,
    })
  );
}

if (process.env.AUTH_EMAIL_SERVER && process.env.AUTH_EMAIL_FROM) {
  providers.push(
    Email({
      server: process.env.AUTH_EMAIL_SERVER,
      from: process.env.AUTH_EMAIL_FROM,
    })
  );
}

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers,
  session: {
    strategy: "jwt",
  },
  callbacks: {
    async jwt({ token, account, profile, user, trigger, session }) {
      // Initial sign-in: account and user are available
      if (account && user) {
        token.sub = user.id;
        token.email = user.email;
        token.name = user.name;
        token.picture = user.image;
        token.accessToken = account.access_token;
        token.provider = account.provider;
      }

      // On session update (e.g., after sign-in or manual update)
      if (trigger === "update" && session) {
        token.name = session.user?.name ?? token.name;
        token.picture = session.user?.image ?? token.picture;
      }

      // Mint API token for the server (HS256, same secret as API)
      // This runs on every JWT callback so the token is always fresh
      if (token.sub && token.email) {
        const apiToken = await mintApiToken({
          sub: token.sub,
          email: token.email,
          name: token.name,
          picture: token.picture,
        });
        token.apiToken = apiToken;
      }

      return token;
    },
    async session({ session, token }) {
      session.user = {
        id: token.sub!,
        email: token.email!,
        name: token.name,
        image: token.picture,
        emailVerified: null,
      };
      // Expose the API token to client components
      session.apiToken = token.apiToken;
      return session;
    },
  },
  pages: {
    signIn: "/auth/signin",
    error: "/auth/error",
  },
  secret: process.env.AUTH_SECRET,
  cookies: {
    sessionToken: {
      name: "metis_session",
      options: {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        path: "/",
      },
    },
  },
});