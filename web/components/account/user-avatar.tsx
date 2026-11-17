import { cn } from "@/lib/utils";

type UserAvatarProps = {
  name: string | null;
  email: string;
  image: string | null;
  className?: string;
};

/** Up to two initials from the name, else the first letter of the email. */
export function initialsOf(name: string | null, email: string): string {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return email.slice(0, 1).toUpperCase();
  return words
    .slice(0, 2)
    .map((word) => word.slice(0, 1).toUpperCase())
    .join("");
}

/**
 * A square avatar (the design has no round shapes): the user's picture over their initials, so a
 * picture that fails to load still leaves the initials.
 */
export function UserAvatar({ name, email, image, className }: UserAvatarProps) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "relative grid size-6 shrink-0 place-items-center overflow-hidden bg-muted text-micro font-medium",
        className,
      )}
    >
      {initialsOf(name, email)}
      {image ? (
        // An external picture URL (Google): next/image would need every host allow-listed.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={image}
          alt=""
          referrerPolicy="no-referrer"
          className="absolute inset-0 size-full object-cover"
        />
      ) : null}
    </span>
  );
}
