import { describe, expect, it } from "vitest";

import { hasOptions, keyChoice, keyHint, pickedLabel, questionHeading, recommendedIds, toggleId } from "./choice";

const options = [
  { id: "o1", label: "Solo freelancers", recommended: true },
  { id: "o2", label: "Small agencies", recommended: false },
  { id: "o3", label: "In-house teams", recommended: true },
];

describe("hasOptions", () => {
  it("is true only for a question with at least one option", () => {
    expect(hasOptions({ kind: "question", text: "Who?", options })).toBe(true);
    expect(hasOptions({ kind: "question", text: "Who?", options: [] })).toBe(false);
    expect(hasOptions({ kind: "question", text: "Who?" })).toBe(false);
    expect(hasOptions(null)).toBe(false);
  });
});

describe("recommendedIds and toggleId", () => {
  it("lists the recommended options in order", () => {
    expect(recommendedIds(options)).toEqual(["o1", "o3"]);
  });

  it("adds and removes an id without changing the input", () => {
    const checked = ["o1"] as const;
    expect(toggleId(checked, "o2")).toEqual(["o1", "o2"]);
    expect(toggleId(checked, "o1")).toEqual([]);
    expect(checked).toEqual(["o1"]);
  });
});

describe("keyChoice", () => {
  it("maps 1–9 to the option at that position", () => {
    expect(keyChoice("2", options, true)).toEqual({ kind: "option", option: options[1] });
  });

  it("ignores a key with no option behind it", () => {
    expect(keyChoice("4", options, true)).toBeNull();
    expect(keyChoice("a", options, true)).toBeNull();
    expect(keyChoice("10", options, true)).toBeNull();
  });

  it("maps 0 to Something else only when free text is allowed", () => {
    expect(keyChoice("0", options, true)).toEqual({ kind: "other" });
    expect(keyChoice("0", options, false)).toBeNull();
  });
});

describe("pickedLabel", () => {
  it("joins the picked labels in option order, as the server saves them", () => {
    expect(pickedLabel(options, ["o3", "o1"])).toBe("Solo freelancers; In-house teams");
    expect(pickedLabel(options, ["o2"])).toBe("Small agencies");
  });
});

describe("questionHeading and keyHint", () => {
  it("shows n of m, n alone, or a plain heading", () => {
    expect(questionHeading(2, 5)).toBe("Question 2 of 5");
    expect(questionHeading(2, undefined)).toBe("Question 2");
    expect(questionHeading(undefined, undefined)).toBe("Pick an answer");
  });

  it("never shows a total below the number", () => {
    expect(questionHeading(4, 3)).toBe("Question 4 of 4");
  });

  it("describes the keys that work", () => {
    expect(keyHint(4, false)).toBe("1–4 to pick");
    expect(keyHint(1, false)).toBe("1 to pick");
    expect(keyHint(3, true)).toBe("1–3 to toggle · Enter to continue");
  });
});
