import path from "node:path";
import { fileURLToPath } from "node:url";

import { FlatCompat } from "@eslint/eslintrc";


const root = path.dirname(fileURLToPath(import.meta.url));
const compat = new FlatCompat({ baseDirectory: root });

export default [
  {
    ignores: [
      "**/.next/**",
      "**/.next-dev/**",
      "**/node_modules/**",
      "**/next-env.d.ts",
      "packages/contracts/src/generated.ts",
      "tmp/**",
      "output/**"
    ]
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      "@next/next/no-html-link-for-pages": "off",
      "@next/next/no-img-element": "off"
    }
  }
];
