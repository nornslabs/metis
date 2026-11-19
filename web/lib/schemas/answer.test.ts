import { describe, expect, it } from "vitest";

import { ANSWER_MAX, QUICK_REPLIES, answerSchema, toAnswer } from "./answer";

describe("answerSchema", () => {
  it("accepts a normal answer", () => {
    expect(answerSchema.safeParse({ text: "Freelancers" }).success).toBe(true);
  });

  it("rejects an empty or blank answer", () => {
    expect(answerSchema.safeParse({ text: "" }).success).toBe(false);
    expect(answerSchema.safeParse({ text: "   \n " }).success).toBe(false);
  });

  it("accepts exactly the maximum and rejects one more", () => {
    expect(answerSchema.safeParse({ text: "a".repeat(ANSWER_MAX) }).success).toBe(true);
    expect(answerSchema.safeParse({ text: "a".repeat(ANSWER_MAX + 1) }).success).toBe(false);
  });

  it("measures the length after trimming", () => {
    expect(answerSchema.safeParse({ text: `  ${"a".repeat(ANSWER_MAX)}  ` }).success).toBe(true);
  });
});

describe("toAnswer", () => {
  it("trims the text", () => {
    expect(toAnswer({ text: "  Freelancers \n" })).toBe("Freelancers");
  });
});

describe("QUICK_REPLIES", () => {
  it("sends the phrases the server understands", () => {
    expect(QUICK_REPLIES.map((reply) => reply.value)).toEqual(["skip", "that's enough"]);
  });
});
