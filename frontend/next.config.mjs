import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: __dirname
  },
  // En Vercel: NEXT_PUBLIC_API_URL=/api y BACKEND_URL=https://<api>. El navegador
  // habla solo con el dominio de Vercel, así las cookies de sesión son first-party.
  async rewrites() {
    const backend = process.env.BACKEND_URL?.replace(/\/$/, '');
    return backend ? [{ source: '/api/:path*', destination: `${backend}/:path*` }] : [];
  }
};

export default nextConfig;
