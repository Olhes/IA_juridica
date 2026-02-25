'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';

interface MarkdownRendererProps {
  content: string;
  isStreaming?: boolean;
}

/**
 * Renderizador de Markdown con estilos propios para burbujas del chat.
 * Soporta light y dark mode con variantes dark: de Tailwind.
 */
export function MarkdownRenderer({ content, isStreaming = false }: MarkdownRendererProps) {
  const components: Components = {
    // ─── Headings ──────────────────────────────────────────────
    h1: ({ children }) => (
      <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100 mt-4 mb-2 pb-1.5 border-b border-slate-200 dark:border-gray-700 first:mt-0">
        {children}
      </h1>
    ),
    h2: ({ children }) => (
      <h2 className="text-base font-bold text-slate-800 dark:text-slate-200 mt-4 mb-2 first:mt-0">
        {children}
      </h2>
    ),
    h3: ({ children }) => (
      <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mt-3 mb-1.5 first:mt-0">
        {children}
      </h3>
    ),
    h4: ({ children }) => (
      <h4 className="text-sm font-semibold text-indigo-700 dark:text-indigo-400 mt-2 mb-1">
        {children}
      </h4>
    ),

    // ─── Párrafos ──────────────────────────────────────────────
    p: ({ children }) => (
      <p className="text-sm md:text-base leading-relaxed text-slate-800 dark:text-slate-200 mb-3 last:mb-0">
        {children}
      </p>
    ),

    // ─── Listas (unordered) ────────────────────────────────────
    ul: ({ children }) => (
      <ul className="my-3 space-y-2 ml-1">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="my-3 space-y-2 ml-1 list-decimal list-inside">{children}</ol>
    ),
    li: ({ children }) => (
      <li className="flex items-start gap-2.5 text-sm md:text-base text-slate-800 dark:text-slate-200 leading-relaxed">
        <span className="flex-shrink-0 mt-2 w-1.5 h-1.5 rounded-full bg-indigo-400 dark:bg-indigo-500" />
        <span className="flex-1 min-w-0">{children}</span>
      </li>
    ),

    // ─── Énfasis ───────────────────────────────────────────────
    strong: ({ children }) => (
      <strong className="font-semibold text-slate-900 dark:text-slate-100">{children}</strong>
    ),
    em: ({ children }) => (
      <em className="italic text-slate-700 dark:text-slate-300">{children}</em>
    ),

    // ─── Código inline ─────────────────────────────────────────
    code: ({ children, className }) => {
      const isBlock = className?.startsWith('language-');
      if (isBlock) {
        return (
          <code className="block w-full font-mono text-xs leading-relaxed text-indigo-200 dark:text-indigo-300">
            {children}
          </code>
        );
      }
      return (
        <code className="inline-block font-mono text-xs bg-indigo-50 dark:bg-indigo-950/50 border border-indigo-200 dark:border-indigo-800 text-indigo-700 dark:text-indigo-300 rounded px-1.5 py-0.5 mx-0.5">
          {children}
        </code>
      );
    },

    // ─── Bloque de código ──────────────────────────────────────
    pre: ({ children }) => (
      <pre className="my-3 p-4 bg-gray-900 dark:bg-gray-950 rounded-xl overflow-x-auto text-xs font-mono text-slate-100 border border-gray-700 dark:border-gray-800">
        {children}
      </pre>
    ),

    // ─── Citas ─────────────────────────────────────────────────
    blockquote: ({ children }) => (
      <blockquote className="my-3 pl-4 border-l-4 border-indigo-300 dark:border-indigo-700 bg-indigo-50/60 dark:bg-indigo-950/30 rounded-r-lg py-2 pr-3 text-sm text-indigo-800 dark:text-indigo-300 italic">
        {children}
      </blockquote>
    ),

    // ─── Divider ───────────────────────────────────────────────
    hr: () => <hr className="my-4 border-slate-200 dark:border-gray-700" />,

    // ─── Tablas ────────────────────────────────────────────────
    table: ({ children }) => (
      <div className="my-4 overflow-x-auto rounded-xl border border-slate-200 dark:border-gray-700">
        <table className="w-full text-sm border-collapse bg-white dark:bg-gray-900">
          {children}
        </table>
      </div>
    ),
    thead: ({ children }) => (
      <thead className="bg-slate-50 dark:bg-gray-800 border-b border-slate-200 dark:border-gray-700">
        {children}
      </thead>
    ),
    tbody: ({ children }) => (
      <tbody className="divide-y divide-slate-100 dark:divide-gray-800">{children}</tbody>
    ),
    tr: ({ children }) => (
      <tr className="hover:bg-slate-50 dark:hover:bg-gray-800/50 transition-colors">{children}</tr>
    ),
    th: ({ children }) => (
      <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide">
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td className="px-4 py-2.5 text-slate-700 dark:text-slate-300">{children}</td>
    ),

    // ─── Links ─────────────────────────────────────────────────
    a: ({ children, href }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-indigo-600 dark:text-indigo-400 underline underline-offset-2 hover:text-indigo-800 dark:hover:text-indigo-300 transition-colors"
      >
        {children}
      </a>
    ),
  };

  return (
    <div className="markdown-content min-w-0">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
      {isStreaming && (
        <span className="inline-block w-0.5 h-4 bg-indigo-500 dark:bg-indigo-400 ml-0.5 align-middle animate-pulse" />
      )}
    </div>
  );
}
