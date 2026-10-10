"use client";

import { useModal } from "@/components/ui/useModal";

export function Dialog({
  title,
  onClose,
  children,
  size = "md",
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  size?: "md" | "lg";
}) {
  const modalRef = useModal<HTMLDivElement>(onClose);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-6">
      <div className="absolute inset-0 bg-ink-950/70 backdrop-blur-[2px]" onClick={onClose} />
      <div
        ref={modalRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`relative flex max-h-[90vh] w-full flex-col ${size === "lg" ? "max-w-5xl" : "max-w-2xl"} rounded-t-2xl outline-none border border-white/10 bg-ink-900 shadow-2xl sm:rounded-2xl`}
      >
        <div className="flex items-center justify-between border-b border-white/5 px-5 py-3">
          <h2 className="font-display text-xl font-bold uppercase tracking-wide">{title}</h2>
          <button type="button" onClick={onClose} className="btn btn-ghost px-2 py-1" aria-label="Close">
            ✕
          </button>
        </div>
        <div className="overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}
