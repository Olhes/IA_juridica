import type { ConsultLegalInput, LegalGateway } from '../../../domain/legal/ports';

export const createConsultLegalUseCase = (gateway: LegalGateway) => {
  return async (input: ConsultLegalInput) => gateway.consult(input);
};
