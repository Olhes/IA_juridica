'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';

interface MarkdownRendererProps {
  content: string;
  isStreaming?: boolean;
}

// Rombo tocapu que marca los subtítulos (diseño A).
function HeadingMark() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" className="flex-none">
      <path d="M12 2l10 10-10 10L2 12z" fill="#B8285F" />
      <path d="M12 8l4 4-4 4-4-4z" fill="#F2A93B" />
    </svg>
  );
}

/**
 * Renderizador de Markdown para las respuestas del asistente, con la jerarquía
 * del diseño A (Tocapu): subtítulos en Bricolage con rombo, viñetas en rombo
 * dorado y listas numeradas en casillas magenta (ver `.md-list` en globals.css).
 */
export function MarkdownRenderer({ content, isStreaming = false }: MarkdownRendererProps) {
  const components: Components = {
    // ─── Headings ──────────────────────────────────────────────
    h1: ({ children }) => (
      <h1 className="font-display text-2xl font-extrabold leading-tight text-[#26162F] mt-6 mb-3 first:mt-0">
        {children}
      </h1>
    ),
    h2: ({ children }) => (
      <h2 className="flex items-center gap-2 font-display text-xl font-extrabold leading-snug text-[#26162F] mt-6 mb-2.5 first:mt-0">
        <HeadingMark />
        {children}
      </h2>
    ),
    h3: ({ children }) => (
      <h3 className="flex items-center gap-2 font-display text-lg font-extrabold leading-snug text-[#26162F] mt-5 mb-2 first:mt-0">
        <HeadingMark />
        {children}
      </h3>
    ),
    h4: ({ children }) => (
      <h4 className="text-[13px] font-extrabold uppercase tracking-wider text-indigo-700 mt-4 mb-1.5 first:mt-0">
        {children}
      </h4>
    ),

    // ─── Párrafos ──────────────────────────────────────────────
    // Un párrafo que solo contiene negrita (`**Título**`) es un subtítulo de la respuesta.
    p: ({ children, node }) => {
      const only = node?.children.length === 1 ? node.children[0] : undefined;
      if (only?.type === 'element' && only.tagName === 'strong') {
        return (
          <h3 className="flex items-center gap-2 font-display text-lg font-extrabold leading-snug text-[#26162F] mt-5 mb-2 first:mt-0">
            <HeadingMark />
            <span>{children}</span>
          </h3>
        );
      }
      return (
        <p className="text-base leading-[1.7] text-[#26162F] mb-3.5 last:mb-0">
          {children}
        </p>
      );
    },

    // ─── Listas ────────────────────────────────────────────────
    ul: ({ children }) => (
      <ul className="md-list my-3 space-y-2">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="md-list my-3 space-y-2.5">{children}</ol>
    ),
    li: ({ children }) => (
      <li className="flex items-start gap-3 text-base text-[#26162F] leading-[1.65]">
        <span className="md-bullet" aria-hidden="true" />
        <span className="flex-1 min-w-0">{children}</span>
      </li>
    ),

    // ─── Énfasis ───────────────────────────────────────────────
    strong: ({ children }) => (
      <strong className="font-extrabold text-indigo-800">{children}</strong>
    ),
    em: ({ children }) => (
      <em className="italic text-slate-700">{children}</em>
    ),

    // ─── Código inline ─────────────────────────────────────────
    code: ({ children, className }) => {
      const isBlock = className?.startsWith('language-');
      if (isBlock) {
        return (
          <code className="block w-full font-mono text-xs leading-relaxed text-slate-100">
            {children}
          </code>
        );
      }
      return (
        <code className="inline-block font-mono text-[13px] bg-slate-100 text-indigo-800 rounded-md px-1.5 py-0.5 mx-0.5">
          {children}
        </code>
      );
    },

    // ─── Bloque de código ──────────────────────────────────────
    pre: ({ children }) => (
      <pre className="my-3 p-4 bg-slate-900 rounded-xl overflow-x-auto text-xs font-mono text-slate-100">
        {children}
      </pre>
    ),

    // ─── Citas: aviso dorado como en el diseño ─────────────────
    blockquote: ({ children }) => (
      <blockquote className="my-4 rounded-2xl bg-amber-50 px-4 py-3 text-[15px] text-amber-800 [&_p]:text-amber-800 [&_p]:text-[15px]">
        {children}
      </blockquote>
    ),

    // ─── Divider ───────────────────────────────────────────────
    hr: () => <hr className="my-5 border-0 border-t border-dashed border-slate-300" />,

    // ─── Tablas ────────────────────────────────────────────────
    table: ({ children }) => (
      <div className="my-4 overflow-x-auto rounded-2xl border border-slate-200">
        <table className="w-full text-sm border-collapse bg-white">
          {children}
        </table>
      </div>
    ),
    thead: ({ children }) => (
      <thead className="bg-slate-100 border-b border-slate-200">
        {children}
      </thead>
    ),
    tbody: ({ children }) => (
      <tbody className="divide-y divide-slate-100">{children}</tbody>
    ),
    tr: ({ children }) => (
      <tr className="hover:bg-slate-50 transition-colors">{children}</tr>
    ),
    th: ({ children }) => (
      <th className="px-4 py-2.5 text-left text-xs font-extrabold text-slate-700 uppercase tracking-wide">
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td className="px-4 py-2.5 text-[#26162F]">{children}</td>
    ),

    // ─── Links ─────────────────────────────────────────────────
    a: ({ children, href }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="font-bold text-indigo-700 underline underline-offset-2 hover:text-indigo-800 transition-colors"
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
        <span className="inline-block w-0.5 h-4 bg-indigo-600 ml-0.5 align-middle animate-pulse" />
      )}
    </div>
  );
}
