import { type ReactNode, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils';

interface PanelProps {
  id: string;
  title: string;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
  defaultCollapsed?: boolean;
  actions?: ReactNode;
}

export function Panel({ id, title, icon, children, className, defaultCollapsed = false, actions }: PanelProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <div
      id={id}
      className={cn(
        'flex flex-col rounded-lg border border-slate-800 bg-slate-900/60 backdrop-blur-sm overflow-hidden',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800 bg-slate-900/80 select-none">
        <div className="flex items-center gap-2">
          {icon && <span className="text-blue-400">{icon}</span>}
          <h2 className="text-sm font-semibold tracking-wide text-slate-200 uppercase">{title}</h2>
        </div>
        <div className="flex items-center gap-2">
          {!collapsed && actions}
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="text-slate-500 hover:text-slate-300 transition-colors p-0.5"
            aria-label={collapsed ? 'Expand panel' : 'Collapse panel'}
          >
            {collapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </button>
        </div>
      </div>
      {/* Body */}
      {!collapsed && (
        <div className="flex-1 overflow-auto p-3">
          {children}
        </div>
      )}
    </div>
  );
}
