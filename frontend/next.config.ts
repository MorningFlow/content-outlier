import type { NextConfig } from "next";

const API_URL = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const apiHostname = (() => {
  try { return new URL(API_URL).hostname; } catch { return "localhost"; }
})();

const nextConfig: NextConfig = {
  output: "standalone",
  images: {
    // Allow Next.js <Image> to serve thumbnails from the FastAPI media server
    remotePatterns: [
      {
        protocol: "http",
        hostname: apiHostname,
      },
      {
        protocol: "https",
        hostname: apiHostname,
      },
    ],
  },

  // In dev: proxy /api/* → FastAPI so you avoid CORS entirely.
  // In production on Vercel, set NEXT_PUBLIC_API_URL to your server domain.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_URL}/:path*`,
      },
      {
        source: "/media/:path*",
        destination: `${API_URL}/media/:path*`,
      },
    ];
  },
};

export default nextConfig;
