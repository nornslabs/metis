import { describe, expect, test } from "vitest";

import { hldComponentNames } from "./hld";

const HLD = `## Overview

Text.

## MVP components

### Auth

**Purpose:** Sign in.

### Billing

**Purpose:** Pay.

## How the components connect

### Not a component`;

describe("hldComponentNames", () => {
  test("lists the ### headings under MVP components only", () => {
    expect(hldComponentNames(HLD)).toEqual(["Auth", "Billing"]);
  });

  test("is empty when the section is missing", () => {
    expect(hldComponentNames("## Overview\n\n### X")).toEqual([]);
  });
});
