'use client';

import { useState } from 'react';
import { X, MessageSquare, Clock, Trash2 } from 'lucide-react';

interface ChatSession {
  id: string;
  title: string;
  preview: string;
  timestamp: Date;
}

interface HistoryPanelProps {
  isOpen: boolean;
  onClose: () => void;
  sessions: ChatSession[];
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
}

export function HistoryPanel({
  isOpen,
  onClose,
  sessions,
  onSelectSession,
  onDeleteSession,
}: HistoryPanelProps) {
  if (!isOpen) return null;

  return (
    <div
      className={`fixed top-0 left-0 h-full w-80 bg-gray-900/95 backdrop-blur-xl border-r border-gray-700/50 shadow-2xl z-[10000] transition-transform duration-300 ${
        isOpen ? 'translate-x-0' : '-translate-x-full'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700/50">
        <h2 className="text-lg font-semibold text-white">Historial</h2>
        <button
          onClick={onClose}
          className="p-2 hover:bg-gray-700/50 rounded-lg transition-colors"
        >
          <X className="w-5 h-5 text-gray-400" />
        </button>
      </div>

      {/* Sessions List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <MessageSquare className="w-12 h-12 mb-2" />
            <p className="text-sm">No hay sesiones recientes</p>
          </div>
        ) : (
          sessions.map((session) => (
            <div
              key={session.id}
              className="group relative p-4 rounded-xl bg-gray-800/50 hover:bg-gray-700/50 border border-gray-700/50 hover:border-indigo-500/50 transition-all cursor-pointer"
              onClick={() => onSelectSession(session.id)}
            >
              <div className="flex items-start justify-between mb-2">
                <h3 className="font-medium text-white text-sm line-clamp-1">
                  {session.title}
                </h3>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteSession(session.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:bg-gray-600 rounded transition-all"
                >
                  <Trash2 className="w-4 h-4 text-gray-400" />
                </button>
              </div>
              <p className="text-xs text-gray-400 line-clamp-2 mb-2">
                {session.preview}
              </p>
              <div className="flex items-center gap-1 text-xs text-gray-500">
                <Clock className="w-3 h-3" />
                <span>
                  {new Date(session.timestamp).toLocaleDateString('es-ES', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="px-6 py-4 border-t border-gray-700/50">
        <button
          onClick={onClose}
          className="w-full py-2 px-4 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors text-sm font-medium"
        >
          Cerrar Panel
        </button>
      </div>
    </div>
  );
}
