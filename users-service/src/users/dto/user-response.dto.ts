import { Role, UserDocument } from '../schemas/user.schema';

/** Representación pública de un usuario (sin contraseña), equivalente a la del monolito. */
export class UserResponseDto {
  id: string;
  username: string;
  email: string;
  role: Role;
  active: boolean;
  created_at: Date;

  static fromDocument(doc: UserDocument): UserResponseDto {
    const dto = new UserResponseDto();
    dto.id = doc._id.toString();
    dto.username = doc.username;
    dto.email = doc.email;
    dto.role = doc.role;
    dto.active = doc.active;
    dto.created_at = doc.created_at;
    return dto;
  }
}

/** Resultado paginado de usuarios, equivalente al `PaginatedUsers` del monolito. */
export class PaginatedUsersDto {
  items: UserResponseDto[];
  total: number;
  page: number;
  page_size: number;
}
