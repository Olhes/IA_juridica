'use client';

import { useState, useRef, useEffect } from 'react';
import { Pen, Mic, Paperclip, History, FileText, Camera } from 'lucide-react';

interface FloatingRadialHubProps {
  onTerminalOpen?: () => void;
  onHistoryOpen?: () => void;
  onFileUpload?: () => void;
  onCameraOpen?: () => void;
  onMicToggle?: () => void;
}

export function FloatingRadialHub({
  onTerminalOpen,
  onHistoryOpen,
  onFileUpload,
  onCameraOpen,
  onMicToggle,
}: FloatingRadialHubProps) {
  const [rotation, setRotation] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [showSatellites, setShowSatellites] = useState(false);
  const hubRef = useRef<HTMLDivElement>(null);
  const startAngleRef = useRef(0);
  const startRotationRef = useRef(0);

  // --- Manejo de Drag / Gestos de Rotación Dial ---
  const handleStart = (clientX: number, clientY: number) => {
    setIsDragging(true);
    const rect = hubRef.current?.getBoundingClientRect();
    if (!rect) return;
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    startAngleRef.current = Math.atan2(clientY - centerY, clientX - centerX);
    startRotationRef.current = rotation;
  };

  const handleMove = (clientX: number, clientY: number) => {
    if (!isDragging || !hubRef.current) return;
    const rect = hubRef.current.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    const currentAngle = Math.atan2(clientY - centerY, clientX - centerX);
    const angleDiff = currentAngle - startAngleRef.current;
    setRotation(startRotationRef.current + angleDiff);
  };

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => handleMove(e.clientX, e.clientY);
    const onMouseUp = () => setIsDragging(false);
    const onTouchMove = (e: TouchEvent) => {
      if (isDragging) {
        e.preventDefault();
        handleMove(e.touches[0].clientX, e.touches[0].clientY);
      }
    };
    const onTouchEnd = () => setIsDragging(false);

    if (isDragging) {
      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);
      window.addEventListener('touchmove', onTouchMove, { passive: false });
      window.addEventListener('touchend', onTouchEnd);
    }
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('touchmove', onTouchMove);
      window.removeEventListener('touchend', onTouchEnd);
    };
  }, [isDragging]);

  // --- Geometría Orbital de Satélites ---
  const clipBaseAngle = Math.PI * 0.75 + rotation;
  const hubRadius = 96; // 48px radio base de la rueda
  const clipInternalDist = hubRadius * 0.5; // Distancia desde el centro del dial al centro del cuadrante Clip

  // Coordenadas locales del botón del clip (origen de la animación)
  const clipX = Math.cos(clipBaseAngle) * clipInternalDist;
  const clipY = Math.sin(clipBaseAngle) * clipInternalDist;

  // Radio orbital expandido
  const orbitRadius = 140; 
  const sat1Angle = clipBaseAngle - 0.38;
  const sat2Angle = clipBaseAngle + 0.38;

  // Coordenadas objetivo expandidas
  const sat1X = Math.cos(sat1Angle) * orbitRadius;
  const sat1Y = Math.sin(sat1Angle) * orbitRadius;

  const sat2X = Math.cos(sat2Angle) * orbitRadius;
  const sat2Y = Math.sin(sat2Angle) * orbitRadius;

  return (
    <>
      <div className="fixed bottom-10 right-10 z-[9999] select-none flex items-center justify-center">
        
        {/* --- CONTENEDOR PRINCIPAL CON VIBRACIÓN --- */}
        <div 
          ref={hubRef}
          className="relative w-48 h-48 animate-vibrate"
          onMouseDown={(e) => handleStart(e.clientX, e.clientY)}
          onTouchStart={(e) => handleStart(e.touches[0].clientX, e.touches[0].clientY)}
          style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
        >

          {/* --- CÍRCULO BASE ROTATORIO --- */}
          <div
            className="absolute inset-0 rounded-full bg-slate-900 border-4 border-black shadow-[0_10px_30px_rgba(0,0,0,0.5)] transition-transform duration-75"
            style={{ transform: `rotate(${rotation}rad)` }}
          >
            {/* Cruz Divisoria Negra en Capa Intermedia */}
            <div className="absolute top-0 bottom-0 left-1/2 -translate-x-1/2 w-2.5 bg-black z-20 pointer-events-none shadow-[2px_0_8px_rgba(0,0,0,0.6)]" />
            <div className="absolute left-0 right-0 top-1/2 -translate-y-1/2 h-2.5 bg-black z-20 pointer-events-none shadow-[0_2px_8px_rgba(0,0,0,0.6)]" />

            {/* --- CUADRANTE 1: ARRIBA IZQUIERDA (LÁPIZ) --- */}
            <button
              onClick={() => {
                setShowSatellites(false);
                onTerminalOpen?.();
              }}
              className="absolute top-0 left-0 w-1/2 h-1/2 rounded-tl-full bg-slate-900 flex items-center justify-center transition-all duration-300 ease-out group hover:z-30 hover:scale-110 hover:-translate-x-1 hover:-translate-y-1 hover:shadow-[0_15px_30px_rgba(0,0,0,0.8)] hover:bg-slate-800 active:scale-95"
            >
              <div style={{ transform: `rotate(${-rotation}rad)` }} className="transition-transform group-hover:scale-110">
                <Pen className="w-8 h-8 text-white stroke-[2.5]" />
              </div>
            </button>

            {/* --- CUADRANTE 2: ARRIBA DERECHA (MICRÓFONO) --- */}
            <button
              onClick={() => {
                setShowSatellites(false);
                onMicToggle?.();
              }}
              className="absolute top-0 right-0 w-1/2 h-1/2 rounded-tr-full bg-slate-900 flex items-center justify-center transition-all duration-300 ease-out group hover:z-30 hover:scale-110 hover:translate-x-1 hover:-translate-y-1 hover:shadow-[0_15px_30px_rgba(0,0,0,0.8)] hover:bg-slate-800 active:scale-95"
            >
              <div style={{ transform: `rotate(${-rotation}rad)` }} className="transition-transform group-hover:scale-110">
                <Mic className="w-8 h-8 text-white stroke-[2.5]" />
              </div>
            </button>

            {/* --- CUADRANTE 3: ABAJO IZQUIERDA (CLIP DE ADJUNTOS) --- */}
            <button
              onClick={() => setShowSatellites(!showSatellites)}
              className="absolute bottom-0 left-0 w-1/2 h-1/2 rounded-bl-full bg-slate-900 flex items-center justify-center transition-all duration-300 ease-out group hover:z-30 hover:scale-110 hover:-translate-x-1 hover:translate-y-1 hover:shadow-[0_15px_30px_rgba(0,0,0,0.8)] hover:bg-slate-800 active:scale-95"
            >
              <div style={{ transform: `rotate(${-rotation}rad)` }} className="transition-transform group-hover:scale-110">
                <Paperclip className="w-8 h-8 text-white stroke-[2.5]" />
              </div>
            </button>

            {/* --- CUADRANTE 4: ABAJO DERECHA (HISTORIAL) --- */}
            <button
              onClick={() => {
                setShowSatellites(false);
                onHistoryOpen?.();
              }}
              className="absolute bottom-0 right-0 w-1/2 h-1/2 rounded-br-full bg-slate-900 flex items-center justify-center transition-all duration-300 ease-out group hover:z-30 hover:scale-110 hover:translate-x-1 hover:translate-y-1 hover:shadow-[0_15px_30px_rgba(0,0,0,0.8)] hover:bg-slate-800 active:scale-95"
            >
              <div style={{ transform: `rotate(${-rotation}rad)` }} className="transition-transform group-hover:scale-110">
                <History className="w-8 h-8 text-white stroke-[2.5]" />
              </div>
            </button>
          </div>

          {/* --- BOTONES SATÉLITE ANIMADOS (POP-OUT ORBITAL) --- */}
          
          {/* Satélite 1: Documento/Archivo */}
          <button
            onClick={() => {
              onFileUpload?.();
              setShowSatellites(false);
            }}
            className={`absolute top-1/2 left-1/2 -ml-6 -mt-6 w-12 h-12 rounded-full bg-slate-900 border-2 border-black shadow-[0_8px_20px_rgba(0,0,0,0.6)] flex items-center justify-center hover:scale-125 active:scale-95 transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] z-40 ${
              showSatellites 
                ? 'opacity-100 pointer-events-auto' 
                : 'opacity-0 pointer-events-none'
            }`}
            style={{
              transform: showSatellites
                ? `translate(${sat1X}px, ${sat1Y}px) scale(1)`
                : `translate(${clipX}px, ${clipY}px) scale(0)`,
              transitionDelay: showSatellites ? '0ms' : '50ms',
            }}
          >
            <FileText className="w-6 h-6 text-white stroke-[2]" />
          </button>

          {/* Satélite 2: Cámara/Foto */}
          <button
            onClick={() => {
              onCameraOpen?.();
              setShowSatellites(false);
            }}
            className={`absolute top-1/2 left-1/2 -ml-6 -mt-6 w-12 h-12 rounded-full bg-slate-900 border-2 border-black shadow-[0_8px_20px_rgba(0,0,0,0.6)] flex items-center justify-center hover:scale-125 active:scale-95 transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] z-40 ${
              showSatellites 
                ? 'opacity-100 pointer-events-auto' 
                : 'opacity-0 pointer-events-none'
            }`}
            style={{
              transform: showSatellites
                ? `translate(${sat2X}px, ${sat2Y}px) scale(1)`
                : `translate(${clipX}px, ${clipY}px) scale(0)`,
              transitionDelay: showSatellites ? '50ms' : '0ms',
            }}
          >
            <Camera className="w-6 h-6 text-white stroke-[2]" />
          </button>

        </div>
      </div>

      {/* --- ESTILOS DE ANIMACIÓN --- */}
      <style jsx global>{`
        @keyframes vibrate {
          0%, 100% { transform: translate(0, 0) rotate(0deg); }
          25% { transform: translate(-1.5px, 1px) rotate(-0.5deg); }
          50% { transform: translate(1px, -1.5px) rotate(0.5deg); }
          75% { transform: translate(-1px, -1px) rotate(-0.2deg); }
        }

        .animate-vibrate {
          animation: vibrate 2.5s ease-in-out infinite;
        }
      `}</style>
    </>
  );
}