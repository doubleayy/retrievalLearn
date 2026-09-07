import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // This app is the workspace root; without this Next walks up and finds
  // unrelated lockfiles in the home directory.
  outputFileTracingRoot: __dirname,
};

export default nextConfig;
