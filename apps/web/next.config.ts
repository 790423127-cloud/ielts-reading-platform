import path from "node:path";
import type { NextConfig } from "next";

const standaloneBuild =
  process.env.NEXT_STANDALONE_BUILD === "1" ||
  (process.platform !== "win32" && process.env.NEXT_STANDALONE_BUILD !== "0");

const nextConfig: NextConfig = {
  poweredByHeader: false,
  compress: true,
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : ".next",
  output: standaloneBuild ? "standalone" : undefined,
  outputFileTracingRoot: path.resolve(__dirname, "../..")
};

export default nextConfig;
