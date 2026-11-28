import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";

import { SafeMarkdown } from "@/components/chat/safe-markdown";

const render = (text: string) => renderToStaticMarkup(createElement(SafeMarkdown, { text }));

describe("SafeMarkdown", () => {
  test("drops raw HTML and script tags", () => {
    const html = render('Hi <script>alert(1)</script> <b onclick="x()">bold</b>');
    expect(html).not.toContain("<script");
    expect(html).not.toContain("<b ");
    expect(html).not.toContain("onclick");
  });

  test("does not load images", () => {
    const html = render("![tracker](https://evil.example/x.png)");
    expect(html).not.toContain("<img");
    expect(html).toContain("tracker");
  });

  test("a javascript: link has no active href", () => {
    expect(render("[go](javascript:alert(1))")).not.toContain("javascript:");
  });

  test("links open safely", () => {
    const html = render("[docs](https://example.com)");
    expect(html).toContain('rel="noopener noreferrer nofollow"');
    expect(html).toContain('target="_blank"');
  });
});
