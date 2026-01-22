const OpenAI = require('openai');
const logger = require('../../utils/logger');

class OpenAIService {
  constructor() {
    this.openai = new OpenAI({
      apiKey: process.env.OPENAI_API_KEY,
    });
    this.model = process.env.OPENAI_MODEL || 'gpt-4';
  }

  /**
   * Procesa texto con OpenAI manteniendo contexto bilingüe
   * @param {string} prompt - Prompt para procesar
   * @param {Object} options - Opciones adicionales
   * @returns {Promise<string>} Respuesta procesada
   */
  async processText(prompt, options = {}) {
    try {
      const systemPrompt = this.buildSystemPrompt(options.language || 'spanish');
      
      const completion = await this.openai.chat.completions.create({
        model: this.model,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: prompt }
        ],
        temperature: 0.7,
        max_tokens: options.maxTokens || 1500,
      });

      return completion.choices[0].message.content;
    } catch (error) {
      logger.error('Error processing text with OpenAI:', error);
      throw new Error('Failed to process text with AI service');
    }
  }

  /**
   * Detecta el idioma del texto
   * @param {string} text - Texto a analizar
   * @returns {Promise<string>} Idioma detectado
   */
  async detectLanguage(text) {
    try {
      const prompt = `Detecta el idioma de este texto y responde SOLO con "quechua" o "spanish":
      
      Texto: "${text.substring(0, 200)}"`;
      
      const result = await this.processText(prompt, { maxTokens: 10 });
      return result.toLowerCase().includes('quechua') ? 'quechua' : 'spanish';
    } catch (error) {
      logger.error('Error detecting language:', error);
      return 'spanish'; // fallback
    }
  }

  /**
   * Traduce texto entre quechua y español
   * @param {string} text - Texto a traducir
   * @param {string} fromLanguage - Idioma origen
   * @param {string} toLanguage - Idioma destino
   * @returns {Promise<string>} Texto traducido
   */
  async translateText(text, fromLanguage, toLanguage) {
    try {
      const prompt = `Traduce el siguiente texto de ${fromLanguage} a ${toLanguage}. Mantén el mismo significado y tono:
      
      ${text}`;
      
      return await this.processText(prompt, { 
        language: toLanguage,
        maxTokens: 2000 
      });
    } catch (error) {
      logger.error('Error translating text:', error);
      throw new Error('Failed to translate text');
    }
  }

  /**
   * Construye el prompt del sistema según el contexto
   * @param {string} language - Idioma principal
   * @returns {string} Prompt del sistema
   */
  buildSystemPrompt(language) {
    const basePrompt = `Eres un asistente legal especializado en derecho digital, bilingüe en quechua y español. 
    Tu misión es proporcionar orientación legal básica y comprensible para comunidades rurales de los Andes.
    
    Directrices:
    - Responde siempre en ambos idiomas (quechua y español)
    - Usa lenguaje sencillo y claro
    - Enfócate en derecho digital: protección de datos, ciberseguridad, derechos digitales
    - Proporciona pasos prácticos y concretos
    - Incluye advertencias sobre consultar abogados para casos complejos
    - Respeta la cosmovisión andina en tus explicaciones
    
    Formato de respuesta:
    [ESPAÑOL]
    [Tu respuesta en español]
    
    [QUECHUA]
    [Tu respuesta en quechua]`;

    return basePrompt;
  }

  /**
   * Genera respuesta legal completa
   * @param {string} query - Consulta del usuario
   * @param {string} language - Idioma detectado
   * @returns {Promise<Object>} Respuesta estructurada
   */
  async generateLegalResponse(query, language) {
    try {
      const legalPrompt = `Consulta legal sobre derecho digital: ${query}
      
      Proporciona una respuesta completa que incluya:
      1. Explicación clara del concepto o problema
      2. Derechos que aplica la situación
      3. Pasos concretos que debe seguir la persona
      4. Riesgos o advertencias importantes
      5. Cuándo consultar a un abogado profesional`;

      const response = await this.processText(legalPrompt, { language });
      
      return {
        originalQuery: query,
        detectedLanguage: language,
        response: response,
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      logger.error('Error generating legal response:', error);
      throw new Error('Failed to generate legal response');
    }
  }
}

module.exports = OpenAIService;
