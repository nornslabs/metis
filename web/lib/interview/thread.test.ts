import { describe, expect, it } from "vitest";

import { buildInterviewThread, groupByRun } from "./thread";

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
    const thread = buildInterviewThread({ runId: "run", turns: [turn("1", "Who?", "Freelancers")], interrupt: null, interruptSeq: 0, sent: [] });
    expect(thread.messages.map((m) => [m.role, m.text])).toEqual([
      ["agent", "Who?"],
      ["user", "Freelancers"],
    ]);
    expect(thread.pendingQuestion).toBeNull();
  });

  it("marks the open turn as the pending question", () => {
    const thread = buildInterviewThread({ runId: "run",
      turns: [turn("1", "Who?", "Freelancers"), turn("2", "Who pays?", null)],
      interrupt: ask("Who pays?"),
      interruptSeq: 2,
      sent: [],
    });
    expect(thread.messages.at(-1)).toMatchObject({ role: "agent", text: "Who pays?" });
    expect(thread.pendingQuestion).toBe("Who pays?");
  });

  it("adds the run's question when the turns list does not hold it yet", () => {
    const thread = buildInterviewThread({ runId: "run", turns: [], interrupt: ask("Who?"), interruptSeq: 1, sent: [] });
    expect(thread.messages).toHaveLength(1);
    expect(thread.pendingQuestion).toBe("Who?");
  });

  it("does not show the same question twice", () => {
    const thread = buildInterviewThread({ runId: "run", turns: [turn("1", "Who?", null)], interrupt: ask("Who?"), interruptSeq: 1, sent: [] });
    expect(thread.messages).toHaveLength(1);
  });

  it("shows an answer sent from this page before the server lists it", () => {
    const sent = [sentAt(1, "Who?", "Freelancers")];
    const listed = buildInterviewThread({ runId: "run", turns: [turn("1", "Who?", null)], interrupt: ask("Who?"), interruptSeq: 1, sent });
    const unlisted = buildInterviewThread({ runId: "run", turns: [], interrupt: ask("Who?"), interruptSeq: 1, sent });
    for (const thread of [listed, unlisted]) {
      expect(thread.messages.map((m) => m.role)).toEqual(["agent", "user"]);
      expect(thread.pendingQuestion).toBeNull();
    }
  });

  it("leaves out noted turns", () => {
    const thread = buildInterviewThread({ runId: "run",
      turns: [turn("1", "Who is it for?", "Freelancers", "noted")],
      interrupt: null,
      interruptSeq: 0,
      sent: [],
    });
    expect(thread.messages).toEqual([]);
  });

  it("has no pending question for an approval", () => {
    const thread = buildInterviewThread({ runId: "run",
      turns: [],
      interrupt: { kind: "approval", text: "Export" },
      interruptSeq: 1,
      sent: [],
    });
    expect(thread).toEqual({ messages: [], pendingQuestion: null });
  });

  it("keeps an open question of an old run unanswered without making it pending", () => {
    const thread = buildInterviewThread({ runId: "run", turns: [turn("1", "Who?", null)], interrupt: null, interruptSeq: 0, sent: [] });
    expect(thread.messages).toHaveLength(1);
    expect(thread.pendingQuestion).toBeNull();
  });
  it("keeps showing an answer after the run moved on (no pending interrupt)", () => {
    const thread = buildInterviewThread({ runId: "run",
      turns: [turn("1", "Who?", null)],
      interrupt: null,
      interruptSeq: 1,
      sent: [sentAt(1, "Who?", "Freelancers")],
    });
    expect(thread.messages.map((m) => m.role)).toEqual(["agent", "user"]);
  });

  it("does not treat a repeated question as already answered", () => {
    const thread = buildInterviewThread({ runId: "run",
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
    const thread = buildInterviewThread({ runId: "run",
      turns: [turn("1", "Who pays?", "Agencies"), turn("2", "Who pays?", null)],
      interrupt: ask("Who pays?"),
      interruptSeq: 2,
      sent: [sentAt(1, "Who pays?", "Agencies"), sentAt(2, "Who pays?", "Freelancers")],
    });
    expect(thread.messages.at(-1)).toMatchObject({ role: "user", text: "Freelancers" });
    expect(thread.pendingQuestion).toBeNull();
  });

  it("shows an older sent answer on its open turn until the server lists it", () => {
    const thread = buildInterviewThread({ runId: "run",
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

  it("marks an answer picked from options, also after the saved turn replaces the sent one", () => {
    const sent = [{ seq: 1, question: "Who?", text: "Solo freelancers; Small agencies", picked: true }];
    const pending = buildInterviewThread({ runId: "run", turns: [], interrupt: ask("Who?"), interruptSeq: 1, sent });
    expect(pending.messages.at(-1)).toMatchObject({ role: "user", text: "Solo freelancers; Small agencies", picked: true });

    const saved = buildInterviewThread({ runId: "run",
      turns: [turn("1", "Who?", "Solo freelancers; Small agencies")],
      interrupt: null,
      interruptSeq: 1,
      sent,
    });
    expect(saved.messages.at(-1)).toMatchObject({ role: "user", picked: true });
  });

  it("does not mark a typed answer as picked", () => {
    const thread = buildInterviewThread({ runId: "run",
      turns: [turn("1", "Who?", "Students")],
      interrupt: null,
      interruptSeq: 1,
      sent: [{ seq: 1, question: "Who?", text: "Students" }],
    });
    expect(thread.messages.at(-1)).toEqual({ role: "user", key: "1:a", text: "Students" });
  });
});

describe("runId and groupByRun", () => {
  const turnOf = (id: string, runId: string, answer: string | null) => ({ ...turn(id, `Q${id}`, answer), run_id: runId });

  it("tags each message with the run that asked it", () => {
    const thread = buildInterviewThread({
      runId: "live",
      turns: [turnOf("1", "first", "a"), turnOf("2", "live", null)],
      interrupt: ask("Q2"),
      interruptSeq: 1,
      sent: [],
    });
    expect(thread.messages.map((m) => m.runId)).toEqual(["first", "first", "live"]);
  });

  it("gives the not-yet-listed pending question to the live run", () => {
    const thread = buildInterviewThread({ runId: "live", turns: [], interrupt: ask("Who?"), interruptSeq: 1, sent: [] });
    expect(thread.messages[0]).toMatchObject({ key: "pending:q", runId: "live" });
  });

  it("groups by run and keeps the order inside each run", () => {
    const thread = buildInterviewThread({
      runId: "live",
      turns: [turnOf("1", "first", "a"), turnOf("2", "live", "b"), turnOf("3", "first", "c")],
      interrupt: null,
      interruptSeq: 0,
      sent: [],
    });
    const groups = groupByRun(thread.messages);
    expect([...groups.keys()]).toEqual(["first", "live"]);
    expect(groups.get("first")?.map((m) => m.key)).toEqual(["1:q", "1:a", "3:q", "3:a"]);
    expect(groups.get("live")?.map((m) => m.key)).toEqual(["2:q", "2:a"]);
  });
});
