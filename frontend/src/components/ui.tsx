import { ReactNode } from "react";

export function Section({
  index,
  title,
  children,
  aside,
}: {
  index: string;
  title: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className="mb-10">
      <div className="mb-3 flex items-baseline gap-3 border-b border-carbon-700 pb-2">
        <span className="data text-xs text-signal">{index}</span>
        <h2 className="label text-sm text-bone-100">{title}</h2>
        {aside && <span className="data ml-auto text-xs text-bone-300">{aside}</span>}
      </div>
      {children}
    </section>
  );
}

export function Panel({
  title,
  children,
  note,
  className = "",
  delay = 0,
}: {
  title?: string;
  children: ReactNode;
  note?: string;
  className?: string;
  delay?: number;
}) {
  return (
    <div className={`panel rise p-4 ${className}`} style={{ animationDelay: `${delay}ms` }}>
      {title && (
        <div className="mb-2 flex items-baseline justify-between">
          <h3 className="label text-xs text-bone-300">{title}</h3>
          {note && <span className="data text-[10px] text-carbon-500">{note}</span>}
        </div>
      )}
      {children}
    </div>
  );
}

export function Stat({
  label,
  value,
  unit,
  tone = "text-bone-50",
  sub,
}: {
  label: string;
  value: string;
  unit?: string;
  tone?: string;
  sub?: string;
}) {
  return (
    <div>
      <div className="label text-[11px] text-bone-300">{label}</div>
      <div className={`data text-3xl font-bold leading-tight ${tone}`}>
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-bone-300">{unit}</span>}
      </div>
      {sub && <div className="data mt-0.5 text-[11px] text-bone-300">{sub}</div>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-40 items-center justify-center border border-dashed border-carbon-700 p-6 text-center">
      <p className="data max-w-md text-xs leading-relaxed text-bone-300">{children}</p>
    </div>
  );
}

export const tooltipStyle = {
  backgroundColor: "#1d1a17",
  border: "1px solid #57503f",
  borderRadius: 0,
  fontFamily: '"Spline Sans Mono", monospace',
  fontSize: 11,
  color: "#e8e2d6",
} as const;
