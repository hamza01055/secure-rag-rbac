/** @type {import('next').NextConfig} */
module.exports = {
  reactStrictMode: true,
  // The API URL is server-side only. It is deliberately not NEXT_PUBLIC_ —
  // the browser never calls the backend directly.
  env: { API_URL: process.env.API_URL },
};
