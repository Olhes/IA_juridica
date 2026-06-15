"""
Detector de idiomas especializado para español y quechua
Optimizado para variantes regionales y contexto rural peruano
"""

from typing import Dict, List, Optional, Tuple,Any
import re
from loguru import logger

try:
    from langdetect import detect, detect_langs
    from langdetect.lang_detect_exception import LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    logger.warning("langdetect no disponible. Usando detección basada en reglas.")
    LANGDETECT_AVAILABLE = False

from .language_config import LanguageConfig, LanguageCode

class LanguageDetector:
    """Detector de idiomas especializado en español/quechua"""
    
    def __init__(self):
        self.config = LanguageConfig()
        
        # Indicadores específicos para quechua
        self.quechua_indicators = {
            # Pronombres personales
            'pronouns': [
                'ñuqa', 'ni', 'ñuqapuni', 'ñuqam', 'ñuqari',
                'qam', 'kam', 'qampuni', 'qamri', 'qamkama',
                'pay', 'payri', 'paypuni', 'payqa', 'paykama',
                'ñuqanchik', 'ñuqayku', 'ñuqanchikpuni',
                'qamkuna', 'qamkunapuni', 'qamkunari',
                'paykuna', 'paykunapuni', 'paykunari'
            ],
            
            # Sufijos quechuas comunes
            'suffixes': [
                'kuna', 'puni', 'ri', 'lla', 'pi', 'pa', 'ta', 'manta', 'wan',
                'hina', 'kama', 'rayku', 'paq', 'n', 'pti', 'nku', 'sku', 'chka'
            ],
            
            # Palabras culturales
            'cultural': [
                'ayllu', 'pachamama', 'inti', 'quilla', 'apu', 'wamani',
                'chaska', 'kusi', 'sumaq', 'allin', 'munay', 'yuyay',
                'yachay', 'llankay', 'ruway', 'kawsay', 'tinkuy'
            ],
            
            # Verbos comunes
            'verbs': [
                'kani', 'kanki', 'kanku', 'kay', 'kachun', 'kachkani',
                'munani', 'munanki', 'munanku', 'munay', 'munachkani',
                'yachani', 'yachanki', 'yachanku', 'yachay', 'yachachkani',
                'ruwani', 'ruwanki', 'ruwanku', 'ruway', 'ruwachkani'
            ],
            
            # Números básicos
            'numbers': [
                'huk', 'iskay', 'kimsa', 'tawa', 'pichqa', 'suqta', 'qanchis',
                'pusaq', 'isqun', 'chunka', 'pachak', 'waranqa', 'hunu'
            ]
        }
        
        # Indicadores para español
        self.spanish_indicators = {
            'articles': ['el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas'],
            'prepositions': ['de', 'a', 'en', 'con', 'por', 'para', 'sin', 'sobre'],
            'conjunctions': ['y', 'o', 'pero', 'mas', 'aunque', 'sino'],
            'common_words': [
                'que', 'como', 'cuando', 'donde', 'porque', 'para', 'este', 'esta',
                'estos', 'estas', 'ser', 'estar', 'tener', 'hacer', 'poder', 'decir'
            ]
        }
        
        # Patrones de error comunes en quechua
        self.quechua_error_patterns = [
            r'\b(kani|kanki|kanku)\b',  # Verbo ser/estar
            r'\b(munani|munanki|munanku)\b',  # Verbo querer
            r'\b(yachani|yachanki|yachanku)\b',  # Verbo saber
            r'\b(ayllu|pachamama|intiquilla)\b',  # Términos culturales
            r'\b(huk|iskay|kimsa|tawa)\b',  # Números
        ]
        
        logger.info("LanguageDetector inicializado")
    
    def detect_language(self, text: str, fallback: str = "es") -> str:
        """
        Detecta el idioma del texto
        
        Args:
            text: Texto a analizar
            fallback: Idioma por defecto si no se puede detectar
            
        Returns:
            Código de idioma detectado
        """
        try:
            # Limpiar texto
            clean_text = self._clean_text(text)
            
            # Si el texto es muy corto, usar detección simple
            if len(clean_text) < self.config.MIN_TEXT_LENGTH_FOR_DETECTION:
                return self._simple_detection(clean_text, fallback)
            
            # Priorizar detección rule-based para Quechua
            # (langdetect NO soporta quechua, así que ejecutamos reglas primero)
            rule_result = self._rule_based_detection(clean_text, fallback)
            if rule_result == "qu":
                return "qu"
            
            # Usar detección automática para español y otros idiomas
            if LANGDETECT_AVAILABLE:
                auto_result = self._automatic_detection(clean_text)
                if auto_result:
                    return auto_result
            
            # Fallback a resultado de reglas
            return rule_result
            
        except Exception as e:
            logger.error(f"Error detectando idioma: {str(e)}")
            return fallback
    
    def _clean_text(self, text: str) -> str:
        """Limpia el texto para detección"""
        # Eliminar caracteres especiales y números
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\d+', ' ', text)
        # Eliminar espacios extra
        text = re.sub(r'\s+', ' ', text).strip()
        return text.lower()
    
    def _simple_detection(self, text: str, fallback: str) -> str:
        """Detección simple para textos cortos"""
        quechua_score = 0
        spanish_score = 0
        
        words = text.split()
        
        for word in words:
            # Verificar indicadores quechua
            if any(word in indicators for indicators in self.quechua_indicators.values()):
                quechua_score += 1
            
            # Verificar indicadores español
            if word in self.spanish_indicators['articles']:
                spanish_score += 2  # Mayor peso para artículos
            elif word in self.spanish_indicators['common_words']:
                spanish_score += 1
        
        return "qu" if quechua_score > spanish_score else fallback
    
    def _automatic_detection(self, text: str) -> Optional[str]:
        """Usa detección automática con langdetect"""
        try:
            # Detectar idioma
            detections = detect_langs(text)
            
            if not detections:
                return None
            
            top_detection = detections[0]
            
            # Verificar confianza
            if top_detection.prob >= self.config.DETECTION_CONFIDENCE_THRESHOLD:
                detected_lang = top_detection.lang
                
                # Mapear a nuestros códigos
                if detected_lang == 'es':
                    return 'es'
                elif detected_lang == 'qu':
                    return 'qu'
                elif detected_lang == 'ay':
                    return 'ay'
            
            return None
            
        except LangDetectException:
            return None
        except Exception as e:
            logger.warning(f"Error en detección automática: {str(e)}")
            return None
    
    def _rule_based_detection(self, text: str, fallback: str) -> str:
        """Detección basada en reglas específicas"""
        quechua_score = 0
        spanish_score = 0
        
        # Contar indicadores quechua
        for category, indicators in self.quechua_indicators.items():
            for indicator in indicators:
                if indicator in text:
                    weight = self._get_category_weight(category)
                    quechua_score += weight * text.count(indicator)
        
        # Contar indicadores español
        for category, indicators in self.spanish_indicators.items():
            for indicator in indicators:
                if indicator in text:
                    weight = self._get_category_weight(category)
                    spanish_score += weight * text.count(indicator)
        
        # Verificar patrones de error quechua
        for pattern in self.quechua_error_patterns:
            matches = len(re.findall(pattern, text))
            quechua_score += matches * 3  # Alto peso para patrones específicos
        
        # Calcular scores relativos
        total_words = len(text.split())
        quechua_ratio = quechua_score / max(total_words, 1)
        spanish_ratio = spanish_score / max(total_words, 1)
        
        # Decisión basada en ratios
        if quechua_ratio > spanish_ratio * 1.5:  # Margen de confianza
            return "qu"
        elif spanish_ratio > quechua_ratio * 1.2:
            return "es"
        else:
            # Si son cercanos, verificar características adicionales
            return self._tie_breaker(text, fallback)
    
    def _get_category_weight(self, category: str) -> float:
        """Obtiene peso para una categoría de indicadores"""
        weights = {
            'pronouns': 3.0,
            'verbs': 2.5,
            'cultural': 4.0,
            'numbers': 2.0,
            'suffixes': 1.5,
            'articles': 2.0,
            'prepositions': 1.0,
            'conjunctions': 1.0,
            'common_words': 1.5
        }
        return weights.get(category, 1.0)
    
    def _tie_breaker(self, text: str, fallback: str) -> str:
        """Desempate cuando los scores son similares"""
        # Verificar presencia de sufijos quechuas
        words = text.split()
        quechua_suffix_count = 0
        
        for word in words:
            for suffix in self.quechua_indicators['suffixes']:
                if word.endswith(suffix):
                    quechua_suffix_count += 1
                    break
        
        # Si hay sufijos quechuas, inclinar hacia quechua
        if quechua_suffix_count >= 2:
            return "qu"
        
        # Verificar estructura de oraciones (español suele tener más preposiciones)
        preposition_count = sum(1 for prep in self.spanish_indicators['prepositions'] 
                              if prep in text)
        
        if preposition_count >= 3:
            return "es"
        
        return fallback
    
    def detect_with_confidence(self, text: str) -> Tuple[str, float]:
        """
        Detecta idioma con nivel de confianza
        
        Returns:
            Tuple con (idioma_detectado, confianza)
        """
        try:
            # Limpiar texto
            clean_text = self._clean_text(text)
            
            if len(clean_text) < self.config.MIN_TEXT_LENGTH_FOR_DETECTION:
                return self.detect_language(text), 0.5
            
            # Calcular scores
            quechua_score = self._calculate_quechua_score(clean_text)
            spanish_score = self._calculate_spanish_score(clean_text)
            
            total_score = quechua_score + spanish_score
            
            if total_score == 0:
                return self.config.FALLBACK_LANGUAGE.value, 0.0
            
            # Determinar idioma y confianza
            if quechua_score > spanish_score:
                confidence = quechua_score / total_score
                return "qu", confidence
            else:
                confidence = spanish_score / total_score
                return "es", confidence
                
        except Exception as e:
            logger.error(f"Error en detección con confianza: {str(e)}")
            return self.config.FALLBACK_LANGUAGE.value, 0.0
    
    def _calculate_quechua_score(self, text: str) -> float:
        """Calcula score para quechua"""
        score = 0.0
        
        for category, indicators in self.quechua_indicators.items():
            weight = self._get_category_weight(category)
            for indicator in indicators:
                score += weight * text.count(indicator)
        
        return score
    
    def _calculate_spanish_score(self, text: str) -> float:
        """Calcula score para español"""
        score = 0.0
        
        for category, indicators in self.spanish_indicators.items():
            weight = self._get_category_weight(category)
            for indicator in indicators:
                score += weight * text.count(indicator)
        
        return score
    
    def detect_quechua_variant(self, text: str) -> Optional[str]:
        """
        Detecta variante regional del quechua
        
        Returns:
            Código de variante detectada o None
        """
        # Indicadores por variante
        variant_indicators = {
            'chanka': ['ayacucho', 'huamanga', 'wamanga'],
            'collao': ['puno', 'titikaka', 'juliaca'],
            'cusco': ['cusco', 'qosqo', 'cusqueño'],
            'ayacucho': ['ayacucho', 'huanta'],
            'puno': ['puno', 'juli', 'azangaro']
        }
        
        text_lower = text.lower()
        variant_scores = {}
        
        for variant, indicators in variant_indicators.items():
            score = sum(1 for indicator in indicators if indicator in text_lower)
            if score > 0:
                variant_scores[variant] = score
        
        if variant_scores:
            return max(variant_scores, key=variant_scores.get)
        
        return None
    
    def get_detection_stats(self, text: str) -> Dict[str, Any]:
        """Obtiene estadísticas detalladas de detección"""
        clean_text = self._clean_text(text)
        
        quechua_score = self._calculate_quechua_score(clean_text)
        spanish_score = self._calculate_spanish_score(clean_text)
        total_score = quechua_score + spanish_score
        
        detected_lang, confidence = self.detect_with_confidence(text)
        variant = self.detect_quechua_variant(text) if detected_lang == "qu" else None
        
        return {
            'detected_language': detected_lang,
            'confidence': confidence,
            'quechua_score': quechua_score,
            'spanish_score': spanish_score,
            'total_score': total_score,
            'text_length': len(text.split()),
            'quechua_variant': variant,
            'method': 'automatic' if LANGDETECT_AVAILABLE else 'rule_based',
            'indicators_found': {
                'quechua_pronouns': sum(1 for ind in self.quechua_indicators['pronouns'] 
                                      if ind in clean_text),
                'quechua_cultural': sum(1 for ind in self.quechua_indicators['cultural'] 
                                       if ind in clean_text),
                'spanish_articles': sum(1 for ind in self.spanish_indicators['articles'] 
                                       if ind in clean_text),
                'spanish_prepositions': sum(1 for ind in self.spanish_indicators['prepositions'] 
                                           if ind in clean_text)
            }
        }
    
    def is_mixed_language(self, text: str, threshold: float = 0.3) -> bool:
        """
        Detecta si el texto mezcla idiomas
        
        Args:
            text: Texto a analizar
            threshold: Umbral para considerar mezcla
            
        Returns:
            True si detecta mezcla de idiomas
        """
        stats = self.get_detection_stats(text)
        
        # Calcular proporciones
        total = stats['quechua_score'] + stats['spanish_score']
        
        if total == 0:
            return False
        
        quechua_ratio = stats['quechua_score'] / total
        spanish_ratio = stats['spanish_score'] / total
        
        # Considerar mezcla si ambos tienen proporción significativa
        return (quechua_ratio > threshold and spanish_ratio > threshold)
    
    def get_language_profile(self, text: str) -> Dict[str, Any]:
        """Obtiene perfil lingüístico completo del texto"""
        stats = self.get_detection_stats(text)
        
        profile = {
            'primary_language': stats['detected_language'],
            'confidence': stats['confidence'],
            'is_mixed': self.is_mixed_language(text),
            'word_count': stats['text_length'],
            'quechua_variant': stats['quechua_variant'],
            'dominance_ratio': max(
                stats['quechua_score'] / max(stats['total_score'], 1),
                stats['spanish_score'] / max(stats['total_score'], 1)
            ),
            'recommendations': []
        }
        
        # Agregar recomendaciones
        if profile['confidence'] < 0.6:
            profile['recommendations'].append("Baja confianza en detección de idioma")
        
        if profile['is_mixed']:
            profile['recommendations'].append("Texto mezcla español y quechua")
            profile['recommendations'].append("Considerar traducción selectiva")
        
        if stats['quechua_variant']:
            profile['recommendations'].append(f"Variante quechua detectada: {stats['quechua_variant']}")
        
        return profile