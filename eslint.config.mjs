import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTypeScript,
  globalIgnores([
    ".next/**",
    "dist/**",
    "out/**",
    "build/**",
    "app/_sites-preview/**",
    "backend/**",
    "db/**",
    "examples/**",
    "drizzle/**",
    "next-env.d.ts",
  ]),
]);
