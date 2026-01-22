const PDFDocument = require('pdfkit');
const fs = require('fs');
const path = require('path');
const logger = require('../../utils/logger');

class PDFService {
  constructor() {
    this.outputDir = path.join(__dirname, '../../temp');
    this.ensureOutputDir();
  }

  /**
   * Genera un informe PDF con la respuesta legal
   * @param {Object} data - Datos para el PDF
   * @returns {Promise<Buffer>} Buffer del PDF generado
   */
  async generateLegalReport(data) {
    return new Promise((resolve, reject) => {
      try {
        const doc = new PDFDocument({
          size: 'A4',
          margins: { top: 50, bottom: 50, left: 50, right: 50 }
        });

        const buffers = [];
        doc.on('data', buffers.push.bind(buffers));
        doc.on('end', () => {
          const pdfBuffer = Buffer.concat(buffers);
          resolve(pdfBuffer);
        });

        // Generar contenido del PDF
        this.generatePDFContent(doc, data);
        doc.end();

      } catch (error) {
        logger.error('Error generating PDF:', error);
        reject(new Error('PDF generation failed'));
      }
    });
  }

  /**
   * Genera el contenido del PDF
   * @param {PDFDocument} doc - Documento PDF
   * @param {Object} data - Datos a incluir
   */
  generatePDFContent(doc, data) {
    // Encabezado
    this.addHeader(doc);
    
    // Título
    doc.fontSize(20)
       .font('Helvetica-Bold')
       .text('INFORME DE ORIENTACIÓN LEGAL', { align: 'center' })
       .moveDown();

    doc.fontSize(14)
       .font('Helvetica')
       .text('Derecho Digital y Protección de Datos', { align: 'center' })
       .moveDown(2);

    // Información de la consulta
    this.addSection(doc, 'INFORMACIÓN DE LA CONSULTA', () => {
      doc.fontSize(12)
         .text(`Fecha: ${new Date(data.timestamp).toLocaleDateString('es-ES')}`)
         .text(`Hora: ${new Date(data.timestamp).toLocaleTimeString('es-ES')}`)
         .text(`Idioma: ${data.language === 'quechua' ? 'Quechua' : 'Español'}`)
         .moveDown();

      doc.font('Helvetica-Bold')
         .text('Consulta:');
      doc.font('Helvetica')
         .text(data.query, { align: 'justify' });
    });

    // Respuesta en español
    if (data.response.spanish) {
      this.addSection(doc, 'RESPUESTA EN ESPAÑOL', () => {
        doc.fontSize(12)
           .font('Helvetica')
           .text(data.response.spanish, { align: 'justify' });
      });
    }

    // Respuesta en quechua
    if (data.response.quechua) {
      this.addSection(doc, 'RESPUESTA EN QUECHUA', () => {
        doc.fontSize(12)
           .font('Helvetica')
           .text(data.response.quechua, { align: 'justify' });
      });
    }

    // Recomendaciones importantes
    this.addRecommendations(doc);

    // Pie de página
    this.addFooter(doc);
  }

  /**
   * Agrega encabezado al PDF
   * @param {PDFDocument} doc - Documento PDF
   */
  addHeader(doc) {
    // Línea superior
    doc.strokeColor('#2c3e50')
       .lineWidth(2)
       .moveTo(50, 30)
       .lineTo(545, 30)
       .stroke();

    // Logo o título (placeholder)
    doc.fontSize(16)
       .font('Helvetica-Bold')
       .fillColor('#2c3e50')
       .text('IA Jurídica - Asistente Legal Bilingüe', 50, 40);
  }

  /**
   * Agrega una sección al PDF
   * @param {PDFDocument} doc - Documento PDF
   * @param {string} title - Título de la sección
   * @param {Function} content - Función que genera el contenido
   */
  addSection(doc, title, content) {
    doc.moveDown();
    
    // Título de sección
    doc.fontSize(14)
       .font('Helvetica-Bold')
       .fillColor('#2c3e50')
       .text(title);
    
    // Línea bajo el título
    doc.strokeColor('#34495e')
       .lineWidth(1)
       .moveTo(50, doc.y)
       .lineTo(545, doc.y)
       .stroke();
    
    doc.moveDown(0.5);
    
    // Contenido
    doc.fillColor('black')
       .font('Helvetica');
    content();
    
    doc.moveDown();
  }

