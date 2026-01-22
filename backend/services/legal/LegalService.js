const LegalServiceContract = require('../contracts/LegalServiceContract');
const OpenAIService = require('../openai/OpenAIService');
const PDFService = require('../pdf/PDFService');
const TranslationService = require('../translation/TranslationService');
const logger = require('../../utils/logger');

class LegalService extends LegalServiceContract {
  constructor() {
    super();
    this.openaiService = new OpenAIService();
    this.pdfService = new PDFService();
    this.translationService = new TranslationService();
  }

  /**
   * Procesa una consulta legal bilingüe completa
   * @param {string} query - La consulta del usuario
   * @param {string} language - Idioma de la consulta ('quechua' | 'spanish')
   * @param {Object} context - Contexto adicional del usuario
   * @returns {Promise<Object>} Respuesta procesada con ambos idiomas
   */
  async processLegalQuery(query, language, context = {}) {
    try {
      logger.info(`Processing legal query in ${language}: ${query.substring(0, 100)}...`);

      // Validar consulta
      const isValid = await this.validateQuery(query);
      if (!isValid) {
        throw new Error('Query validation failed - inappropriate content or format');
      }

      // Detectar idioma si no se proporciona
      const detectedLanguage = language || await this.openaiService.detectLanguage(query);

      // Generar respuesta legal con OpenAI
      const legalResponse = await this.openaiService.generateLegalResponse(query, detectedLanguage);

      // Procesar respuesta bilingüe
      const processedResponse = await this.processBilingualResponse(legalResponse);

      // Guardar consulta en base de datos (opcional)
      await this.saveQuery(query, processedResponse, context);

      return {
        success: true,
        query: query,
        language: detectedLanguage,
        response: processedResponse,
        timestamp: new Date().toISOString(),
        context: context
      };

    } catch (error) {
      logger.error('Error in processLegalQuery:', error);
      return {
        success: false,
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }

  /**
   * Valida si una consulta es apropiada para el sistema
   * @param {string} query - Consulta a validar
   * @returns {Promise<boolean>} True si es válida
   */
  async validateQuery(query) {
    try {
      // Validaciones básicas
      if (!query || query.trim().length < 10) {
        return false;
      }

      if (query.length > 2000) {
        return false;
      }

      // Validar que sea sobre temas legales apropiados
      const legalTopics = [
        'datos', 'privacidad', 'ciberseguridad', 'contratos', 'estafa', 'fraude',
        'derechos', 'protección', 'internet', 'digital', 'online', 'redes sociales',
        'email', 'contraseña', 'identidad', 'robo', 'acoso', 'ciberacoso'
      ];

      const queryLower = query.toLowerCase();
      const hasLegalTopic = legalTopics.some(topic => queryLower.includes(topic));

      if (!hasLegalTopic) {
        // Usar OpenAI para validar si es una consulta legal
        const validationPrompt = `Esta consulta es sobre derecho digital o temas legales relacionados? Responde SOLO "si" o "no":
        
        "${query}"`;
        
        const validation = await this.openaiService.processText(validationPrompt, { maxTokens: 5 });
        return validation.toLowerCase().includes('si');
      }

      return true;
    } catch (error) {
      logger.error('Error validating query:', error);
      return false;
    }
  }

  /**
   * Genera un informe PDF con la respuesta legal
   * @param {Object} legalResponse - Respuesta legal procesada
   * @param {Object} userData - Datos del usuario
   * @returns {Promise<Buffer>} Buffer del PDF generado
   */
  async generateLegalPDF(legalResponse, userData = {}) {
    try {
      logger.info('Generating PDF for legal response');
      
      const pdfData = {
        query: legalResponse.query,
        response: legalResponse.response,
        timestamp: legalResponse.timestamp,
        userData: userData,
        language: legalResponse.language
      };

      return await this.pdfService.generateLegalReport(pdfData);
    } catch (error) {
      logger.error('Error generating PDF:', error);
      throw new Error('Failed to generate PDF report');
    }
  }

  /**
   * Procesa respuesta para asegurar formato bilingüe correcto
   * @param {Object} legalResponse - Respuesta de OpenAI
   * @returns {Promise<Object>} Respuesta procesada
   */
  async processBilingualResponse(legalResponse) {
    try {
      const response = legalResponse.response;
      
      // Extraer secciones en español y quechua
      const spanishSection = this.extractLanguageSection(response, 'ESPAÑOL');
      const quechuaSection = this.extractLanguageSection(response, 'QUECHUA');

      // Si falta alguna sección, traducir
      let finalSpanish = spanishSection;
      let finalQuechua = quechuaSection;

      if (!finalSpanish && finalQuechua) {
        finalSpanish = await this.translationService.translateText(
          finalQuechua, 'quechua', 'spanish'
        );
      }

      if (!finalQuechua && finalSpanish) {
        finalQuechua = await this.translationService.translateText(
          finalSpanish, 'spanish', 'quechua'
        );
      }

      return {
        spanish: finalSpanish || 'Respuesta no disponible',
        quechua: finalQuechua || 'Respuesta no disponible',
        raw: response
      };
    } catch (error) {
      logger.error('Error processing bilingual response:', error);
      throw new Error('Failed to process bilingual response');
    }
  }

  /**
   * Extrae sección de idioma específica de la respuesta
   * @param {string} response - Respuesta completa
   * @param {string} language - Idioma a extraer
   * @returns {string|null} Sección extraída
   */
  extractLanguageSection(response, language) {
    try {
      const regex = new RegExp(`\\[${language}\\]([\\s\\S]*?)(?=\\[|$)`, 'i');
      const match = response.match(regex);
      return match ? match[1].trim() : null;
    } catch (error) {
      logger.error(`Error extracting ${language} section:`, error);
      return null;
    }
  }

  /**
   * Guarda consulta en base de datos
   * @param {string} query - Consulta original
   * @param {Object} response - Respuesta procesada
   * @param {Object} context - Contexto adicional
   */
  async saveQuery(query, response, context) {
    try {
      // Implementar guardado en base de datos
      // Por ahora solo log
      logger.info(`Query saved: ${query.substring(0, 50)}...`);
    } catch (error) {
      logger.error('Error saving query:', error);
    }
  }
}

module.exports = LegalService;
