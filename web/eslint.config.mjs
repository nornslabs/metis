import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import pluginReact from "eslint-plugin-react";
import pluginReactHooks from "eslint-plugin-react-hooks";
import pluginUnusedImports from "eslint-plugin-unused-imports";
import tseslint from "typescript-eslint";

const eslintConfig = defineConfig([
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "lib/api/schema.d.ts",
    "node_modules/**",
  ]),
  ...tseslint.configs.recommended,
  ...nextVitals,
  ...nextTs,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: {
      react: pluginReact,
      "react-hooks": pluginReactHooks,
      "unused-imports": pluginUnusedImports,
    },
    settings: {
      react: {
        version: "19",
      },
    },
    rules: {
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",
      "react-hooks/exhaustive-deps": "warn",
      "unused-imports/no-unused-imports": "error",
      "unused-imports/no-unused-vars": [
        "error",
        {
          vars: "all",
          varsIgnorePattern: "^_",
          args: "after-used",
          argsIgnorePattern: "^_",
        },
      ],
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          vars: "all",
          varsIgnorePattern: "^_",
          args: "after-used",
          argsIgnorePattern: "^_",
        },
      ],
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/no-unused-expressions": "error",
      "@typescript-eslint/consistent-type-imports": "error",
      "no-console": ["warn", { allow: ["warn", "error"] }],
    },
  },
  {
    files: ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}", "lib/**/*.{ts,tsx}"],
    ignores: ["components/ui/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "Literal[value=/\\\\[[^\\\\]\\\\s]*\\\\d(px|em|rem)[^\\\\]\\\\s]*\\\\]/]",
          message:
            "Use a named length from the @theme block in app/globals.css, not a px/em/rem literal.",
        },
        {
          selector:
            "TemplateElement[value.raw=/\\\\[[^\\\\]\\\\s]*\\\\d(px|em|rem)[^\\\\]\\\\s]*\\\\]/]",
          message:
            "Use a named length from the @theme block in app/globals.css, not a px/em/rem literal.",
        },
      ],
    },
  },
]);

export default eslintConfig;