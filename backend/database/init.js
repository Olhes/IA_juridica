const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const fs = require('fs');
const logger = require('../utils/logger');

const DB_PATH = process.env.DB_PATH || path.join(__dirname, 'juridica.db');

/**
 * Inicializa la base de datos y crea las tablas necesarias
 */
async function initializeDatabase() {
  return new Promise((resolve, reject) => {
    try {
      // Asegurar que el directorio de la base de datos exista
      const dbDir = path.dirname(DB_PATH);
      if (!fs.existsSync(dbDir)) {
        fs.mkdirSync(dbDir, { recursive: true });
      }

      const db = new sqlite3.Database(DB_PATH, (err) => {
        if (err) {
          logger.error('Error opening database:', err);
          reject(err);
          return;
        }
        logger.info(`Connected to SQLite database at ${DB_PATH}`);
      });

      // Crear tablas
      db.serialize(() => {
        // Tabla de consultas legales
        db.run(`
          CREATE TABLE IF NOT EXISTS legal_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            language TEXT NOT NULL CHECK (language IN ('spanish', 'quechua')),
            response_spanish TEXT,
            response_quechua TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            response_time_ms INTEGER,
            success BOOLEAN DEFAULT 1
          )
        `, (err) => {
          if (err) {
            logger.error('Error creating legal_queries table:', err);
            reject(err);
            return;
          }
          logger.info('Table legal_queries created or already exists');
        });

        // Tabla de estadísticas
        db.run(`
          CREATE TABLE IF NOT EXISTS daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE UNIQUE NOT NULL,
            total_queries INTEGER DEFAULT 0,
            spanish_queries INTEGER DEFAULT 0,
            quechua_queries INTEGER DEFAULT 0,
            avg_response_time REAL DEFAULT 0,
            successful_queries INTEGER DEFAULT 0,
            failed_queries INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
          )
        `, (err) => {
          if (err) {
            logger.error('Error creating daily_stats table:', err);
            reject(err);
            return;
          }
          logger.info('Table daily_stats created or already exists');
        });

        // Tabla de temas populares
        db.run(`
          CREATE TABLE IF NOT EXISTS popular_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            frequency INTEGER DEFAULT 1,
            last_mentioned DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
          )
        `, (err) => {
          if (err) {
            logger.error('Error creating popular_topics table:', err);
            reject(err);
            return;
          }
          logger.info('Table popular_topics created or already exists');
        });

        // Tabla de errores
        db.run(`
          CREATE TABLE IF NOT EXISTS error_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            error_type TEXT NOT NULL,
            error_message TEXT NOT NULL,
            query TEXT,
            ip_address TEXT,
            user_agent TEXT,
            stack_trace TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
          )
        `, (err) => {
          if (err) {
            logger.error('Error creating error_logs table:', err);
            reject(err);
            return;
          }
          logger.info('Table error_logs created or already exists');
        });

        // Crear índices para mejor rendimiento
        db.run(`
          CREATE INDEX IF NOT EXISTS idx_legal_queries_created_at 
          ON legal_queries(created_at)
        `, (err) => {
          if (err) {
            logger.error('Error creating index on legal_queries.created_at:', err);
          } else {
            logger.info('Index idx_legal_queries_created_at created or already exists');
          }
        });

        db.run(`
          CREATE INDEX IF NOT EXISTS idx_daily_stats_date 
          ON daily_stats(date)
        `, (err) => {
          if (err) {
            logger.error('Error creating index on daily_stats.date:', err);
          } else {
            logger.info('Index idx_daily_stats_date created or already exists');
          }
        });

        db.run(`
          CREATE INDEX IF NOT EXISTS idx_error_logs_created_at 
          ON error_logs(created_at)
        `, (err) => {
          if (err) {
            logger.error('Error creating index on error_logs.created_at:', err);
          } else {
            logger.info('Index idx_error_logs_created_at created or already exists');
          }
        });

      });

      db.close((err) => {
        if (err) {
          logger.error('Error closing database:', err);
          reject(err);
          return;
        }
        logger.info('Database initialization completed successfully');
        resolve();
      });

    } catch (error) {
      logger.error('Database initialization error:', error);
      reject(error);
    }
  });
}

/**
 * Guarda una consulta legal en la base de datos
 * @param {Object} queryData - Datos de la consulta
 */
