import { IsBoolean } from 'class-validator';

export class UpdateActiveDto {
  @IsBoolean()
  active: boolean;
}
