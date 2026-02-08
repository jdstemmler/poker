import { useEffect, useRef } from "react";

interface HelpModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

export default function HelpModal({ open, onClose, title, children }: HelpModalProps) {
  const backdropRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="help-backdrop"
      ref={backdropRef}
      onClick={(e) => {
        if (e.target === backdropRef.current) onClose();
      }}
    >
      <div className="help-modal">
        <div className="help-modal-header">
          <h2>{title}</h2>
          <button className="help-modal-close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <div className="help-modal-body">{children}</div>
      </div>
    </div>
  );
}