  /**
   * Agrega recomendaciones importantes
   * @param {PDFDocument} doc - Documento PDF
   */
  addRecommendations(doc) {
    this.addSection(doc, 'RECOMENDACIONES IMPORTANTES', () => {
      const recommendations = [
        'Este informe proporciona orientación básica y no reemplaza el consejo de un abogado profesional.',
        'Para casos complejos o situaciones específicas, consulte siempre con un abogado licenciado.',
        'Guarde este documento como referencia futura.',
        'Comparta esta información con su comunidad para ayudar a otros en situaciones similares.'
      ];

      doc.fontSize(11);
      recommendations.forEach((rec, index) => {
        doc.text(`${index + 1}. ${rec}`, { align: 'justify' });
        doc.moveDown(0.3);
      });
    });
  }

  /**
   * Agrega pie de página
   * @param {PDFDocument} doc - Documento PDF
   */
  addFooter(doc) {
    const bottom = doc.page.height - 50;
    
    // Línea inferior
    doc.strokeColor('#2c3e50')
       .lineWidth(2)
       .moveTo(50, bottom - 20)
       .lineTo(545, bottom - 20)
       .stroke();

    // Texto del pie
    doc.fontSize(10)
       .font('Helvetica')
       .fillColor('#7f8c8d')
       .text('Generado por IA Jurídica - Asistente Legal Bilingüe para Comunidades Andinas', 
             50, bottom - 10, { align: 'center' });
    
    doc.text('Derecho Digital • Protección de Datos • Acceso a la Justicia', 
             50, bottom, { align: 'center' });
  }

  /**
   * Asegura que el directorio de salida exista
   */
  ensureOutputDir() {
    if (!fs.existsSync(this.outputDir)) {
      fs.mkdirSync(this.outputDir, { recursive: true });
    }
  }

  /**
   * Guarda PDF en archivo (opcional)
   * @param {Buffer} pdfBuffer - Buffer del PDF
   * @param {string} filename - Nombre del archivo
   * @returns {Promise<string>} Ruta del archivo guardado
   */
  async savePDF(pdfBuffer, filename) {
    try {
      const filepath = path.join(this.outputDir, filename);
      fs.writeFileSync(filepath, pdfBuffer);
      logger.info(`PDF saved: ${filepath}`);
      return filepath;
    } catch (error) {
      logger.error('Error saving PDF:', error);
      throw new Error('Failed to save PDF');
    }
  }

  /**
   * Genera PDF con formato simplificado para móvil
   * @param {Object} data - Datos para el PDF
   * @returns {Promise<Buffer>} Buffer del PDF generado
   */
  async generateMobileReport(data) {
    return new Promise((resolve, reject) => {
      try {
        const doc = new PDFDocument({
          size: 'A4',
          margins: { top: 30, bottom: 30, left: 30, right: 30 }
        });

        const buffers = [];
        doc.on('data', buffers.push.bind(buffers));
        doc.on('end', () => {
          const pdfBuffer = Buffer.concat(buffers);
          resolve(pdfBuffer);
        });

        // Contenido simplificado para móvil
        doc.fontSize(16)
           .font('Helvetica-Bold')
           .text('ORIENTACIÓN LEGAL', { align: 'center' })
           .moveDown();

        doc.fontSize(12)
           .font('Helvetica')
           .text(`Consulta: ${data.query}`)
           .moveDown();

        if (data.response.spanish) {
          doc.font('Helvetica-Bold')
             .text('Respuesta:');
          doc.font('Helvetica')
             .text(data.response.spanish, { align: 'justify' })
             .moveDown();
        }

        doc.end();

      } catch (error) {
        logger.error('Error generating mobile PDF:', error);
        reject(new Error('Mobile PDF generation failed'));
      }
    });
  }
}

module.exports = PDFService;
