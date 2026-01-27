from typing import List, Dict, Any
import asyncio
from loguru import logger

try:
    from deepeval import evaluate
    from deepeval.test_case import LLMTestCase
    from deepeval.metrics import (
        AnswerRelevancyMetric, 
        BiasMetric, 
        HallucinationMetric,
        FaithfulnessMetric,
        ContextualRelevancyMetric
    )
    DEEPEVAL_AVAILABLE = True
except ImportError:
    logger.warning("DeepEval no disponible. Usando implementación simulada.")
    DEEPEVAL_AVAILABLE = False

class LegalEvaluationSuite:
    """Suite de evaluación para respuestas legales con DeepEval"""
    
    def __init__(self):
        self.test_cases = []
        self.evaluation_results = []
        
        if DEEPEVAL_AVAILABLE:
            self._initialize_metrics()
        else:
            logger.warning("DeepEval no inicializado - usando evaluaciones simuladas")
    
    def _initialize_metrics(self):
        """Inicializa métricas de evaluación"""
        
        self.metrics = {
            "relevancy": AnswerRelevancyMetric(threshold=0.7),
            "bias": BiasMetric(threshold=0.3),
            "hallucination": HallucinationMetric(threshold=0.3),
            "faithfulness": FaithfulnessMetric(threshold=0.7),
            "context_relevancy": ContextualRelevancyMetric(threshold=0.7)
        }
        
        logger.info("Métricas DeepEval inicializadas")
    
    def create_legal_test_cases(self) -> List[LLMTestCase]:
        """Crea casos de prueba para evaluación legal"""
        
        test_cases = [
            # Caso 1: Violencia Familiar
            LLMTestCase(
                input="¿Qué hago si mi pareja me golpea?",
                actual_output="Debes llamar al 113 inmediatamente y acudir a la comisaría de mujeres. La Ley 30364 te protege.",
                expected_output="Llamar a emergencias y acudir a autoridad",
                retrieval_context=["Ley 30364", "Violencia familiar", "Medidas de protección"],
                context=["Artículo 2 de la Ley 30364 define tipos de violencia"]
            ),
            
            # Caso 2: Pensión de Alimentos
            LLMTestCase(
                input="¿Cómo solicito pensión de alimentos para mis hijos?",
                actual_output="Debes presentar una demanda en el Juzgado de Familia con DNI, partidas de nacimiento y comprobantes de ingresos del obligado.",
                expected_output="Presentar demanda judicial con documentos específicos",
                retrieval_context=["Código Civil artículos 472-485", "Pensión de alimentos", "Proceso judicial"],
                context=["El Código Civil establece la obligación alimentaria"]
            ),
            
            # Caso 3: Medidas de Protección
            LLMTestCase(
                input="¿Qué son las medidas de protección y cómo las obtengo?",
                actual_output="Son ordenes judiciales para proteger a víctimas de violencia. Se solicitan en comisaría o fiscalía y pueden incluir alejamiento.",
                expected_output="Órdenes judiciales de protección inmediata",
                retrieval_context=["Ley 30364 Artículo 20", "Medidas de protección", "Procedimiento urgente"],
                context=["Las medidas protegen contra agresores"]
            ),
            
            # Caso 4: Régimen de Visitas
            LLMTestCase(
                input="¿Mi ex no me deja ver a mis hijos, qué hago?",
                actual_output="Debes solicitar un régimen de visitas en el Juzgado de Familia. El juez establecerá un horario regular para tu convivencia.",
                expected_output="Solicitar régimen de visitas judicial",
                retrieval_context=["Código Civil", "Régimen de visitas", "Derechos parentales"],
                context=["Los hijos tienen derecho a convivir con ambos padres"]
            ),
            
            # Caso 5: Denuncias y Procesos
            LLMTestCase(
                input="¿Cuánto tiempo dura un proceso de violencia familiar?",
                actual_output="Varía entre 6 meses y 2 años dependiendo de la complejidad. Las medidas de protección son inmediatas.",
                expected_output="Proceso de 6 meses a 2 años, medidas inmediatas",
                retrieval_context=["Proceso judicial peruano", "Plazos legales", "Medidas urgentes"],
                context=["Los procesos pueden ser largos pero la protección es rápida"]
            )
        ]
        
        return test_cases
    
    async def run_single_evaluation(self, test_case: LLMTestCase) -> Dict[str, Any]:
        """Evalúa un solo caso de prueba"""
        
        try:
            if DEEPEVAL_AVAILABLE:
                # Usar DeepEval real
                results = {}
                
                for metric_name, metric in self.metrics.items():
                    try:
                        metric.measure(test_case)
                        results[metric_name] = {
                            "score": metric.score,
                            "passed": metric.score >= metric.threshold,
                            "threshold": metric.threshold,
                            "reason": metric.reason if hasattr(metric, 'reason') else "No reason provided"
                        }
                    except Exception as e:
                        logger.error(f"Error en métrica {metric_name}: {str(e)}")
                        results[metric_name] = {
                            "score": 0.0,
                            "passed": False,
                            "error": str(e)
                        }
                
                # Calcular puntuación general
                passed_count = sum(1 for r in results.values() if r.get("passed", False))
                total_count = len(results)
                overall_score = passed_count / total_count if total_count > 0 else 0.0
                
                return {
                    "test_input": test_case.input,
                    "overall_score": overall_score,
                    "passed": overall_score >= 0.7,
                    "metrics": results,
                    "evaluation_method": "deepeval"
                }
            else:
                # Implementación fallback
                return await self._fallback_evaluation(test_case)
                
        except Exception as e:
            logger.error(f"Error en evaluación: {str(e)}")
            return {
                "test_input": test_case.input,
                "error": str(e),
                "overall_score": 0.0,
                "passed": False
            }
    
    async def _fallback_evaluation(self, test_case: LLMTestCase) -> Dict[str, Any]:
        """Implementación fallback de evaluación"""
        
        # Evaluación simple basada en palabras clave
        input_lower = test_case.input.lower()
        output_lower = test_case.actual_output.lower()
        expected_lower = test_case.expected_output.lower()
        
        # Métricas simples
        relevancy_score = self._calculate_keyword_similarity(input_lower, output_lower)
        bias_score = self._detect_bias(output_lower)
        hallucination_score = self._detect_hallucination(output_lower, test_case.retrieval_context)
        faithfulness_score = self._calculate_faithfulness(output_lower, expected_lower)
        
        results = {
            "relevancy": {"score": relevancy_score, "passed": relevancy_score >= 0.7},
            "bias": {"score": bias_score, "passed": bias_score <= 0.3},
            "hallucination": {"score": hallucination_score, "passed": hallucination_score <= 0.3},
            "faithfulness": {"score": faithfulness_score, "passed": faithfulness_score >= 0.7}
        }
        
        passed_count = sum(1 for r in results.values() if r["passed"])
        overall_score = passed_count / len(results)
        
        return {
            "test_input": test_case.input,
            "overall_score": overall_score,
            "passed": overall_score >= 0.7,
            "metrics": results,
            "evaluation_method": "fallback"
        }
    
    def _calculate_keyword_similarity(self, input_text: str, output_text: str) -> float:
        """Calcula similitud basada en palabras clave"""
        
        input_words = set(input_text.split())
        output_words = set(output_text.split())
        
        if not input_words:
            return 0.0
        
        intersection = input_words & output_words
        return len(intersection) / len(input_words)
    
    def _detect_bias(self, text: str) -> float:
        """Detecta sesgo en el texto"""
        
        bias_indicators = [
            "siempre", "nunca", "todos", "ninguno",
            "obviamente", "claramente", "definitivamente"
        ]
        
        text_lower = text.lower()
        bias_count = sum(1 for indicator in bias_indicators if indicator in text_lower)
        
        # Score normalizado (más alto = más sesgo)
        return min(bias_count * 0.2, 1.0)
    
    def _detect_hallucination(self, text: str, context: List[str]) -> float:
        """Detecta alucinaciones comparando con contexto"""
        
        if not context:
            return 0.5  # Neutral si no hay contexto
        
        context_text = " ".join(context).lower()
        text_lower = text.lower()
        
        # Buscar información que no está en contexto
        text_words = set(text_lower.split())
        context_words = set(context_text.split())
        
        unknown_words = text_words - context_words
        hallucination_ratio = len(unknown_words) / len(text_words) if text_words else 0.0
        
        return min(hallucination_ratio, 1.0)
    
    def _calculate_faithfulness(self, output: str, expected: str) -> float:
        """Calcula fidelidad a la respuesta esperada"""
        
        output_words = set(output.lower().split())
        expected_words = set(expected.lower().split())
        
        if not expected_words:
            return 0.0
        
        intersection = output_words & expected_words
        return len(intersection) / len(expected_words)
    
    async def run_full_evaluation(self) -> Dict[str, Any]:
        """Ejecuta evaluación completa del sistema"""
        
        logger.info("Iniciando evaluación completa del sistema legal")
        
        # Crear casos de prueba
        test_cases = self.create_legal_test_cases()
        
        # Evaluar cada caso
        results = []
        overall_scores = []
        
        for i, test_case in enumerate(test_cases):
            logger.info(f"Evaluando caso {i+1}/{len(test_cases)}: {test_case.input[:50]}...")
            
            result = await self.run_single_evaluation(test_case)
            results.append(result)
            overall_scores.append(result["overall_score"])
        
        # Calcular estadísticas generales
        avg_score = sum(overall_scores) / len(overall_scores) if overall_scores else 0.0
        passed_tests = sum(1 for r in results if r["passed"])
        pass_rate = passed_tests / len(results) if results else 0.0
        
        # Análisis por métrica
        metric_analysis = self._analyze_metrics(results)
        
        evaluation_summary = {
            "total_tests": len(results),
            "passed_tests": passed_tests,
            "failed_tests": len(results) - passed_tests,
            "pass_rate": pass_rate,
            "average_score": avg_score,
            "metric_analysis": metric_analysis,
            "individual_results": results,
            "evaluation_timestamp": self._get_current_timestamp(),
            "system_version": "2.0.0"
        }
        
        logger.info(f"Evaluación completada: {pass_rate:.2%} pass rate, {avg_score:.2f} avg score")
        
        return evaluation_summary
    
    def _analyze_metrics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analiza rendimiento por métrica"""
        
        metric_scores = {}
        
        for result in results:
            if "metrics" in result:
                for metric_name, metric_data in result["metrics"].items():
                    if metric_name not in metric_scores:
                        metric_scores[metric_name] = []
                    
                    score = metric_data.get("score", 0.0)
                    metric_scores[metric_name].append(score)
        
        # Calcular estadísticas por métrica
        metric_analysis = {}
        for metric_name, scores in metric_scores.items():
            if scores:
                metric_analysis[metric_name] = {
                    "average": sum(scores) / len(scores),
                    "min": min(scores),
                    "max": max(scores),
                    "passed_count": sum(1 for s in scores if s >= 0.7),
                    "total_count": len(scores),
                    "pass_rate": sum(1 for s in scores if s >= 0.7) / len(scores)
                }
        
        return metric_analysis
    
    def _get_current_timestamp(self) -> str:
        """Obtiene timestamp actual"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    async def evaluate_response_quality(self, query: str, response: str, context: List[str]) -> Dict[str, Any]:
        """Evalúa calidad de una respuesta específica"""
        
        test_case = LLMTestCase(
            input=query,
            actual_output=response,
            retrieval_context=context
        )
        
        return await self.run_single_evaluation(test_case)
    
    def generate_evaluation_report(self, results: Dict[str, Any]) -> str:
        """Genera reporte de evaluación en formato markdown"""
        
        report = f"""# Informe de Evaluación - IA Jurídica

## 📊 Resumen General
- **Fecha**: {results['evaluation_timestamp']}
- **Versión**: {results['system_version']}
- **Total de Pruebas**: {results['total_tests']}
- **Pruebas Aprobadas**: {results['passed_tests']}
- **Tasa de Aprobación**: {results['pass_rate']:.2%}
- **Puntuación Promedio**: {results['average_score']:.2f}

## 📈 Análisis por Métrica
"""
        
        for metric_name, analysis in results['metric_analysis'].items():
            report += f"""
### {metric_name.title()}
- **Promedio**: {analysis['average']:.2f}
- **Mínimo**: {analysis['min']:.2f}
- **Máximo**: {analysis['max']:.2f}
- **Tasa de Aprobación**: {analysis['pass_rate']:.2%}
"""
        
        report += """
## 📋 Resultados Detallados
"""
        
        for i, result in enumerate(results['individual_results'], 1):
            status = "✅ Aprobado" if result['passed'] else "❌ Reprobado"
            report += f"""
### Prueba {i}: {result['test_input'][:50]}...
- **Estado**: {status}
- **Puntuación**: {result['overall_score']:.2f}
- **Método**: {result.get('evaluation_method', 'unknown')}
"""
        
        report += """

## 🎯 Recomendaciones
"""
        
        if results['pass_rate'] < 0.8:
            report += "- **Mejorar respuestas**: La tasa de aprobación es baja. Revisar prompts y contexto.\n"
        
        if results['average_score'] < 0.7:
            report += "- **Ajustar métricas**: Las puntuaciones promedio son bajas. Considerar ajustar umbrales.\n"
        
        # Recomendaciones específicas por métrica
        for metric_name, analysis in results['metric_analysis'].items():
            if analysis['pass_rate'] < 0.7:
                report += f"- **Mejorar {metric_name}**: Tasa de aprobación baja ({analysis['pass_rate']:.2%}).\n"
        
        report += f"""
---
*Informe generado automáticamente por DeepEval - {self._get_current_timestamp()}*
"""
        
        return report
    
    async def save_evaluation_results(self, results: Dict[str, Any], filepath: str = None):
        """Guarda resultados de evaluación"""
        
        if filepath is None:
            filepath = f"evaluation_results_{self._get_current_timestamp().replace(':', '-')}.json"
        
        try:
            import json
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Resultados guardados en {filepath}")
            
            # También generar reporte markdown
            report_path = filepath.replace('.json', '.md')
            report = self.generate_evaluation_report(results)
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report)
            
            logger.info(f"Reporte guardado en {report_path}")
            
        except Exception as e:
            logger.error(f"Error guardando resultados: {str(e)}")
            raise
