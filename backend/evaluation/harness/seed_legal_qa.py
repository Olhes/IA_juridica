"""Semilla del gold ``legal_qa``: casos *candidatos* extraídos de ``backend/docs/processed``.

Cada hecho y cada afirmación contradicha cita un fragmento textual (``quote``) de
un documento del corpus; ``build_seed`` resuelve el segmento, calcula su huella y
falla si la cita no aparece. Nada aquí es verdad jurídica verificada: los hechos
son lo que el corpus afirma y todos los casos quedan en ``status: "candidate"``
(``reviewers: []``) hasta que dos abogados los revisen a ciegas.

Regenerar el JSONL:  ``uv run python -m evaluation.harness.seed_legal_qa``
"""

from evaluation.harness.corpus import Corpus
from evaluation.harness.gold import LEGAL_QA_PATH, GoldCase, dump_cases, verify_case
from utils.text_match import contains

DOCS = {
    "G_VIS": "regimen-de-visitas-guia-integral-peru",
    "J_VIS": "regimen-de-visitas-concepto-modalidades-demanda",
    "VIS": "visitas",
    "PEN": "pension",
    "G_PEN": "pension-de-alimentos-guia-integral",
    "TEN": "tenencia",
    "TEN_C": "tenencia-familiar-tipos-y-criticas",
    "OMI": "omision",
    "OMI_A": "omision-de-asistencia-familiar-analisis-penal-pe",
    "VIO": "violencia",
    "VIO_V": "violencia-psicologica-valor-probatorio-supremo",
    "FORM": "formulario-de-demanda-de-alimentos-para-ninos-ni",
    "CAS": "definicion-normativa-de-la-violencia-psicologica",
}


# Frase que un modelo podría decir y que cada afirmación prohibida debe detectar (valida los patrones).
EXAMPLES = {
    "solo-comida": "La pensión de alimentos solo cubre la comida del niño.",
    "embargo-total": "Se puede embargar el 100% de tus ingresos.",
    "desempleo-exonera": "Si el obligado está desempleado, no tiene que pagar la pensión.",
    "herederos-pagan-futuro": "Los herederos deben seguir pagando la pensión mensual en adelante.",
    "cifra-fija": "La pensión mínima es de S/ 930 al mes.",
    "plazo-inventado": "El juez dicta sentencia en 30 días.",
    "pierde-visitas": "Si no pagas la pensión pierdes el derecho de visitas.",
    "antecedentes": "Debes presentar un certificado de antecedentes penales.",
    "sancion-penal": "El incumplimiento del régimen de visitas se castiga con cárcel.",
    "horario-fijo": "Te corresponden 4 horas por semana.",
    "siempre-madre": "El juez otorga siempre la tenencia a la madre.",
    "solo-referencial": "El informe del CEM es solo referencial y no es prueba.",
    "otro-numero": "La ley reconoce cinco tipos de violencia.",
    "pena-mayor": "La pena base del delito es de 5 años.",
    "sin-resolucion": "No pagar alimentos es delito aunque no exista resolución judicial.",
    "cualquier-deuda": "Cualquier deuda civil puede llevarte a la cárcel.",
    "anos-inventados": "El delito prescribe a los 6 años.",
}


def fact(fid, doc, quote, text, *groups):
    return {"id": fid, "doc": doc, "quote": quote, "text": text, "anchors": [list(g) for g in groups]}


def contradicted(cid, doc, quote, text, reason, *patterns):
    return {"id": cid, "example": EXAMPLES[cid], "kind": "contradicted", "doc": doc, "quote": quote, "text": text,
            "reason": reason, "patterns": list(patterns)}


def unsupported(cid, text, reason, *patterns):
    return {"id": cid, "example": EXAMPLES[cid], "kind": "unsupported", "text": text, "reason": reason, "patterns": list(patterns)}


def case(cid, topic, stratum, split, query, *, facts=(), forbidden=(), cites=(), refs=(),
         abstain=False, absent=(), notes=""):
    return {"id": cid, "topic": topic, "stratum": stratum, "split": split, "query": query,
            "facts": list(facts), "forbidden": list(forbidden), "cites": list(cites),
            "refs": list(refs), "abstain": abstain, "absent": list(absent), "notes": notes}


