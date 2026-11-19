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
const sentAt = (seq: number, question: string, text: string) => ({ seq, question, text });

describe("buildInterviewThread", () => {
  it("shows answered turns as a question and an answer", () => {
    const thread = buildInterviewThread({ turns: [turn("1", "Who?", "Freelancers")], interrupt: null, interruptSeq: 0, sent: [] });
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
      interruptSeq: 2,
      sent: [],
    });
    expect(thread.messages.at(-1)).toMatchObject({ role: "agent", text: "Who pays?" });
    expect(thread.pendingQuestion).toBe("Who pays?");
  });

  it("adds the run's question when the turns list does not hold it yet", () => {
    const thread = buildInterviewThread({ turns: [], interrupt: ask("Who?"), interruptSeq: 1, sent: [] });
    expect(thread.messages).toHaveLength(1);
    expect(thread.pendingQuestion).toBe("Who?");
  });

  it("does not show the same question twice", () => {
    const thread = buildInterviewThread({ turns: [turn("1", "Who?", null)], interrupt: ask("Who?"), interruptSeq: 1, sent: [] });
    expect(thread.messages).toHaveLength(1);
  });

  it("shows an answer sent from this page before the server lists it", () => {
    const sent = [sentAt(1, "Who?", "Freelancers")];
    const listed = buildInterviewThread({ turns: [turn("1", "Who?", null)], interrupt: ask("Who?"), interruptSeq: 1, sent });
    const unlisted = buildInterviewThread({ turns: [], interrupt: ask("Who?"), interruptSeq: 1, sent });
    for (const thread of [listed, unlisted]) {
      expect(thread.messages.map((m) => m.role)).toEqual(["agent", "user"]);
      expect(thread.pendingQuestion).toBeNull();
    }
  });

  it("leaves out noted turns", () => {
    const thread = buildInterviewThread({
      turns: [turn("1", "Who is it for?", "Freelancers", "noted")],
      interrupt: null,
      interruptSeq: 0,
      sent: [],
    });
    expect(thread.messages).toEqual([]);
  });

  it("has no pending question for an approval", () => {
    const thread = buildInterviewThread({
      turns: [],
      interrupt: { kind: "approval", text: "Export" },
      interruptSeq: 1,
      sent: [],
    });
    expect(thread).toEqual({ messages: [], pendingQuestion: null });
  });

  it("keeps an open question of an old run unanswered without making it pending", () => {
    const thread = buildInterviewThread({ turns: [turn("1", "Who?", null)], interrupt: null, interruptSeq: 0, sent: [] });
    expect(thread.messages).toHaveLength(1);
    expect(thread.pendingQuestion).toBeNull();
  });
  it("keeps showing an answer after the run moved on (no pending interrupt)", () => {
    const thread = buildInterviewThread({
      turns: [turn("1", "Who?", null)],
      interrupt: null,
      interruptSeq: 1,
      sent: [sentAt(1, "Who?", "Freelancers")],
    });
    expect(thread.messages.map((m) => m.role)).toEqual(["agent", "user"]);
  });

  it("does not treat a repeated question as already answered", () => {
    const thread = buildInterviewThread({
      turns: [turn("1", "Who pays?", "Agencies"), turn("2", "Who pays?", null)],
      interrupt: ask("Who pays?"),
      interruptSeq: 2,
      sent: [sentAt(1, "Who pays?", "Agencies")],
    });
    expect(thread.messages.map((m) => [m.role, m.text])).toEqual([
      ["agent", "Who pays?"],
      ["user", "Agencies"],
      ["agent", "Who pays?"],
    ]);
    expect(thread.pendingQuestion).toBe("Who pays?");
  });

  it("answers a repeated question once its own answer is sent", () => {
    const thread = buildInterviewThread({
      turns: [turn("1", "Who pays?", "Agencies"), turn("2", "Who pays?", null)],
      interrupt: ask("Who pays?"),
      interruptSeq: 2,
      sent: [sentAt(1, "Who pays?", "Agencies"), sentAt(2, "Who pays?", "Freelancers")],
    });
    expect(thread.messages.at(-1)).toMatchObject({ role: "user", text: "Freelancers" });
    expect(thread.pendingQuestion).toBeNull();
  });

  it("shows an older sent answer on its open turn until the server lists it", () => {
    const thread = buildInterviewThread({
      turns: [turn("1", "Who?", null), turn("2", "Who pays?", null)],
      interrupt: ask("Who pays?"),
      interruptSeq: 2,
      sent: [sentAt(1, "Who?", "Freelancers")],
    });
    expect(thread.messages.map((m) => [m.role, m.text])).toEqual([
      ["agent", "Who?"],
      ["user", "Freelancers"],
      ["agent", "Who pays?"],
    ]);
    expect(thread.pendingQuestion).toBe("Who pays?");
  });
});
