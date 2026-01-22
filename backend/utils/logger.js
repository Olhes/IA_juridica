const winston = require('winston');
const path = require('path');

// Definir niveles y colores personalizados
const logLevels = {
  error: 0,
  warn: 1,
  info: 2,
  http: 3,
  debug: 4
};

const logColors = {
  error: 'red',
  warn: 'yellow',
  info: 'green',
  http: 'magenta',
  debug: 'white'
};

// Agregar colores a winston
winston.addColors(logColors);

// Formato personalizado para logs
const logFormat = winston.format.combine(
  winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss:ms' }),
  winston.format.colorize({ all: true }),
  winston.format.printf(
    (info) => `${info.timestamp} ${info.level}: ${info.message}`
  )
);

// Formato para archivos (sin colores)
const fileLogFormat = winston.format.combine(
  winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss:ms' }),
  winston.format.errors({ stack: true }),
  winston.format.json()
);

// Crear el logger
const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  levels: logLevels,
  format: fileLogFormat,
  defaultMeta: { service: 'ia-juridica-backend' },
  transports: [
    // Archivo de errores
    new winston.transports.File({
      filename: path.join(__dirname, '../../logs/error.log'),
      level: 'error',
      maxsize: 5242880, // 5MB
      maxFiles: 5,
    }),
    // Archivo de todos los logs
    new winston.transports.File({
      filename: path.join(__dirname, '../../logs/combined.log'),
      maxsize: 5242880, // 5MB
      maxFiles: 5,
    })
  ],
});

// Si no estamos en producción, agregar consola
if (process.env.NODE_ENV !== 'production') {
  logger.add(new winston.transports.Console({
    format: logFormat
  }));
}

// Middleware para logging de requests HTTP
logger.httpLogger = (req, res, next) => {
  const start = Date.now();
  
  res.on('finish', () => {
    const duration = Date.now() - start;
    const message = `${req.method} ${req.originalUrl} ${res.statusCode} - ${duration}ms - ${req.ip}`;
    
    if (res.statusCode >= 400) {
      logger.warn(message);
    } else {
      logger.http(message);
    }
  });
  
  next();
};

// Función para loggear errores específicos del servicio
logger.logLegalError = (error, query, userId = null) => {
  logger.error({
    type: 'legal_service_error',
    error: error.message,
    stack: error.stack,
    query: query ? query.substring(0, 100) : null,
    userId: userId,
    timestamp: new Date().toISOString()
  });
};

// Función para loggear consultas legales
logger.logLegalQuery = (query, language, responseTime, userId = null) => {
  logger.info({
    type: 'legal_query',
    query: query.substring(0, 100),
    language: language,
    responseTime: `${responseTime}ms`,
    userId: userId,
    timestamp: new Date().toISOString()
  });
};

// Función para loggear generación de PDFs
logger.logPDFGeneration = (success, fileSize, userId = null) => {
  logger.info({
    type: 'pdf_generation',
    success: success,
    fileSize: fileSize ? `${fileSize} bytes` : null,
    userId: userId,
    timestamp: new Date().toISOString()
  });
};

// Función para loggear traducciones
logger.logTranslation = (fromLang, toLang, textLength, cacheHit = false) => {
  logger.debug({
    type: 'translation',
    fromLanguage: fromLang,
    toLanguage: toLang,
    textLength: textLength,
    cacheHit: cacheHit,
    timestamp: new Date().toISOString()
  });
};

// Función para loggear eventos de seguridad
logger.logSecurityEvent = (event, details, ip = null) => {
  logger.warn({
    type: 'security_event',
    event: event,
    details: details,
    ip: ip,
    timestamp: new Date().toISOString()
  });
};

// Manejo de excepciones no capturadas
logger.exceptions.handle(
  new winston.transports.File({
    filename: path.join(__dirname, '../../logs/exceptions.log'),
    maxsize: 5242880,
    maxFiles: 5,
  })
);

// Manejo de promesas rechazadas no manejadas
process.on('unhandledRejection', (reason, promise) => {
  logger.error('Unhandled Rejection at:', promise, 'reason:', reason);
});

module.exports = logger;