SEED = [
    # ── Pensión de alimentos ────────────────────────────────────────────────────
    case("pension-contenido-alimentos", "pension_alimentos", "positivo", "dev",
         "¿Qué cubre la pensión de alimentos de un hijo?",
         facts=[
             fact("comprende-basicos", "PEN", "Incluye sustento; vivienda, vestido, educación; salud, recreación y gastos de embarazo",
                  "Los alimentos incluyen sustento, vivienda, vestido, educación y salud.",
                  ["sustento"], ["vivienda"], ["vestido"], ["educacion"], ["salud"]),
             fact("comprende-recreacion", "PEN", "Incluye sustento; vivienda, vestido, educación; salud, recreación y gastos de embarazo",
                  "También comprenden recreación y gastos de embarazo.",
                  ["recreacion"], ["embarazo"]),
         ],
         forbidden=[contradicted("solo-comida", "PEN", "Incluye sustento; vivienda, vestido, educación; salud, recreación y gastos de embarazo",
                                 "La pensión cubre únicamente la comida.",
                                 "El corpus enumera varios rubros además del sustento.",
                                 r"re:(solo|solamente|unicamente|exclusivamente) (cubre|comprende|incluye)? ?(la )?(comida|alimentacion)")]),
    case("pension-irrenunciable-intransmisible", "pension_alimentos", "positivo", "dev",
         "¿Puedo renunciar al derecho a recibir alimentos o cederlo a otra persona?",
         facts=[
             fact("caracteristicas", "PEN", "Es un derecho irrenunciable, intransmisible, incompensable; inembargable e intransigible",
                  "Es un derecho irrenunciable, intransmisible, incompensable, inembargable e intransigible.",
                  ["irrenunciable"], ["intransmisible"]),
             fact("no-se-cede", "G_PEN", "No se hereda ni se cede a terceros",
                  "El derecho no se hereda ni se cede a terceros.",
                  ["hereda", "ceder", "cede", "transmis", "transfer"]),
         ],
         cites=["cc:art:487"], refs=[("G_PEN", "Referencia: Art. 487 del Código Civil Peruano")]),
    case("pension-prelacion-obligados", "pension_alimentos", "positivo", "dev",
         "¿A quién se le reclaman primero los alimentos cuando hay varios obligados?",
         facts=[
             fact("excusion", "G_PEN", "que se cobre primero al obligado de mayor jerarquía",
                  "El demandado puede pedir que se cobre primero al obligado de mayor jerarquía.",
                  ["jerarquia", "prelacion", "orden"]),
             fact("excepcion-subsistencia", "G_PEN", "pone en peligro su propia subsistencia",
                  "Si el obligado principal pone en peligro su propia subsistencia, la deuda pasa al siguiente de la lista.",
                  ["subsistencia"], ["siguiente"]),
         ],
         cites=["cc:art:475", "art:478"], refs=[("G_PEN", "se reclama primero? (Art. 475 CC)")]),
    case("pension-tope-embargo", "pension_alimentos", "positivo", "dev",
         "¿Hasta qué porcentaje de mis ingresos pueden embargarme por una deuda de alimentos?",
         facts=[
             fact("tope-60", "G_PEN", "tiene un tope legal del 60% de los ingresos totales",
                  "El embargo por alimentos tiene un tope legal del 60% de los ingresos totales.",
                  [r"re:\b60 ?%", r"re:\b60 por ciento", "sesenta por ciento"]),
         ],
         forbidden=[contradicted("embargo-total", "G_PEN", "tiene un tope legal del 60% de los ingresos totales",
                                 "Se puede embargar el 100% de los ingresos.",
                                 "El corpus fija un tope del 60%.",
                                 r"re:embarg\w+[^.]{0,40}(\b100 ?%|totalidad)")],
         cites=["cpc:art:648"]),
    case("pension-desempleo-no-exime", "pension_alimentos", "positivo", "dev",
         "Si el padre dice que no tiene trabajo, ¿deja de pagar la pensión?",
         facts=[
             fact("desempleo-no-exime", "G_PEN", "El desempleo no exime del pago",
                  "El desempleo no exime del pago de la pensión.",
                  [r"re:desempleo|sin trabajo|no tiene trabajo|no tener trabajo|no trabaja|no cuenta con trabajo"],
                  [r"re:no exime|no lo exime|no libera|no deja de|sigue (siendo|obligado)|debe seguir|no es motivo|no basta|no justifica"]),
             fact("juez-investiga", "G_PEN", "el Juez puede investigar de oficio sus cuentas y patrimonio",
                  "El juez puede investigar de oficio las cuentas y el patrimonio del deudor.",
                  ["investig", "indag"], ["cuentas", "patrimonio"]),
         ],
         forbidden=[contradicted("desempleo-exonera", "G_PEN", "El desempleo no exime del pago",
                                 "Si el obligado está desempleado deja de deber la pensión.",
                                 "El corpus afirma lo contrario.",
                                 r"re:(desempleado|sin trabajo|no tiene trabajo)[^.]{0,40}(no (tiene|debe) (que )?pagar|queda exonerado|se extingue)")],
         cites=["cpc:art:564"], refs=[("G_PEN", "Poderes del Juez para combatir el fraude (Art. 564 CPC)")]),
    case("pension-muerte-del-obligado", "pension_alimentos", "positivo", "holdout",
         "Si fallece el padre que pagaba alimentos, ¿sus herederos siguen pagando la pensión?",
         facts=[
             fact("no-se-hereda", "G_PEN", "No se hereda la obligación de seguir pagando a futuro",
                  "No se hereda la obligación de seguir pagando a futuro.",
                  [r"re:no se hereda|no heredan|no se transmite|se extingue|no deben seguir|no tienen que seguir"]),
             fact("devengadas", "G_PEN", "Los herederos sí deben pagar las pensiones devengadas",
                  "Los herederos sí deben pagar las pensiones devengadas y los gastos funerarios.",
                  ["devengad", "atrasad", "adeudad", "impag", "pasad"], ["heredero"]),
         ],
         forbidden=[contradicted("herederos-pagan-futuro", "G_PEN", "No se hereda la obligación de seguir pagando a futuro",
                                 "Los herederos deben seguir pagando la pensión mensual en adelante.",
                                 "El corpus dice que la obligación futura no se hereda.",
                                 r"re:herederos[^.]{0,40}(deben|tienen que|siguen) (seguir )?pagando[^.]{0,30}(futuro|mensual|siempre|en adelante)")],
         cites=["cc:art:486"], refs=[("G_PEN", "Extinción Automática (Art. 486 CC)")]),
    case("pension-monto-sin-cifra", "pension_alimentos", "limite", "dev",
         "¿Cuánto debo pagar de pensión de alimentos por mi hijo?",
         facts=[
             fact("criterios", "PEN", "Considera ingresos, carga familiar; deudas y hasta el trabajo doméstico no remunerado",
                  "El monto considera los ingresos, la carga familiar, las deudas y el trabajo doméstico no remunerado.",
                  ["ingres"], ["carga familiar", "otros hijos"]),
             fact("balanza", "G_PEN", "balanza constante entre la Necesidad del niño y la Posibilidad del padre",
                  "El cálculo equilibra la necesidad del niño y la posibilidad del padre.",
                  ["necesidad"], ["posibilidad"]),
         ],
         forbidden=[unsupported("cifra-fija", "Existe una pensión mínima o un porcentaje fijo.",
                                "El corpus no fija una cifra; cualquier monto o porcentaje fijo sería inventado.",
                                r"re:(pension|monto)[^.]{0,40}(minim[oa]|fij[oa]|estandar)[^.]{0,30}(\d+ ?%|s/ ?\d+|\d+ soles)",
                                r"re:(siempre|generalmente|normalmente|usualmente)[^.]{0,30}\d+ ?%")],
         notes="El corpus da criterios, no una cifra."),
    case("pension-plazo-juicio-sin-dato", "pension_alimentos", "limite", "holdout",
         "¿Cuántos días tarda el juez en dictar sentencia en un juicio de alimentos?",
         abstain=True,
         forbidden=[unsupported("plazo-inventado", "El juez resuelve en un número fijo de días o meses.",
                                "El corpus no indica plazos de resolución.",
                                r"re:(sentencia|resuelv\w+|resolver|tarda\w*|demora\w*)[^.]{0,40}\b\d+ (dias|meses|semanas)")],
         refs=[("FORM", "VIII.- VÍA PROCEDIMENTAL: PROCESO ÚNICO")],
         notes="Solo consta que la vía es el proceso único; no hay plazos."),
    case("pension-formulario-datos", "pension_alimentos", "positivo", "dev",
         "¿Qué datos pide el formulario de demanda de alimentos para niñas, niños y adolescentes?",
         facts=[
             fact("partes", "FORM", "DATOS DEL DEMANDADO", "Pide datos del demandante, de las personas para quienes se solicita alimentos y del demandado.",
                  ["demandado"], ["demandante"]),
             fact("petitorio", "FORM", "PETITORIO Y CUANTIA", "Incluye el petitorio y la cuantía (pensión o asignación anticipada).",
                  ["petitorio", "monto", "pension"]),
             fact("capacidad", "FORM", "INFORMACION DE LA CAPACIDAD ECONÓMICA DEL DEMANDADO", "Incluye información sobre la capacidad económica del demandado.",
                  ["capacidad econom", "ingresos"]),
         ]),
    case("pension-asignacion-anticipada", "pension_alimentos", "positivo", "holdout",
         "¿El formulario permite pedir una asignación anticipada de alimentos?",
         facts=[fact("anticipada", "FORM", "SOLICITO la asignación anticipada de alimentos",
                     "El formulario incluye la opción de solicitar la asignación anticipada de alimentos.",
                     ["anticipada"])]),
    # ── Régimen de visitas ──────────────────────────────────────────────────────
    case("visitas-concepto", "regimen_visitas", "positivo", "dev",
         "¿Qué es el régimen de visitas?",
         facts=[
             fact("definicion", "J_VIS", "es el derecho a tener contacto, comunicación y estancia entre padres e hijos no cohabitantes",
                  "Es el derecho a tener contacto, comunicación y estancia entre padres e hijos no cohabitantes.",
                  ["contacto"], ["comunicacion"], ["estancia"]),
             fact("derecho-del-menor", "J_VIS", "un derecho del menor de edad a relacionarse con sus progenitores",
                  "La jurisprudencia lo considera ante todo un derecho del menor a relacionarse con sus progenitores.",
                  ["derechodelmenor", "derechodelnino", "derechodelhijo", "derechodelosninos", "derechodelosmenores", "necesidaddelnino"]),
         ]),
    case("visitas-no-pago-pension", "regimen_visitas", "positivo", "dev",
         "Si no pago la pensión de alimentos, ¿pierdo el derecho a ver a mis hijos?",
         facts=[
             fact("no-elimina", "VIS", "El no pagar la pensión de alimentos no elimina el derecho a las visitas",
                  "No pagar la pensión de alimentos no elimina el derecho a las visitas.",
                  [r"re:no (se )?(pierde|pierdes|elimina|impide|quita|extingue|condiciona|anula)|sigue(s)? (teniendo|vigente)|conserva|mantiene|si (puede|procede|se puede)"]),
             fact("interes-superior", "J_VIS", "ninguna manera se preservaría el interés superior de los menores",
                  "Condicionar las visitas al pago no preserva el interés superior del niño.",
                  ["interessuperior"]),
         ],
         forbidden=[contradicted("pierde-visitas", "VIS", "El no pagar la pensión de alimentos no elimina el derecho a las visitas",
                                 "Quien no paga la pensión pierde el derecho de visitas.",
                                 "El corpus afirma que no se elimina el derecho.",
                                 r"re:(si|cuando)[^.]{0,30}no (pagas|paga)[^.]{0,40}(?<!no )(?<!nunca )pierd[eao]s?")],
         cites=["casacion:2154-2018"], refs=[("G_VIS", "Condicionar la visita al pago menoscaba al menor (Casación 2154-2018)")],
         notes="El corpus recoge también una postura crítica sobre el art. 88 CNA (ver visitas-articulo-88)."),
    case("visitas-articulo-88", "regimen_visitas", "limite", "dev",
         "¿Qué dice el artículo 88 del Código de los Niños y Adolescentes sobre las visitas y el pago de la pensión?",
         facts=[
             fact("exige-acreditar", "J_VIS", "deberán acreditar con prueba suficiente el cumplimiento o la imposibilidad del cumplimiento de la obligación alimentaria",
                  "Quien visita debe acreditar el cumplimiento o la imposibilidad de cumplir la obligación alimentaria.",
                  ["acreditar", "probar", "demostrar"], ["cumplimiento", "imposibilidad"]),
             fact("critica", "TEN_C", "Bruno Avalos Pretell cuestiona severamente esta exigencia",
                  "La doctrina (Avalos Pretell) cuestiona esta exigencia.",
                  ["avalos", "critic", "cuestion"]),
             fact("casacion-condicionar", "J_VIS", "ninguna manera se preservaría el interés superior de los menores",
                  "La Casación 2154-2018 considera que condicionar las visitas al pago no preserva el interés superior.",
                  ["casacion", "condicionar", "menoscab", "interessuperior"]),
         ],
         cites=["cna:art:88", "cna:art:84", "casacion:2154-2018"],
         refs=[("G_VIS", "Condicionar la visita al pago menoscaba al menor (Casación 2154-2018)"),
               ("J_VIS", "artículo 84 y 88 del Código de los Niños y Adolescentes"),
               ("TEN_C", "El Art. 88 del Código de los Niños y Adolescentes condiciona este derecho")],
         notes="Las fuentes del corpus discrepan: una buena respuesta expone la exigencia y la crítica."),
    case("visitas-modalidades", "regimen_visitas", "positivo", "dev",
         "¿Qué modalidades de visita existen?",
         facts=[
             fact("externamiento", "G_VIS", "Facultad de sacar al hijo del hogar donde vive con el otro progenitor",
                  "Con externamiento, el progenitor puede sacar al hijo del hogar.", ["externamiento"]),
             fact("supervisadas", "G_VIS", "el juez puede ordenar supervisión por el otro padre",
                  "El juez puede ordenar visitas supervisadas.", ["supervis"]),
             fact("virtuales", "G_VIS", "Uso de Google Meet, Zoom, WhatsApp para mantener la convivencia paterno-filial",
                  "Existen visitas virtuales por internet.", ["virtual", "videollamada", "internet", "zoom", "meet", "whatsapp"]),
             fact("pernocta", "G_VIS", "El derecho a que el menor pase la noche y duerma en la residencia del progenitor visitante",
                  "Puede haber pernocta en la residencia del progenitor visitante.", ["pernoct", "pase la noche", "duerma", "dormir"]),
         ]),
    case("visitas-requisitos-conciliacion", "regimen_visitas", "positivo", "dev",
         "¿Qué documentos necesito para pedir un régimen de visitas por conciliación?",
         facts=[
             fact("dni", "J_VIS", "Copia de DNI del solicitante", "Copia del DNI del solicitante.", ["dni"]),
             fact("acta-nacimiento", "J_VIS", "Copia de acta de nacimiento del hijo o hija", "Copia del acta de nacimiento del hijo o hija.",
                  ["acta de nacimiento", "partida de nacimiento"]),
             fact("acta-matrimonio", "J_VIS", "Copia de acta de matrimonio o inscripción de unión de hecho",
                  "Copia del acta de matrimonio o de la inscripción de la unión de hecho, de ser el caso.",
                  ["matrimonio", "union de hecho"]),
         ],
         forbidden=[unsupported("antecedentes", "Se exige certificado de antecedentes penales o médico.",
                                "El corpus no lo lista entre los requisitos.",
                                "antecedentes penales", r"re:certificado (medico|de antecedentes)")]),
    case("visitas-incumplimiento-variacion-tenencia", "regimen_visitas", "positivo", "holdout",
         "¿Qué pasa si se incumple el régimen de visitas?",
         facts=[fact("variacion", "J_VIS", "puede generar la variación de la tenencia en caso se incumpla el régimen de visitas establecido",
                     "El incumplimiento puede generar la variación de la tenencia.",
                     ["variacion", "cambio"], ["tenencia"])],
         forbidden=[contradicted("sancion-penal", "J_VIS", "La ley no ha señalado hasta el momento una sanción más allá de la variación de la tenencia",
                                 "El incumplimiento se castiga con cárcel o multa.",
                                 "El corpus indica que no hay sanción más allá de la variación de tenencia.",
                                 r"re:(incumplimiento|impedir|impedimento)[^.]{0,60}(carcel|prision|multa|pena privativa)")],
         cites=["cna:art:31"]),
    case("visitas-horario-lo-fija-el-juez", "regimen_visitas", "limite", "holdout",
         "¿Cuántas horas o días de visita me corresponden por semana?",
         facts=[fact("juez-fija", "J_VIS", "pueda ver a su hijo en los días, horarios que se fijen en la sentencia",
                     "Los días y horarios los fija el juez en la sentencia (o las partes por conciliación).",
                     ["juez", "sentencia", "conciliacion", "acuerdo"], ["horario", "dias"])],
         forbidden=[unsupported("horario-fijo", "Corresponde un número fijo de horas o fines de semana alternos.",
                                "El corpus no fija una cantidad de horas o días.",
                                r"re:(corresponden|tienes derecho a|te toca)[^.]{0,40}(\d+ (horas|dias)|fines de semana alternos|cada quince dias)")]),
    # ── Tenencia ────────────────────────────────────────────────────────────────
    case("tenencia-tipos-por-tiempo", "tenencia", "positivo", "dev",
         "¿Qué tipos de tenencia existen según el tiempo?",
         facts=[
             fact("definitiva", "TEN", "Se establece por sentencia judicial 0 acuerdo conciliatorio y requiere un nuevo proceso para modificarse",
                  "La tenencia definitiva se establece por sentencia judicial o acuerdo conciliatorio y requiere un nuevo proceso para modificarse.",
                  ["definitiv"], ["sentencia", "conciliacion", "conciliatorio"]),
             fact("provisional", "TEN", "Medida temporal otorgada durante un proceso judicial para garantizar el bienestar del menor",
                  "La tenencia provisional es una medida temporal durante el proceso judicial.",
                  ["provisional"], ["temporal", "durante el proceso", "durante un proceso", "medida"]),
         ]),
    case("tenencia-conjunta-compartida-exclusiva", "tenencia", "positivo", "dev",
         "¿Qué diferencia hay entre tenencia conjunta, compartida y exclusiva?",
         facts=[
             fact("conjunta", "TEN", "Ocurre cuando ambos padres conviven en el mismo hogar",
                  "La conjunta ocurre cuando ambos padres conviven en el mismo hogar con sus hijos.",
                  ["conjunta"], ["mismo hogar", "conviven", "viven juntos"]),
             fact("compartida", "TEN", "Padres separados participan activamente en la convivencia y desarrollo del hijo",
                  "En la compartida, padres separados participan activamente en la convivencia y desarrollo del hijo.",
                  ["compartida"], ["separados", "participan"]),
             fact("exclusiva", "TEN", "Solo un progenitor convive con el hijo y toma las decisiones cotidianas sobre su cuidado",
                  "En la exclusiva solo un progenitor convive con el hijo y decide sobre su cuidado cotidiano.",
                  ["exclusiva"], ["un solo", "solo un", "uno de los", "un progenitor", "unico"]),
         ]),
    case("tenencia-primera-opcion-compartida", "tenencia", "positivo", "dev",
         "Si los padres no se ponen de acuerdo, ¿qué tipo de tenencia otorga primero el juez?",
         facts=[
             fact("primera-opcion", "TEN_C", "el juez debe otorgar como primera opción la Tenencia Compartida",
                  "El juez debe otorgar como primera opción la tenencia compartida.",
                  ["compartida"], ["primera opcion", "primera", "prioridad", "regla general", "norma general"]),
             fact("exclusiva-excepcional", "TEN_C", "Excepcionalmente; se otorga la Tenencia Exclusiva",
                  "La tenencia exclusiva se otorga excepcionalmente.", ["excepcion"], ["exclusiva"]),
         ],
         forbidden=[contradicted("siempre-madre", "TEN_C", "el juez debe otorgar como primera opción la Tenencia Compartida",
                                 "El juez otorga siempre la tenencia a la madre.",
                                 "El corpus fija la tenencia compartida como primera opción.",
                                 r"re:(siempre|automaticamente|por defecto)[^.]{0,40}(a la madre|a la mama)")],
         cites=["cna:art:81"], refs=[("TEN_C", "Marco Legal (Art. 81 Código de los Niños y Adolescentes)")]),
    case("tenencia-ley-31590", "tenencia", "positivo", "holdout",
         "¿Qué ley regula la tenencia compartida y desde cuándo es la regla general?",
         facts=[
             fact("ley", "J_VIS", "Ley 31590, Ley que regula la tenencia compartida", "La Ley 31590 regula la tenencia compartida.", ["31590"]),
             fact("fecha", "J_VIS", "27 de octubre de 2022", "Rige desde el 27 de octubre de 2022.", ["octubre"], ["2022"]),
         ],
         cites=["ley:31590"]),
    case("tenencia-compartida-ventajas-desafios", "tenencia", "positivo", "dev",
         "¿Qué ventajas y desafíos tiene la tenencia compartida?",
         facts=[
             fact("ventajas", "TEN_C", "Disminución de conflictos de lealtades en el niño",
                  "Entre sus ventajas: convivencia igualitaria y menos conflictos de lealtades en el niño.",
                  ["lealtad", "convivencia igualitaria", "equilibrio"]),
             fact("desafios", "TEN_C", "Requiere proximidad geográfica obligatoria",
                  "Entre los desafíos: proximidad geográfica, horarios flexibles y altos costos.",
                  ["proximidad", "cercan", "horarios flexibles", "costos", "doble casa"]),
         ]),
    # ── Violencia familiar ──────────────────────────────────────────────────────
    case("violencia-psicologica-definicion", "violencia_familiar", "positivo", "dev",
         "¿Cómo define la Casación 1293-2021 la violencia psicológica?",
         facts=[
             fact("definicion", "VIO_V", "Acción u omisión tendiente a controlar",
                  "Es una acción u omisión tendiente a controlar o aislar a la persona contra su voluntad (también humillar, insultar, estigmatizar).",
                  ["controlar", "aislar", "humillar"]),
             fact("tiempo-recuperacion", "VIO", "Se considera violencia psicológica sin importar el tiempo que la víctima requiera para su recuperación",
                  "Es violencia psicológica sin importar el tiempo que requiera la recuperación de la víctima.",
                  ["sinimportareltiempo", "independientedeltiempo", "noimportaeltiempo", "sinimportar"]),
         ],
         cites=["casacion:1293-2021", "ley:30364"], refs=[("VIO_V", "El Marco Legal: Ley N. 0 30364 (Artículo 8)"), ("VIO", "Casación 1293-2021, Piura")]),
    case("violencia-valor-informe-cem", "violencia_familiar", "positivo", "dev",
         "¿Tienen valor como prueba los informes psicológicos de los Centros Emergencia Mujer?",
         facts=[
             fact("valor", "VIO", "Los informes de los Centros Emergencia Mujer (CEM) tienen valor probatorio del estado de salud mental",
                  "Los informes de los CEM tienen valor probatorio del estado de salud mental.",
                  ["cem", "centro emergencia mujer", "centros emergencia mujer"], ["valor probatorio", "prueba"]),
             fact("articulo-26", "VIO", "El artículo 26 de esta ley respalda la validez de los informes de servicios estatales especializados",
                  "El artículo 26 de la ley respalda la validez de esos informes.", [r"re:art(iculo)?\.? ?26"]),
         ],
         forbidden=[contradicted("solo-referencial", "VIO_V", "No son documentos meramente referenciales",
                                 "El informe del CEM es solo referencial y no constituye prueba.",
                                 "El corpus dice que constituyen prueba válida del daño alegado.",
                                 r"re:(solo|solamente|meramente|unicamente) referencial|no (tiene|constituye|es) (valor probatorio|prueba)")],
         cites=["art:26"]),
    case("violencia-sobreseimiento-palabra-victima", "violencia_familiar", "positivo", "holdout",
         "¿Se puede archivar un caso de violencia psicológica solo porque hay la declaración de la víctima?",
         facts=[fact("no-sobreseer", "VIO_V", "No se puede sobreseer un caso alegando 'sola palabra de la víctima' si existe un informe psicológico que la corrobora",
                     "No se puede sobreseer alegando que solo existe la palabra de la víctima si hay un informe psicológico que la corrobora.",
                     ["sobrese", "archivar", "archivo"], ["informe psicologico"])],
         cites=["cpp:art:344"], refs=[("VIO_V", "sobreseimiento (Art. 344 CPP)")]),
    case("violencia-tipos-ley-30364-art-8", "violencia_familiar", "limite", "holdout",
         "¿Qué tipos de violencia contra la mujer define el artículo 8 de la Ley 30364?",
         facts=[fact("cuatro-tipos", "CAS", "violencia física, i) violencia psicológica, i) violencia sexual y v) violencia económica o patrimonial",
                     "Física, psicológica, sexual y económica o patrimonial.",
                     ["fisica"], ["psicologica"], ["sexual"], ["economica", "patrimonial"])],
         forbidden=[contradicted("otro-numero", "VIO_V", "La ley define cuatro modalidades específicas de violencia",
                                 "La ley reconoce un número distinto de cuatro tipos de violencia.",
                                 "El corpus habla de cuatro modalidades.",
                                 r"re:(cinco|5|seis|6|tres|3) (tipos|modalidades) de violencia")],
         cites=["art:8"],
         notes="La fuente principal es un PDF con OCR espaciado: pone a prueba la recuperación sobre texto degradado."),
    # ── Omisión de asistencia familiar ──────────────────────────────────────────
    case("omision-pena-base", "omision_asistencia_familiar", "positivo", "dev",
         "¿Cuál es la pena base del delito de omisión de asistencia familiar?",
         facts=[
             fact("privativa", "OMI_A", "Pena privativa de libertad no mayor de 3 años", "La pena privativa de libertad no es mayor de 3 años.",
                  [r"re:\b(3|tres) anos"]),
             fact("servicio-comunitario", "OMI_A", "Servicio comunitario (20 a 52 jornadas)", "Alternativamente, servicio comunitario de 20 a 52 jornadas.",
                  ["servicio comunitario"]),
         ],
         forbidden=[contradicted("pena-mayor", "OMI", "Pena Base: Hasta 3 años", "La pena base llega a 5 años o más.",
                                 "El corpus fija la pena base en hasta 3 años.",
                                 r"re:pena[^.]{0,40}(base|basica)[^.]{0,40}\b(4|5|6|7|8|10) anos")],
         cites=["art:149"], refs=[("OMI_A", "Anatomía del Artículo 149: El Tipo Base")]),
    case("omision-requiere-mandato-judicial", "omision_asistencia_familiar", "positivo", "dev",
         "¿Es delito no pagar la pensión de alimentos si no hay sentencia?",
         facts=[fact("mandato-previo", "OMI", "Solo es delito si existe un mandato judicial previo incumplido en la vía civil",
                     "Solo es delito si existe un mandato judicial previo incumplido en la vía civil.",
                     ["mandato", "resolucion", "sentencia"], ["previo", "civil", "judicial"])],
         forbidden=[contradicted("sin-resolucion", "OMI", "Solo es delito si existe un mandato judicial previo incumplido en la vía civil",
                                 "No pagar es delito aunque no exista resolución judicial.",
                                 "El corpus exige un mandato judicial previo.",
                                 r"re:(es|constituye|configura)[^.]{0,20}delito[^.]{0,40}(aunque|incluso|sin) (no )?(exist|haya|tener|resolucion|mandato|sentencia)")]),
    case("omision-simulacion-renuncia-maliciosa", "omision_asistencia_familiar", "positivo", "dev",
         "¿Qué pena corresponde si alguien finge deudas o renuncia al trabajo para no pagar alimentos?",
         facts=[fact("pena-hasta-4", "OMI", "eleva la pena hasta 4 años", "Fingir deudas o renunciar al trabajo eleva la pena hasta 4 años.",
                     [r"re:\b(4|cuatro) anos"], [r"re:fing|simul|renunci"])]),
    case("omision-consumacion-y-prescripcion", "omision_asistencia_familiar", "positivo", "holdout",
         "¿Cuándo se consuma el delito de omisión de asistencia familiar y desde cuándo corre la prescripción?",
         facts=[
             fact("consumacion", "OMI", "El delito se perfecciona al vencer el plazo del requerimiento de pago judicial",
                  "El delito se perfecciona al vencer el plazo del requerimiento de pago judicial.",
                  ["requerimiento"], ["vencer", "vencimiento", "vence", "plazo"]),
             fact("prescripcion-inicio", "OMI_A", "Se computa desde el día siguiente de vencido el requerimiento",
                  "La prescripción se computa desde el día siguiente de vencido el requerimiento.",
                  ["dia siguiente", "siguiente"], ["requerimiento"]),
         ]),
    case("omision-no-es-prision-por-deudas", "omision_asistencia_familiar", "positivo", "holdout",
         "¿Por qué no se considera prisión por deudas la omisión de asistencia familiar?",
         facts=[
             fact("excepcion-constitucional", "OMI", "La Constitución permite la prisión efectiva por incumplimiento de deberes alimentarios",
                  "La Constitución permite la prisión por incumplimiento de deberes alimentarios.",
                  ["constitucion"], ["alimentari", "alimentos"]),
             fact("regla-general", "OMI_A", "No hay prisión por deudas", "La regla general es que no hay prisión por deudas.",
                  ["prision por deudas"]),
         ],
         forbidden=[unsupported("cualquier-deuda", "Cualquier deuda civil puede llevar a la cárcel.",
                                "El corpus limita la excepción a los deberes alimentarios.",
                                r"re:(cualquier|toda) deuda[^.]{0,40}(carcel|prision)")],
         cites=["const:art:2"], refs=[("OMI_A", "Art. 2, inc. 24, lit. C, Constitución Política del Perú")]),
    case("omision-plazo-prescripcion-sin-cifra", "omision_asistencia_familiar", "limite", "holdout",
         "¿En cuántos años prescribe el delito de omisión de asistencia familiar?",
         facts=[fact("inicio-no-plazo", "OMI_A", "Se computa desde el día siguiente de vencido el requerimiento",
                     "La prescripción se computa desde el día siguiente de vencido el requerimiento; el corpus no indica el número de años.",
                     ["dia siguiente", "siguiente"], ["requerimiento"])],
         forbidden=[unsupported("anos-inventados", "El delito prescribe en un número concreto de años.",
                                "El corpus solo dice desde cuándo se computa, no cuántos años.",
                                r"re:prescrib\w*[^.]{0,40}\b\d+ ?anos", r"re:\b\d+ anos[^.]{0,30}prescrib")]),
    # ── Fuera del corpus ────────────────────────────────────────────────────────
    case("fuera-licencia-de-conducir", "fuera_de_corpus", "negativo", "dev",
         "¿Cuál es el procedimiento para obtener una licencia de conducir?",
         abstain=True, absent=["licencia de conducir", "brevete"]),
    case("fuera-cts-renuncia", "fuera_de_corpus", "negativo", "holdout",
         "¿Cómo calculo mi CTS si renuncio a mi trabajo?",
         abstain=True, absent=["compensación por tiempo de servicios", "compensacion de tiempo de servicios"]),
    case("fuera-adopcion-extranjeros", "fuera_de_corpus", "negativo", "dev",
         "¿Qué requisitos debe cumplir un extranjero para adoptar a un niño en el Perú?",
         abstain=True, absent=["adopción internacional", "adopcion internacional"]),
    case("fuera-impuesto-a-la-renta", "fuera_de_corpus", "negativo", "holdout",
         "¿Cuál es la tasa del impuesto a la renta de cuarta categoría?",
         abstain=True, absent=["impuesto a la renta"]),
    case("fuera-pension-argentina", "fuera_de_corpus", "negativo", "dev",
         "¿Cómo se tramita la cuota alimentaria ante un juzgado de Argentina?",
         abstain=True, absent=["argentina", "cuota alimentaria"]),
]


