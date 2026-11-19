import { describe, expect, it } from "vitest";

import { buildInterviewThread } from "./thread";

const turn = (id: string, question: string, answer: string | null, source: "asked" | "noted" = "asked") => ({
  id,
  idea_id: "idea",
  run_id: "run",
  topic: "problem" as const,
  source,
  question,
  answer,
});

const ask = (text: string) => ({ kind: "question" as const, text });

describe("buildInterviewThread", () => {
  it("shows answered turns as a question and an answer", () => {
    const thread = buildInterviewThread({ turns: [turn("1", "Who?", "Freelancers")], interrupt: null, sent: [] });
    expect(thread.messages.map((m) => [m.role, m.text])).toEqual([
      ["agent", "Who?"],
      ["user", "Freelancers"],
    ]);
    expect(thread.pendingQuestion).toBeNull();
  });

  it("marks the open turn as the pending question", () => {
    const thread = buildInterviewThread({
      turns: [turn("1", "Who?", "Freelancers"), turn("2", "Who pays?", null)],
      interrupt: ask("Who pays?"),
      sent: [],
    });
    expect(thread.messages.at(-1)).toMatchObject({ role: "agent", text: "Who pays?" });
    expect(thread.pendingQuestion).toBe("Who pays?");
  });

  it("adds the run's question when the turns list does not hold it yet", () => {
    const thread = buildInterviewThread({ turns: [], interrupt: ask("Who?"), sent: [] });
    expect(thread.messages).toHaveLength(1);
    expect(thread.pendingQuestion).toBe("Who?");
  });

  it("does not show the same question twice", () => {
    const thread = buildInterviewThread({ turns: [turn("1", "Who?", null)], interrupt: ask("Who?"), sent: [] });
    expect(thread.messages).toHaveLength(1);
  });

  it("shows an answer sent from this page before the server lists it", () => {
    const sent = [{ question: "Who?", text: "Freelancers" }];
    const listed = buildInterviewThread({ turns: [turn("1", "Who?", null)], interrupt: ask("Who?"), sent });
    const unlisted = buildInterviewThread({ turns: [], interrupt: ask("Who?"), sent });
    for (const thread of [listed, unlisted]) {
      expect(thread.messages.map((m) => m.role)).toEqual(["agent", "user"]);
      expect(thread.pendingQuestion).toBeNull();
    }
  });

  it("leaves out noted turns", () => {
    const thread = buildInterviewThread({
      turns: [turn("1", "Who is it for?", "Freelancers", "noted")],
      interrupt: null,
      sent: [],
    });
    expect(thread.messages).toEqual([]);
  });

  it("has no pending question for an approval", () => {
    const thread = buildInterviewThread({
      turns: [],
      interrupt: { kind: "approval", text: "Export" },
      sent: [],
    });
    expect(thread).toEqual({ messages: [], pendingQuestion: null });
  });

  it("keeps an open question of an old run unanswered without making it pending", () => {
    const thread = buildInterviewThread({ turns: [turn("1", "Who?", null)], interrupt: null, sent: [] });
    expect(thread.messages).toHaveLength(1);
    expect(thread.pendingQuestion).toBeNull();
  });
});
