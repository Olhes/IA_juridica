'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';
import { ChevronDown, Compass, FileCheck2, Heart, MessageSquare, Moon, ShieldCheck, Sparkles, Sun } from 'lucide-react';
import type { SupportedLanguage } from '../../domain/legal/types';
import { homeTranslations } from '../i18n/translations';

const LANGUAGE_STORAGE_KEY = 'preferredLanguage';

export function LegalAssistantPage() {
  const [currentLanguage, setCurrentLanguage] = useState<SupportedLanguage>('spanish');
  const [mounted, setMounted] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(0);
  const { resolvedTheme, setTheme } = useTheme();

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const savedLanguage = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (savedLanguage === 'spanish' || savedLanguage === 'quechua') {
      setCurrentLanguage(savedLanguage);
    }
  }, []);

  const handleLanguageChange = (language: SupportedLanguage) => {
    setCurrentLanguage(language);
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  };

  const isDark = resolvedTheme === 'dark';
  const t = homeTranslations[currentLanguage];

  const landing = {
    spanish: {
      badge: 'Asistente legal bilingue',
      heading: 'Tu punto de entrada para orientacion legal segura',
      body:
        'Recibe una guia clara sobre violencia familiar, pension de alimentos y medidas de proteccion. Luego continua en el chat para resolver tu caso paso a paso.',
      goChat: 'Ir al chat legal',
      howItWorks: 'Como funciona',
      steps: [
        'Describe tu situacion en lenguaje simple.',
        'Obtiene orientacion estructurada y accionable.',
        'Descarga un informe y continua tu seguimiento.',
      ],
      rights: 'Enfoque: acceso a la justicia para comunidades andinas.',
      darkLabel: 'Cambiar modo',
      faqTitle: 'Preguntas frecuentes',
      popularTitle: 'Temas populares',
      popularTopics: [
        'Denuncia por violencia familiar',
        'Solicitud de pension de alimentos',
        'Medidas de proteccion urgentes',
        'Orientacion para audiencia judicial',
      ],
      impactTitle: 'Lo que ofrece la plataforma',
      impacts: [
        { Icon: ShieldCheck, title: 'Guia accionable', text: 'Respuestas en pasos concretos para tu siguiente decision.' },
        { Icon: FileCheck2, title: 'Informe descargable', text: 'Genera un resumen para seguimiento y apoyo institucional.' },
        { Icon: Heart, title: 'Enfoque humano', text: 'Lenguaje claro y cercano para situaciones sensibles.' },
      ],
      finalCtaTitle: 'Lista o listo para iniciar tu consulta?',
      finalCtaBody: 'Entra al chat y describe tu caso. Te guiaremos con una ruta legal clara.',
      finalCtaButton: 'Comenzar ahora',
      galleryTitle: 'Vista previa de la aplicacion',
      galleryDescription: 'Estas capturas muestran el flujo real del asistente y la experiencia de consulta en el chat.',
      galleryLabels: ['Pantalla inicial del chat', 'Respuesta legal en conversacion'],
      faqs: [
        {
          q: 'La orientacion reemplaza a una abogada o abogado?',
          a: 'No. Esta herramienta es una guia inicial para entender opciones y pasos. Para decisiones legales, acude a asesoria profesional.',
        },
        {
          q: 'Que temas puedo consultar aqui?',
          a: 'Violencia familiar, pension de alimentos, medidas de proteccion y dudas generales de rutas legales en Peru.',
        },
        {
          q: 'Como continuo luego de recibir la respuesta?',
          a: 'Puedes ir al chat, profundizar tu caso y descargar un informe para organizar tu siguiente accion.',
        },
      ],
    },
    quechua: {
      badge: 'Iskay simipi yanapaq legal',
      heading: 'Legal orientacionman yaykuna punku',
      body:
        'Llakichikuy, alimentos, proteccionmanta sutinchasqa yanapayta chaskinki. Chaymanta chatman yaykuspa kasuykita paso paso allinchanki.',
      goChat: 'Legal chatman riy',
      howItWorks: 'Imaynam purin',
      steps: [
        'Kusaykita mana sasachakuspa willay.',
        'Ordenasqa, rurana yachachiyta chaskiy.',
        'Informe uraykachiy, qatiqninpi puriy.',
      ],
      rights: 'Sunqun: andinas llaqtakunapaq justicia yaykuy.',
      darkLabel: 'Modo tikray',
      faqTitle: 'Sapa kuti tapukuykuna',
      popularTitle: 'Aswan tapusqa temakuna',
      popularTopics: [
        'Llakichikuy willakuy',
        'Alimentos mañakuy',
        'Utqay proteccion mañakuy',
        'Audiencia judicioman orientacion',
      ],
      impactTitle: 'Plataformapa yanapaynin',
      impacts: [
        { Icon: ShieldCheck, title: 'Rurasqa guia', text: 'Kutichiykunam qatiqninpi ima rurayta sutita rikuchin.' },
        { Icon: FileCheck2, title: 'Informe uraykachina', text: 'Qillqasqa resumen qatiyninpaq yanapakuq.' },
        { Icon: Heart, title: 'Runa sunqunwan', text: 'Sutipaq simipi yanapay, sasachakuy pacha.' },
      ],
      finalCtaTitle: 'Tapukuyta qallariyta munankichu?',
      finalCtaBody: 'Chatman yaykuy hinaspa kasuykita willay. Sutinchasqa legal puriyta qochisun.',
      finalCtaButton: 'Kunan qallariy',
      galleryTitle: 'Aplicacionpa rikchaynin',
      galleryDescription: 'Kay capturakunam chatpi imayna purisqanman huk chiqaq qhawariyta qun.',
      galleryLabels: ['Chat qallariy pantalla', 'Rimaypi legal kutichiy'],
      faqs: [
        {
          q: 'Kay orientacionqa abogadota rantinchu?',
          a: 'Mana. Kayqa qallariy yanapaylla. Hatun legal desicionkunapaq profesional asesoriata maskay.',
        },
        {
          q: 'Ima temakunata tapuy atini?',
          a: 'Llakichikuy, alimentos, proteccion, hinallataq Peru legal puriymanta tapukuykunata.',
        },
        {
          q: 'Kutichiy chaskispa imatataq ruwani?',
          a: 'Chatman yaykuy, kasuykita aswan allinta qhaway, chaymanta informe uraykachiy qatiqninpaq.',
        },
      ],
    },
  } as const;

  const copy = landing[currentLanguage];
  const galleryImages = [
    '/Captura%20de%20pantalla%202026-04-06%20144848.png',
    '/Captura%20de%20pantalla%202026-04-06%20144955.png',
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-indigo-50/30 to-violet-50/20 dark:bg-none dark:bg-gray-950 transition-colors duration-300">
      <header className="sticky top-0 z-30 border-b border-slate-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto h-16 px-4 md:px-8 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center shadow">
              <MessageSquare className="w-5 h-5 text-white" />
            </div>
            <div className="leading-tight min-w-0">
              <p className="text-base font-bold text-slate-900 dark:text-slate-100 truncate">{t.title}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400 truncate">{t.tagline}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex bg-slate-100 dark:bg-gray-800 rounded-full p-0.5 gap-0.5">
              {(['spanish', 'quechua'] as SupportedLanguage[]).map((lang) => (
                <button
                  key={lang}
                  type="button"
                  onClick={() => handleLanguageChange(lang)}
                  className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all duration-200 ${currentLanguage === lang
                    ? 'bg-white dark:bg-gray-700 text-indigo-700 dark:text-indigo-300 shadow-sm'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
                    }`}
                >
                  {lang === 'spanish' ? 'Espanol' : 'Quechua'}
                </button>
              ))}
            </div>

            <button
              type="button"
              onClick={() => setTheme(isDark ? 'light' : 'dark')}
              aria-label={copy.darkLabel}
              className="w-9 h-9 flex items-center justify-center rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-slate-600 dark:text-slate-300 transition-all duration-200"
            >
              {!mounted ? <div className="w-4 h-4" /> : isDark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-indigo-500" />}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 md:px-8 py-10 md:py-14">
        <section className="relative overflow-hidden rounded-3xl border border-indigo-100 dark:border-indigo-900/60 bg-white/85 dark:bg-gray-900/90 shadow-xl shadow-indigo-100/40 dark:shadow-black/20 p-6 md:p-10 animate-fade-in">
          <div className="absolute -top-20 -right-20 w-56 h-56 rounded-full bg-indigo-500/10 blur-3xl" />
          <div className="absolute -bottom-24 -left-20 w-64 h-64 rounded-full bg-violet-500/10 blur-3xl" />

          <div className="relative max-w-3xl">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-900">
              <Sparkles className="w-3.5 h-3.5" />
              {copy.badge}
            </span>

            <h1 className="mt-4 text-3xl md:text-5xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 leading-tight">
              {copy.heading}
            </h1>
            <p className="mt-4 text-sm md:text-base text-slate-600 dark:text-slate-300 leading-relaxed">
              {copy.body}
            </p>

            <div className="mt-7 flex flex-wrap items-center gap-3">
              <Link
                href="/chat"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-md hover:shadow-lg hover:scale-[1.02] active:scale-[0.98] transition-all"
              >
                <MessageSquare className="w-4 h-4" />
                {copy.goChat}
              </Link>
              <a
                href="#como-funciona"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold border border-slate-300 dark:border-gray-700 bg-white/70 dark:bg-gray-900 text-slate-700 dark:text-slate-200 hover:border-indigo-400 dark:hover:border-indigo-600 hover:text-indigo-700 dark:hover:text-indigo-300 transition-colors"
              >
                <Compass className="w-4 h-4" />
                {copy.howItWorks}
              </a>
            </div>
          </div>
        </section>

        <section id="como-funciona" className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-3">
          {copy.steps.map((step) => (
            <article
              key={step}
              className="rounded-2xl border border-slate-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 p-4"
            >
              <ShieldCheck className="w-4 h-4 text-indigo-600 dark:text-indigo-400 mb-2" />
              <p className="text-sm text-slate-700 dark:text-slate-300">{step}</p>
            </article>
          ))}
        </section>

        <section className="mt-8 rounded-2xl border border-amber-200 dark:border-amber-900/50 bg-amber-50/70 dark:bg-amber-950/20 px-4 py-3">
          <p className="text-sm text-amber-800 dark:text-amber-300">{copy.rights}</p>
        </section>

        <section className="mt-8 grid grid-cols-1 lg:grid-cols-2 gap-4">
          <article className="rounded-2xl border border-slate-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 p-4 md:p-6">
            <h2 className="text-lg md:text-xl font-bold text-slate-900 dark:text-slate-100 mb-4">{copy.popularTitle}</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {copy.popularTopics.map((topic) => (
                <div
                  key={topic}
                  className="text-sm px-3 py-2 rounded-xl border border-indigo-200 dark:border-indigo-900/60 bg-indigo-50/60 dark:bg-indigo-950/20 text-indigo-800 dark:text-indigo-300"
                >
                  {topic}
                </div>
              ))}
            </div>
          </article>

          <article className="rounded-2xl border border-slate-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 p-4 md:p-6">
            <h2 className="text-lg md:text-xl font-bold text-slate-900 dark:text-slate-100 mb-4">{copy.impactTitle}</h2>
            <div className="space-y-3">
              {copy.impacts.map(({ Icon, title, text }) => (
                <div key={title} className="rounded-xl border border-slate-200 dark:border-gray-800 bg-slate-50/60 dark:bg-gray-950/50 p-3">
                  <div className="flex items-start gap-3">
                    <Icon className="w-4 h-4 mt-0.5 text-indigo-600 dark:text-indigo-400" />
                    <div>
                      <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">{title}</p>
                      <p className="text-sm text-slate-600 dark:text-slate-300">{text}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </article>
        </section>

        <section className="mt-8 rounded-2xl border border-slate-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 p-4 md:p-6">
          <h2 className="text-lg md:text-xl font-bold text-slate-900 dark:text-slate-100 mb-4">{copy.faqTitle}</h2>
          <div className="space-y-2">
            {copy.faqs.map((faq, idx) => {
              const isOpen = openFaq === idx;
              return (
                <article key={faq.q} className="rounded-xl border border-slate-200 dark:border-gray-800 bg-slate-50/60 dark:bg-gray-950/50 overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setOpenFaq(isOpen ? null : idx)}
                    className="w-full px-4 py-3 text-left flex items-center justify-between gap-3"
                  >
                    <span className="text-sm md:text-base font-semibold text-slate-800 dark:text-slate-200">{faq.q}</span>
                    <ChevronDown className={`w-4 h-4 text-slate-500 dark:text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                  </button>
                  {isOpen && (
                    <div className="px-4 pb-4">
                      <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">{faq.a}</p>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        </section>

        <section className="mt-8 rounded-2xl border border-slate-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 p-4 md:p-6">
          <h2 className="text-lg md:text-xl font-bold text-slate-900 dark:text-slate-100">{copy.galleryTitle}</h2>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{copy.galleryDescription}</p>

          <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
            {galleryImages.map((src, idx) => (
              <figure
                key={src}
                className="rounded-2xl overflow-hidden border border-slate-200 dark:border-gray-800 bg-slate-100 dark:bg-gray-950"
              >
                <div className="relative aspect-[16/9]">
                  <Image
                    src={src}
                    alt={copy.galleryLabels[idx]}
                    fill
                    sizes="(max-width: 1024px) 100vw, 50vw"
                    className="object-cover"
                    priority={idx === 0}
                  />
                </div>
                <figcaption className="px-3 py-2 text-xs text-slate-600 dark:text-slate-300 border-t border-slate-200 dark:border-gray-800">
                  {copy.galleryLabels[idx]}
                </figcaption>
              </figure>
            ))}
          </div>
        </section>

        <section className="mt-8 rounded-3xl border border-indigo-200 dark:border-indigo-900/60 bg-gradient-to-br from-indigo-600 to-violet-600 p-6 md:p-8 text-white">
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight">{copy.finalCtaTitle}</h2>
          <p className="mt-2 text-indigo-100 max-w-2xl">{copy.finalCtaBody}</p>
          <div className="mt-5">
            <Link
              href="/chat"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold bg-white text-indigo-700 hover:bg-indigo-50 transition-colors"
            >
              <MessageSquare className="w-4 h-4" />
              {copy.finalCtaButton}
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-slate-200 dark:border-gray-800 py-6">
        <div className="max-w-6xl mx-auto px-4 md:px-8 flex items-center justify-between gap-3 flex-wrap">
          <p className="text-sm text-slate-500 dark:text-slate-400">IA Juridica</p>
          <p className="text-sm text-slate-500 dark:text-slate-400">{t.footer}</p>
        </div>
      </footer>
    </div>
  );
}
