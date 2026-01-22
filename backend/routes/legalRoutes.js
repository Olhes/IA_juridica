const express = require('express');
const router = express.Router();
const LegalService = require('../services/legal/LegalService');
const { validateLegalQuery } = require('../middleware/validation');
const rateLimit = require('express-rate-limit');
const logger = require('../utils/logger');

const legalService = new LegalService();

// Rate limiting específico para endpoints legales
const legalLimiter = rateLimit({
  windowMs: 5 * 60 * 1000, // 5 minutos
  max: 10, // máximo 10 consultas por IP
  message: {
    error: 'Too many legal queries. Please wait before making another request.',
    retryAfter: '5 minutes'
  }
});

/**
 * @route   POST /api/legal/consult
 * @desc    Procesa una consulta legal bilingüe
 * @access  Public
 */
router.post('/consult', legalLimiter, validateLegalQuery, async (req, res) => {
  try {
    const { query, language, context } = req.body;

    logger.info(`Legal consultation request from ${req.ip}: ${query.substring(0, 50)}...`);

    const result = await legalService.processLegalQuery(query, language, context);

    if (result.success) {
      res.status(200).json({
        success: true,
        data: result,
        message: 'Legal consultation processed successfully'
      });
    } else {
      res.status(400).json({
        success: false,
        error: result.error,
        message: 'Failed to process legal consultation'
      });
    }

  } catch (error) {
    logger.error('Error in legal consultation:', error);
    res.status(500).json({
      success: false,
      error: 'Internal server error',
      message: 'Failed to process consultation'
    });
  }
});

/**
 * @route   POST /api/legal/pdf
 * @desc    Genera PDF con respuesta legal
 * @access  Public
 */
router.post('/pdf', async (req, res) => {
  try {
    const { legalResponse, userData } = req.body;

    if (!legalResponse) {
      return res.status(400).json({
        success: false,
        error: 'Legal response is required'
      });
    }

    logger.info(`PDF generation request from ${req.ip}`);

    const pdfBuffer = await legalService.generateLegalPDF(legalResponse, userData);

    // Configurar headers para descarga
    const filename = `informe-legal-${Date.now()}.pdf`;
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
    res.setHeader('Content-Length', pdfBuffer.length);

    res.send(pdfBuffer);

  } catch (error) {
    logger.error('Error generating PDF:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to generate PDF',
      message: error.message
    });
  }
});

/**
 * @route   GET /api/legal/health
 * @desc    Verifica estado del servicio legal
 * @access  Public
 */
router.get('/health', (req, res) => {
  res.status(200).json({
    success: true,
    service: 'Legal Service',
    status: 'Operational',
    timestamp: new Date().toISOString(),
    version: '1.0.0'
  });
});

/**
 * @route   POST /api/language/detect
 * @desc    Detecta idioma del texto
 * @access  Public
 */
router.post('/language/detect', async (req, res) => {
  try {
    const { text } = req.body;

    if (!text || text.trim().length < 5) {
      return res.status(400).json({
        success: false,
        error: 'Text is required and must be at least 5 characters'
      });
    }

    const TranslationService = require('../services/translation/TranslationService');
    const translationService = new TranslationService();
    
    const detectedLanguage = await translationService.detectLanguage(text);

    res.status(200).json({
      success: true,
      data: {
        text: text.substring(0, 100) + '...',
        detectedLanguage: detectedLanguage,
        confidence: 'high'
      }
    });

  } catch (error) {
    logger.error('Error detecting language:', error);
    res.status(500).json({
      success: false,
      error: 'Language detection failed'
    });
  }
});

/**
 * @route   POST /api/legal/validate
 * @desc    Valida si una consulta es apropiada para el sistema
 * @access  Public
 */
router.post('/validate', async (req, res) => {
  try {
    const { query } = req.body;

    if (!query || query.trim().length < 10) {
      return res.status(400).json({
        success: false,
        error: 'Query must be at least 10 characters'
      });
    }

    const isValid = await legalService.validateQuery(query);

    res.status(200).json({
      success: true,
      data: {
        query: query.substring(0, 100) + '...',
        isValid: isValid,
        reason: isValid ? 'Query is appropriate for legal assistance' : 'Query may not be suitable for this system'
      }
    });

  } catch (error) {
    logger.error('Error validating query:', error);
    res.status(500).json({
      success: false,
      error: 'Query validation failed'
    });
  }
});

/**
 * @route   GET /api/legal/stats
 * @desc    Obtiene estadísticas del servicio (para admin)
 * @access  Private (implementar auth después)
 */
router.get('/stats', async (req, res) => {
  try {
    // Implementar estadísticas reales después
    const stats = {
      totalQueries: 0,
      queriesToday: 0,
      averageResponseTime: '0ms',
      topTopics: [],
      languageDistribution: {
        spanish: 0,
        quechua: 0
      }
    };

    res.status(200).json({
      success: true,
      data: stats
    });

  } catch (error) {
    logger.error('Error getting stats:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get statistics'
    });
  }
});

module.exports = router;
