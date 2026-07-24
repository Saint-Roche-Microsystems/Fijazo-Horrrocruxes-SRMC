import { IsEnum } from 'class-validator';
import { Role } from '../schemas/user.schema';

export class UpdateRoleDto {
  @IsEnum(Role)
  role: Role;
}
