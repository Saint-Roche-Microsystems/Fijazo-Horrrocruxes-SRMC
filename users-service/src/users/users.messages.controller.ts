import { Controller } from '@nestjs/common';
import { MessagePattern, Payload } from '@nestjs/microservices';
import { UsersService, ValidateResult } from './users.service';

/**
 * Transporte TCP: contrato consumible por otros servicios sin pasar por el HTTP
 * público (p. ej. bets-service valida usuarios sin acoplarse al gateway).
 */
@Controller()
export class UsersMessagesController {
  constructor(private readonly usersService: UsersService) {}

  @MessagePattern('users.validate')
  validate(
    @Payload() data: { user_id: string },
  ): Promise<ValidateResult> {
    return this.usersService.validate(data?.user_id);
  }
}
