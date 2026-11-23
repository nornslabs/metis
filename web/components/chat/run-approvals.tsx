import { AdviceDecision } from "@/components/chat/advice-decision";
import { ApprovalPrompt } from "@/components/chat/approval-prompt";
import { SpecReviewPrompt } from "@/components/chat/spec-review-prompt";
import { UserBubble } from "@/components/chat/user-bubble";
import type { AdviceChoice, Decision } from "@/components/chat/use-answer-actions";
import type { AdviceInterrupt, ApprovalInterrupt, SpecReviewInterrupt } from "@/lib/events/schemas";
import type { AdviceDecision as AdviceChoiceKind, AdviceResume, } from "@/lib/scores/decision";
import type { Suggestion } from "@/lib/scores/view";

interface RunApprovalsProps {
  advice: AdviceInterrupt | null;
  approval: ApprovalInterrupt | null;
  specReview: SpecReviewInterrupt | null;
  ideaId: string;
  ideaText: string;
  accepted: readonly Suggestion[];
  adviceChoices: readonly AdviceChoice[];
  decisions: readonly Decision[];
  disabled: boolean;
  onAdvise: (value: AdviceResume, decision: AdviceChoiceKind) => void;
  onDecide: (approved: boolean) => void;
  onOpenSpec: () => void;
}

/** The prompts that are not questions (advice decision, spec review, approval) and the user's earlier choices. */
export function RunApprovals({
  advice,
  approval,
  specReview,
  ideaId,
  ideaText,
  accepted,
  adviceChoices,
  decisions,
  disabled,
  onAdvise,
  onDecide,
  onOpenSpec,
}: RunApprovalsProps) {
  return (
    <>
      {advice ? (
        <AdviceDecision interrupt={advice} ideaText={ideaText} accepted={accepted} disabled={disabled} onDecide={onAdvise} />
      ) : null}
      {adviceChoices.map((choice) => (
        <UserBubble key={choice.seq} text={choice.label} />
      ))}
      {specReview ? <SpecReviewPrompt ideaId={ideaId} interrupt={specReview} onOpenSpec={onOpenSpec} /> : null}
      {approval ? <ApprovalPrompt interrupt={approval} disabled={disabled} onDecide={onDecide} /> : null}
      {decisions.map((decision) => (
        <UserBubble key={decision.seq} text={decision.approved ? "Approved" : "Rejected"} />
      ))}
    </>
  );
}
