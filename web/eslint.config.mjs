import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    // No px/em/rem literals in class names: use a named length from the @theme block in
    // app/globals.css (text-meta, h-control, max-w-pitch, max-compact:). Generated shadcn files
    // in components/ui are exempt.
    files: ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}", "lib/**/*.{ts,tsx}"],
    ignores: ["components/ui/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "Literal[value=/\\[[^\\]\\s]*\\d(px|em|rem)[^\\]\\s]*\\]/]",
          message: "Use a named length from the @theme block in app/globals.css, not a px/em/rem literal.",
        },
        {
          selector: "TemplateElement[value.raw=/\\[[^\\]\\s]*\\d(px|em|rem)[^\\]\\s]*\\]/]",
          message: "Use a named length from the @theme block in app/globals.css, not a px/em/rem literal.",
        },
      ],
    },
  },
]);

export default eslintConfig;