async function saveLegalQuery(queryData) {
  return new Promise((resolve, reject) => {
    const db = new sqlite3.Database(DB_PATH);
    
    const stmt = db.prepare(`
      INSERT INTO legal_queries 
      (query, language, response_spanish, response_quechua, ip_address, user_agent, response_time_ms, success)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);

    stmt.run([
      queryData.query,
      queryData.language,
      queryData.response?.spanish || null,
      queryData.response?.quechua || null,
      queryData.ipAddress || null,
      queryData.userAgent || null,
      queryData.responseTime || null,
      queryData.success !== false ? 1 : 0
    ], function(err) {
      if (err) {
        logger.error('Error saving legal query:', err);
        reject(err);
      } else {
        logger.info(`Legal query saved with ID: ${this.lastID}`);
        resolve(this.lastID);
      }
    });

    stmt.finalize();
    db.close();
  });
}

/**
 * Actualiza estadísticas diarias
 * @param {Object} statsData - Datos de estadísticas
 */
async function updateDailyStats(statsData) {
  return new Promise((resolve, reject) => {
    const db = new sqlite3.Database(DB_PATH);
    
    const today = new Date().toISOString().split('T')[0];
    
    db.run(`
      INSERT OR REPLACE INTO daily_stats 
      (date, total_queries, spanish_queries, quechua_queries, avg_response_time, successful_queries, failed_queries)
      VALUES (?, 
        COALESCE((SELECT total_queries FROM daily_stats WHERE date = ?), 0) + 1,
        COALESCE((SELECT spanish_queries FROM daily_stats WHERE date = ?), 0) + ?,
        COALESCE((SELECT quechua_queries FROM daily_stats WHERE date = ?), 0) + ?,
        COALESCE((SELECT avg_response_time FROM daily_stats WHERE date = ?), 0),
        COALESCE((SELECT successful_queries FROM daily_stats WHERE date = ?), 0) + ?,
        COALESCE((SELECT failed_queries FROM daily_stats WHERE date = ?), 0) + ?
      )
    `, [
      today, today, today,
      statsData.language === 'spanish' ? 1 : 0,
      today, today, today,
      statsData.responseTime || 0,
      today, today,
      statsData.success ? 1 : 0,
      today, today,
      statsData.success ? 0 : 1
    ], function(err) {
      if (err) {
        logger.error('Error updating daily stats:', err);
        reject(err);
      } else {
        resolve();
      }
    });

    db.close();
  });
}

/**
 * Registra un error en la base de datos
 * @param {Object} errorData - Datos del error
 */
async function logError(errorData) {
  return new Promise((resolve, reject) => {
    const db = new sqlite3.Database(DB_PATH);
    
    const stmt = db.prepare(`
      INSERT INTO error_logs 
      (error_type, error_message, query, ip_address, user_agent, stack_trace)
      VALUES (?, ?, ?, ?, ?, ?)
    `);

    stmt.run([
      errorData.type || 'unknown',
      errorData.message || 'Unknown error',
      errorData.query || null,
      errorData.ipAddress || null,
      errorData.userAgent || null,
      errorData.stack || null
    ], function(err) {
      if (err) {
        logger.error('Error logging to database:', err);
        reject(err);
      } else {
        resolve(this.lastID);
      }
    });

    stmt.finalize();
    db.close();
  });
}

/**
 * Obtiene estadísticas generales
 * @returns {Promise<Object>} Estadísticas
 */
async function getGeneralStats() {
  return new Promise((resolve, reject) => {
    const db = new sqlite3.Database(DB_PATH);
    
    const stats = {
      totalQueries: 0,
      queriesToday: 0,
      spanishQueries: 0,
      quechuaQueries: 0,
      avgResponseTime: 0,
      successRate: 0
    };

    // Total de consultas
    db.get('SELECT COUNT(*) as total FROM legal_queries', (err, row) => {
      if (err) {
        reject(err);
        return;
      }
      stats.totalQueries = row.total;

      // Consultas de hoy
      const today = new Date().toISOString().split('T')[0];
      db.get(
        'SELECT COUNT(*) as today FROM legal_queries WHERE DATE(created_at) = ?',
        [today],
        (err, row) => {
          if (err) {
            reject(err);
            return;
          }
          stats.queriesToday = row.today;

          // Distribución por idioma
          db.get(`
            SELECT 
              SUM(CASE WHEN language = 'spanish' THEN 1 ELSE 0 END) as spanish,
              SUM(CASE WHEN language = 'quechua' THEN 1 ELSE 0 END) as quechua
            FROM legal_queries
          `, (err, row) => {
            if (err) {
              reject(err);
              return;
            }
            stats.spanishQueries = row.spanish || 0;
            stats.quechuaQueries = row.quechua || 0;

            // Tiempo de respuesta promedio y tasa de éxito
            db.get(`
              SELECT 
                AVG(response_time_ms) as avgTime,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as successRate
              FROM legal_queries 
              WHERE response_time_ms IS NOT NULL
            `, (err, row) => {
              if (err) {
                reject(err);
                return;
              }
              stats.avgResponseTime = Math.round(row.avgTime || 0);
              stats.successRate = Math.round((row.successRate || 0) * 100) / 100;

              db.close();
              resolve(stats);
            });
          });
        }
      );
    });
  });
}

module.exports = {
  initializeDatabase,
  saveLegalQuery,
  updateDailyStats,
  logError,
  getGeneralStats,
  DB_PATH
};
