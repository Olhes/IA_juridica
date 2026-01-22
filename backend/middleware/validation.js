const Joi = require('joi');
const logger = require('../utils/logger');

/**
 * Esquemas de validación
 */
const schemas = {
  legalQuery: Joi.object({
    query: Joi.string()
      .min(10)
      .max(2000)
      .required()
      .messages({
        'string.min': 'La consulta debe tener al menos 10 caracteres',
        'string.max': 'La consulta no puede exceder 2000 caracteres',
        'any.required': 'La consulta es obligatoria'
      }),
    language: Joi.string()
      .valid('spanish', 'quechua')
      .optional()
      .messages({
        'any.only': 'El idioma debe ser "spanish" o "quechua"'
      }),
    context: Joi.object()
      .optional()
      .default({})
  }),

  pdfRequest: Joi.object({
    legalResponse: Joi.object()
      .required()
      .messages({
        'any.required': 'La respuesta legal es obligatoria'
      }),
    userData: Joi.object()
      .optional()
      .default({})
  }),

  languageDetection: Joi.object({
    text: Joi.string()
      .min(5)
      .max(1000)
      .required()
      .messages({
        'string.min': 'El texto debe tener al menos 5 caracteres',
        'string.max': 'El texto no puede exceder 1000 caracteres',
        'any.required': 'El texto es obligatorio'
      })
  })
};

/**
 * Middleware de validación para consultas legales
 */
const validateLegalQuery = (req, res, next) => {
  try {
    const { error, value } = schemas.legalQuery.validate(req.body);
    
    if (error) {
      logger.warn(`Validation error: ${error.details[0].message}`);
      return res.status(400).json({
        success: false,
        error: 'Validation failed',
        details: error.details[0].message
      });
    }

    // Sanitización adicional
    value.query = sanitizeInput(value.query);
    
    req.body = value;
    next();
  } catch (error) {
    logger.error('Validation middleware error:', error);
    res.status(500).json({
      success: false,
      error: 'Validation error'
    });
  }
};

/**
 * Middleware de validación para generación de PDF
 */
const validatePDFRequest = (req, res, next) => {
  try {
    const { error, value } = schemas.pdfRequest.validate(req.body);
    
    if (error) {
      logger.warn(`PDF validation error: ${error.details[0].message}`);
      return res.status(400).json({
        success: false,
        error: 'PDF validation failed',
        details: error.details[0].message
      });
    }

    req.body = value;
    next();
  } catch (error) {
    logger.error('PDF validation middleware error:', error);
    res.status(500).json({
      success: false,
      error: 'PDF validation error'
    });
  }
};

/**
 * Middleware de validación para detección de idioma
 */
const validateLanguageDetection = (req, res, next) => {
  try {
    const { error, value } = schemas.languageDetection.validate(req.body);
    
    if (error) {
      logger.warn(`Language detection validation error: ${error.details[0].message}`);
      return res.status(400).json({
        success: false,
        error: 'Language detection validation failed',
        details: error.details[0].message
      });
    }

    value.text = sanitizeInput(value.text);
    req.body = value;
    next();
  } catch (error) {
    logger.error('Language detection validation error:', error);
    res.status(500).json({
      success: false,
      error: 'Language detection validation error'
    });
  }
};

/**
 * Función de sanitización de entrada
 * @param {string} input - Texto a sanitizar
 * @returns {string} Texto sanitizado
 */
function sanitizeInput(input) {
  if (typeof input !== 'string') {
    return '';
  }

  return input
    .trim()
    // Eliminar scripts y HTML potencialmente peligroso
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/<[^>]*>/g, '')
    // Normalizar espacios
    .replace(/\s+/g, ' ')
    // Eliminar caracteres de control
    .replace(/[\x00-\x1F\x7F]/g, '');
}

/**
 * Middleware de validación genérico
 * @param {Object} schema - Esquema de Joi
 * @param {string} source - 'body', 'query', 'params'
 */
const validate = (schema, source = 'body') => {
  return (req, res, next) => {
    try {
      const { error, value } = schema.validate(req[source]);
      
      if (error) {
        logger.warn(`Validation error in ${source}: ${error.details[0].message}`);
        return res.status(400).json({
          success: false,
          error: 'Validation failed',
          details: error.details[0].message,
          source: source
        });
      }

      req[source] = value;
      next();
    } catch (error) {
      logger.error(`Validation middleware error in ${source}:`, error);
      res.status(500).json({
        success: false,
        error: 'Validation error'
      });
    }
  };
};

/**
 * Middleware de validación de límites de tamaño
 */
const validateSizeLimits = (req, res, next) => {
  try {
    const contentLength = req.get('content-length');
    
    if (contentLength && parseInt(contentLength) > 10 * 1024 * 1024) { // 10MB
      return res.status(413).json({
        success: false,
        error: 'Request entity too large',
        message: 'Maximum request size is 10MB'
      });
    }

    next();
  } catch (error) {
    logger.error('Size validation error:', error);
    res.status(500).json({
      success: false,
      error: 'Size validation error'
    });
  }
};

/**
 * Middleware de validación de origen (CORS básico)
 */
const validateOrigin = (req, res, next) => {
  try {
    const origin = req.get('origin');
    const allowedOrigins = [
      'http://localhost:3000',
      'http://localhost:3001',
      process.env.FRONTEND_URL
    ].filter(Boolean);

    if (allowedOrigins.length > 0 && origin && !allowedOrigins.includes(origin)) {
      logger.warn(`Unauthorized origin: ${origin}`);
      return res.status(403).json({
        success: false,
        error: 'Unauthorized origin'
      });
    }

    next();
  } catch (error) {
    logger.error('Origin validation error:', error);
    res.status(500).json({
      success: false,
      error: 'Origin validation error'
    });
  }
};

module.exports = {
  validateLegalQuery,
  validatePDFRequest,
  validateLanguageDetection,
  validate,
  validateSizeLimits,
  validateOrigin,
  schemas
};
