import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function PageHero({
  icon: Icon,
  eyebrow,
  title,
  description,
  children,
}: {
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  description: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="-mx-4 border-b px-4 pb-8 pt-6 sm:-mx-6 sm:px-6 sm:pt-8">
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        <span className="flex w-fit items-center gap-2 rounded-sm border bg-muted/60 px-2 py-1 font-mono text-[11px] text-muted-foreground">
          <Icon className="size-3 text-primary" />
          {eyebrow}
        </span>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
        <p className="max-w-2xl text-balance text-muted-foreground">{description}</p>
        {children}
      </div>
    </div>
  );
}
