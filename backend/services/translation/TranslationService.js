const OpenAIService = require('../openai/OpenAIService');
const logger = require('../../utils/logger');

class TranslationService {
  constructor() {
    this.openaiService = new OpenAIService();
    this.cache = new Map(); // Cache simple para traducciones frecuentes
  }

  /**
   * Traduce texto entre quechua y español
   * @param {string} text - Texto a traducir
   * @param {string} fromLanguage - Idioma origen ('quechua' | 'spanish')
   * @param {string} toLanguage - Idioma destino ('quechua' | 'spanish')
   * @returns {Promise<string>} Texto traducido
   */
  async translateText(text, fromLanguage, toLanguage) {
    try {
      // Validar idiomas
      if (fromLanguage === toLanguage) {
        return text;
      }

      // Generar clave de cache
      const cacheKey = `${fromLanguage}-${toLanguage}-${text.substring(0, 100)}`;
      
      // Verificar cache
      if (this.cache.has(cacheKey)) {
        logger.debug(`Cache hit for translation: ${cacheKey}`);
        return this.cache.get(cacheKey);
      }

      // Realizar traducción
      const translatedText = await this.openaiService.translateText(text, fromLanguage, toLanguage);

      // Guardar en cache
      if (this.cache.size > 1000) {
        // Limpiar cache si es muy grande
        this.cache.clear();
      }
      this.cache.set(cacheKey, translatedText);

      logger.info(`Translation completed: ${fromLanguage} -> ${toLanguage}`);
      return translatedText;

    } catch (error) {
      logger.error('Error in translation service:', error);
      throw new Error(`Translation failed: ${error.message}`);
    }
  }

  /**
   * Detecta automáticamente el idioma de un texto
   * @param {string} text - Texto a analizar
   * @returns {Promise<string>} Idioma detectado ('quechua' | 'spanish')
   */
  async detectLanguage(text) {
    try {
      // Palabras clave en quechua para detección rápida
      const quechuaKeywords = [
        'imata', 'pipas', 'maypi', 'kay', 'puni', 'mana', 'allin', 'sumaq',
        'yachay', 'llankay', 'muna', 'kani', 'kanki', 'kanchik', 'kankuna',
        'ñuqa', 'qam', 'pay', 'ñuqanchik', 'qamkuna', 'paykuna'
      ];

      const textLower = text.toLowerCase();
      const hasQuechuaKeywords = quechuaKeywords.some(keyword => 
        textLower.includes(keyword)
      );

      if (hasQuechuaKeywords) {
        return 'quechua';
      }

      // Usar OpenAI para detección más precisa
      return await this.openaiService.detectLanguage(text);

    } catch (error) {
      logger.error('Error detecting language:', error);
      return 'spanish'; // fallback seguro
    }
  }

  /**
   * Traduce texto completo manteniendo formato y estructura
   * @param {string} text - Texto a traducir
   * @param {string} targetLanguage - Idioma destino
   * @returns {Promise<string>} Texto traducido con formato
   */
  async translateFormattedText(text, targetLanguage) {
    try {
      const sourceLanguage = await this.detectLanguage(text);
      
      if (sourceLanguage === targetLanguage) {
        return text;
      }

      // Dividir texto en líneas para mantener formato
      const lines = text.split('\n');
      const translatedLines = [];

      for (const line of lines) {
        if (line.trim() === '') {
          translatedLines.push(line);
          continue;
        }

        // Traducir línea manteniendo estructura
        const translatedLine = await this.translateText(line, sourceLanguage, targetLanguage);
        translatedLines.push(translatedLine);
      }

      return translatedLines.join('\n');

    } catch (error) {
      logger.error('Error translating formatted text:', error);
      throw new Error(`Formatted translation failed: ${error.message}`);
    }
  }

  /**
   * Valida si una traducción es confiable
   * @param {string} original - Texto original
   * @param {string} translated - Texto traducido
   * @returns {Promise<number>} Score de confianza (0-1)
   */
  async validateTranslation(original, translated) {
    try {
      // Traducción inversa para validar
      const detectedLang = await this.detectLanguage(original);
      const reverseTranslation = await this.translateText(
        translated, 
        detectedLang === 'spanish' ? 'quechua' : 'spanish',
        detectedLang
      );

      // Comparar similitud (implementación simple)
      const similarity = this.calculateSimilarity(original, reverseTranslation);
      
      return Math.min(similarity, 1.0);

    } catch (error) {
      logger.error('Error validating translation:', error);
      return 0.5; // Score neutro en caso de error
    }
  }

  /**
   * Calcula similitud entre dos textos (implementación simple)
   * @param {string} text1 - Primer texto
   * @param {string} text2 - Segundo texto
   * @returns {number} Score de similitud (0-1)
   */
  calculateSimilarity(text1, text2) {
    const words1 = text1.toLowerCase().split(' ');
    const words2 = text2.toLowerCase().split(' ');
    
    const intersection = words1.filter(word => words2.includes(word));
    const union = [...new Set([...words1, ...words2])];
    
    return intersection.length / union.length;
  }

  /**
   * Limpia el cache de traducciones
   */
  clearCache() {
    this.cache.clear();
    logger.info('Translation cache cleared');
  }

  /**
   * Obtiene estadísticas del cache
   * @returns {Object} Estadísticas
   */
  getCacheStats() {
    return {
      size: this.cache.size,
      keys: Array.from(this.cache.keys())
    };
  }
}

module.exports = TranslationService;
