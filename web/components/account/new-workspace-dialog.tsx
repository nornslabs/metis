"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { useSwitchWorkspace } from "@/components/account/workspace-switcher";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateWorkspace } from "@/lib/api/mutations/use-create-workspace";
import { errorMessage, fieldErrors, isApiError } from "@/lib/api/errors";
import { workspaceNameSchema, type WorkspaceNameValues } from "@/lib/schemas/settings-forms";

type NewWorkspaceDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/** Names a new workspace, creates it and switches to it. */
export function NewWorkspaceDialog({ open, onOpenChange }: NewWorkspaceDialogProps) {
  const create = useCreateWorkspace();
  const switchWorkspace = useSwitchWorkspace();
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isValid },
  } = useForm<WorkspaceNameValues>({
    resolver: zodResolver(workspaceNameSchema),
    defaultValues: { name: "" },
    mode: "onChange",
  });

  function close(next: boolean) {
    if (!next) reset();
    onOpenChange(next);
  }

  const submit = handleSubmit(async ({ name }) => {
    try {
      const membership = await create.mutateAsync(name);
      close(false);
      switchWorkspace(membership.workspace.id);
    } catch (error) {
      if (!isApiError(error)) throw error;
      const fields = fieldErrors(error);
      if (fields.length === 0) setError("name", { type: "server", message: errorMessage(error) });
      for (const { name: field, error: fieldError } of fields) {
        setError(field as keyof WorkspaceNameValues, fieldError);
      }
    }
  });

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-card">
        <form onSubmit={submit} noValidate className="grid gap-3">
          <DialogHeader>
            <DialogTitle>New workspace</DialogTitle>
            <DialogDescription>Keep ideas, keys and limits for a project apart.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-1">
            <Label htmlFor="workspace-name">Workspace name</Label>
            <Input
              id="workspace-name"
              autoComplete="off"
              aria-invalid={errors.name ? true : undefined}
              aria-describedby={errors.name ? "workspace-name-error" : undefined}
              {...register("name")}
            />
            {errors.name ? (
              <p id="workspace-name-error" role="alert" className="text-meta text-destructive">
                {errors.name.message}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => close(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!isValid || create.isPending}>
              Create workspace
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