def _segment_for(corpus, doc_key, quote, label):
    doc_id = DOCS[doc_key]
    hits = [s for s in corpus.documents[doc_id].segments if contains(s.text, quote)]
    if not hits:
        raise ValueError(f"{label}: la cita no aparece en {doc_id}: {quote!r}")
    return hits[0]


def build_case(spec, corpus) -> GoldCase:
    label, segments = spec["id"], {}

    def ref(doc, quote, what):
        segment = _segment_for(corpus, doc, quote, f"{label}/{what}")
        segments[segment.id] = segment
        return segment

    facts = []
    for f in spec["facts"]:
        segment = ref(f["doc"], f["quote"], f["id"])
        facts.append({"id": f["id"], "text": f["text"], "anchors": f["anchors"],
                      "source": {"segment_id": segment.id, "quote": f["quote"]}})
    for doc, quote in spec["refs"]:
        ref(doc, quote, "ref")
    forbidden = []
    for c in spec["forbidden"]:
        item = {"id": c["id"], "text": c["text"], "kind": c["kind"], "reason": c["reason"],
                "patterns": c["patterns"], "example": c["example"]}
        if c["kind"] == "contradicted":
            segment = _segment_for(corpus, c["doc"], c["quote"], f"{label}/{c['id']}")
            item["contradicted_by"] = {"segment_id": segment.id, "quote": c["quote"]}
        forbidden.append(item)
    return GoldCase.model_validate({
        "id": label, "version": 1, "status": "candidate", "reviewers": [], "topic": spec["topic"],
        "query": spec["query"], "language": "spanish", "stratum": spec["stratum"], "split": spec["split"],
        "must_abstain": spec["abstain"],
        "reference_segments": [{"segment_id": s.id, "sha": s.sha} for s in sorted(segments.values(), key=lambda s: s.id)],
        "required_facts": facts, "forbidden_claims": forbidden, "acceptable_citations": spec["cites"],
        "absent_terms": spec["absent"], "notes": spec["notes"],
    })


def build_seed(corpus=None):
    corpus = corpus or Corpus.load()
    cases, problems = [], []
    for spec in SEED:
        try:
            cases.append(build_case(spec, corpus))
        except ValueError as error:
            problems.append(str(error).splitlines()[0])
    problems += [p for c in cases for p in verify_case(c, corpus)]
    if problems:
        raise ValueError("Semilla inválida:\n- " + "\n- ".join(problems))
    return cases


if __name__ == "__main__":
    built = build_seed()
    dump_cases(built, LEGAL_QA_PATH)
    print(f"{len(built)} casos candidatos escritos en {LEGAL_QA_PATH}")
