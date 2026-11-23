import { describe, expect, it } from "vitest";

import { ANSWER_MAX, QUICK_REPLIES, answerSchema, pickValue, textValue, toAnswer } from "./answer";

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

describe("answer values", () => {
  it("sends typed text as a plain string for a plain question and as {text} when options were offered", () => {
    expect(textValue("Students", false)).toBe("Students");
    expect(textValue("Students", true)).toEqual({ option_ids: [], text: "Students" });
  });

  it("sends picks as option ids and copies the list", () => {
    const ids = ["o1", "o3"] as const;
    const value = pickValue(ids);
    expect(value).toEqual({ option_ids: ["o1", "o3"] });
    expect(value).not.toBe(ids);
  });
});
