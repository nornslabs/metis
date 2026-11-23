import { AdviceDecision } from "@/components/chat/advice-decision";
import { ApprovalPrompt } from "@/components/chat/approval-prompt";
import { UserBubble } from "@/components/chat/user-bubble";
import type { AdviceChoice, Decision } from "@/components/chat/use-answer-actions";
import type { AdviceInterrupt, ApprovalInterrupt } from "@/lib/events/schemas";
import type { AdviceDecision as AdviceChoiceKind, AdviceResume, } from "@/lib/scores/decision";
import type { Suggestion } from "@/lib/scores/view";

interface RunApprovalsProps {
  advice: AdviceInterrupt | null;
  approval: ApprovalInterrupt | null;
  ideaText: string;
  accepted: readonly Suggestion[];
  adviceChoices: readonly AdviceChoice[];
  decisions: readonly Decision[];
  disabled: boolean;
  onAdvise: (value: AdviceResume, decision: AdviceChoiceKind) => void;
  onDecide: (approved: boolean) => void;
}

/** The prompts that are not questions (advice decision, approval) and the user's earlier choices. */
export function RunApprovals({
  advice,
  approval,
  ideaText,
  accepted,
  adviceChoices,
  decisions,
  disabled,
  onAdvise,
  onDecide,
}: RunApprovalsProps) {
  return (
    <>
      {advice ? (
        <AdviceDecision interrupt={advice} ideaText={ideaText} accepted={accepted} disabled={disabled} onDecide={onAdvise} />
      ) : null}
      {adviceChoices.map((choice) => (
        <UserBubble key={choice.seq} text={choice.label} />
      ))}
      {approval ? <ApprovalPrompt interrupt={approval} disabled={disabled} onDecide={onDecide} /> : null}
      {decisions.map((decision) => (
        <UserBubble key={decision.seq} text={decision.approved ? "Approved" : "Rejected"} />
      ))}
    </>
  );
}
