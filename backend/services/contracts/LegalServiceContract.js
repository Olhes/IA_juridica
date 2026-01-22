/**
 * Contrato para el servicio de procesamiento legal
 * Define la interfaz que deben seguir todas las implementaciones
 */
class LegalServiceContract {
  /**
   * Procesa una consulta legal bilingüe
   * @param {string} query - La consulta del usuario
   * @param {string} language - Idioma de la consulta ('quechua' | 'spanish')
   * @param {Object} context - Contexto adicional del usuario
   * @returns {Promise<Object>} Respuesta procesada con ambos idiomas
   */
  async processLegalQuery(query, language, context = {}) {
    throw new Error('Method must be implemented');
  }

  /**
   * Valida si una consulta es apropiada para el sistema
   * @param {string} query - Consulta a validar
   * @returns {Promise<boolean>} True si es válida
   */
  async validateQuery(query) {
    throw new Error('Method must be implemented');
  }

  /**
   * Genera un informe PDF con la respuesta legal
   * @param {Object} legalResponse - Respuesta legal procesada
   * @param {Object} userData - Datos del usuario
   * @returns {Promise<Buffer>} Buffer del PDF generado
   */
  async generateLegalPDF(legalResponse, userData) {
    throw new Error('Method must be implemented');
  }
}

module.exports = LegalServiceContract;
