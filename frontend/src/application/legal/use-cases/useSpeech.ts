import { useState, useRef, useCallback, useEffect } from 'react';

const VOICE_LANG = 'es-PE'; // Español Perú para Web Speech API
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export function useSpeechToText(onFinalText: (text: string) => void, onEnd?: () => void) {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const recRef = useRef<any>(null);
  const callbackRef = useRef(onFinalText);
  const onEndRef = useRef(onEnd);
  callbackRef.current = onFinalText;
  onEndRef.current = onEnd;

  const supported =
    typeof window !== 'undefined' &&
    !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);

  console.log('[useSpeechToText] supported:', supported);
  console.log('[useSpeechToText] SpeechRecognition:', typeof window !== 'undefined' ? (window as any).SpeechRecognition : 'N/A');
  console.log('[useSpeechToText] webkitSpeechRecognition:', typeof window !== 'undefined' ? (window as any).webkitSpeechRecognition : 'N/A');

  const start = useCallback(() => {
    console.log('[useSpeechToText] start() called');
    if (!supported) {
      alert('Tu navegador no soporta voz. Usa Chrome o Edge.');
      return;
    }
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    console.log('[useSpeechToText] Creating SpeechRecognition instance');
    const rec = new SR();
    rec.lang = VOICE_LANG;
    rec.interimResults = true;
    rec.continuous = false;

    rec.onresult = (e: any) => {
      console.log('[useSpeechToText] onresult:', e);
      let finalText = '';
      let partial = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalText += t;
        else partial += t;
      }
      setInterim(partial);
      if (finalText) callbackRef.current(finalText.trim());
    };
    rec.onend = () => {
      console.log('[useSpeechToText] onend');
      setListening(false);
      setInterim('');
      onEndRef.current?.();
    };
    rec.onerror = (e: any) => {
      console.error('[useSpeechToText] Error de voz:', e.error);
      if (e.error === 'not-allowed') alert('Permite el micrófono en el navegador.');
      setListening(false);
    };

    recRef.current = rec;
    console.log('[useSpeechToText] Starting recognition');
    rec.start();
    setListening(true);
  }, [supported]);

  const stop = useCallback(() => recRef.current?.stop(), []);

  return { supported, listening, interim, start, stop };
}

/* ───────── TEXTO → VOZ (la IA habla) ───────── */
function limpiarTexto(md: string) {
  return md
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[*_#>`~]/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

export function useTextToSpeech() {
  const [speaking, setSpeaking] = useState(false);
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  const stop = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [supported]);

  const speak = useCallback(
    (text: string) => {
      if (!supported) return;
      window.speechSynthesis.cancel();

      const voices = window.speechSynthesis.getVoices();
      const voice =
        voices.find((v) => v.lang === 'es-PE') ||
        voices.find((v) => v.lang === 'es-419') ||
        voices.find((v) => v.lang.startsWith('es'));

      // Se divide en frases porque Chrome corta los textos muy largos.
      const frases = limpiarTexto(text).match(/[^.!?]+[.!?]*/g) || [];
      frases.forEach((frase, i) => {
        const u = new SpeechSynthesisUtterance(frase.trim());
        u.lang = VOICE_LANG;
        if (voice) u.voice = voice;
        u.rate = 0.95;
        if (i === 0) u.onstart = () => setSpeaking(true);
        if (i === frases.length - 1) {
          u.onend = () => setSpeaking(false);
          u.onerror = () => setSpeaking(false);
        }
        window.speechSynthesis.speak(u);
      });
    },
    [supported],
  );

  useEffect(() => () => stop(), [stop]);

  return { supported, speaking, speak, stop };
}

/* ───────── TEXTO → VOZ PARA QUECHUA (MMS-TTS) ───────── */
export function useQuechuaTextToSpeech() {
  const [speaking, setSpeaking] = useState(false);
  const [loading, setLoading] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const stop = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    setSpeaking(false);
  }, []);

  const speak = useCallback(async (text: string) => {
    try {
      setLoading(true);
      stop();

      console.log('[useQuechuaTextToSpeech] Requesting TTS for:', text.substring(0, 50));

      const response = await fetch(`${API_BASE}/tts/synthesize`, {
        method: 'POST',
        credentials: 'include',  // Importante: incluir cookies httpOnly para autenticación
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text,
          language: 'quechua',
        }),
      });

      console.log('[useQuechuaTextToSpeech] Response status:', response.status);

      if (!response.ok) {
        const errorText = await response.text();
        console.error('[useQuechuaTextToSpeech] Error response:', errorText);
        throw new Error(`Failed to synthesize audio: ${response.status}`);
      }

      const audioBlob = await response.blob();
      console.log('[useQuechuaTextToSpeech] Audio blob size:', audioBlob.size);
      const audioUrl = URL.createObjectURL(audioBlob);

      const audio = new Audio(audioUrl);
      audioRef.current = audio;

      audio.onplay = () => {
        console.log('[useQuechuaTextToSpeech] Audio playing');
        setSpeaking(true);
      };
      audio.onended = () => {
        console.log('[useQuechuaTextToSpeech] Audio ended');
        setSpeaking(false);
        URL.revokeObjectURL(audioUrl);
      };
      audio.onerror = (e) => {
        console.error('[useQuechuaTextToSpeech] Audio error:', e);
        setSpeaking(false);
        URL.revokeObjectURL(audioUrl);
      };

      audio.play();
    } catch (error) {
      console.error('Error en TTS de Quechua:', error);
      alert('Error al generar audio en Quechua: ' + (error as Error).message);
    } finally {
      setLoading(false);
    }
  }, [stop]);

  useEffect(() => () => stop(), [stop]);

  return { supported: true, speaking, loading, speak, stop };
}
