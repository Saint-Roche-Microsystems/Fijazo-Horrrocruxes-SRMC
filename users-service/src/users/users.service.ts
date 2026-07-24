import {
  ConflictException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model, isValidObjectId } from 'mongoose';
import * as bcrypt from 'bcryptjs';
import { Role, User, UserDocument } from './schemas/user.schema';
import { AuthClient } from './auth.client';
import { CreateUserDto } from './dto/create-user.dto';
import {
  PaginatedUsersDto,
  UserResponseDto,
} from './dto/user-response.dto';

/** Resultado del contrato `users.validate`. */
export interface ValidateResult {
  active: boolean;
  tier: string | null;
  locked: boolean;
  locked_until: string | null;
}

@Injectable()
export class UsersService {
  constructor(
    @InjectModel(User.name) private readonly userModel: Model<UserDocument>,
    private readonly authClient: AuthClient,
  ) {}

  /** Crea un usuario. El password se hashea con bcrypt, como en el monolito. */
  async create(dto: CreateUserDto): Promise<UserResponseDto> {
    const hashed_password = await bcrypt.hash(dto.password, 12);
    try {
      const doc = await this.userModel.create({
        username: dto.username,
        email: dto.email,
        hashed_password,
        role: dto.role ?? Role.USER,
      });
      return UserResponseDto.fromDocument(doc);
    } catch (err: unknown) {
      if (this.isDuplicateKey(err)) {
        throw new ConflictException(
          'El correo o el nombre de usuario ya existe.',
        );
      }
      throw err;
    }
  }

  /** Lista usuarios paginados: `(items, total)` ordenados por `created_at` asc. */
  async list(page = 1, pageSize = 20): Promise<PaginatedUsersDto> {
    const skip = (page - 1) * pageSize;
    const [docs, total] = await Promise.all([
      this.userModel
        .find()
        .sort({ created_at: 1 })
        .skip(skip)
        .limit(pageSize)
        .exec(),
      this.userModel.countDocuments().exec(),
    ]);
    return {
      items: docs.map((d) => UserResponseDto.fromDocument(d)),
      total,
      page,
      page_size: pageSize,
    };
  }

  /** Devuelve un usuario o lanza 404, equivalente a `NotFoundError` del monolito. */
  async getById(userId: string): Promise<UserResponseDto> {
    return UserResponseDto.fromDocument(await this.findOrFail(userId));
  }

  /** Activa/desactiva un usuario. */
  async setActive(userId: string, active: boolean): Promise<UserResponseDto> {
    const doc = await this.findOrFail(userId);
    doc.active = active;
    await doc.save();
    return UserResponseDto.fromDocument(doc);
  }

  /** Cambia el rol de un usuario. */
  async setRole(userId: string, role: Role): Promise<UserResponseDto> {
    const doc = await this.findOrFail(userId);
    doc.role = role;
    await doc.save();
    return UserResponseDto.fromDocument(doc);
  }

  /**
   * Contrato de validación consumido por otros servicios (vía TCP). Devuelve el
   * estado del usuario sin exponer HTTP público. Un usuario inexistente se trata
   * como no activo, para que el llamador (Bets) no dependa de errores.
   */
  async validate(userId: string): Promise<ValidateResult> {
    if (!isValidObjectId(userId)) {
      return { active: false, tier: null, locked: false, locked_until: null };
    }
    const doc = await this.userModel.findById(userId).exec();
    if (!doc) {
      return { active: false, tier: null, locked: false, locked_until: null };
    }
    // Hop B->C: enriquecer con el estado de bloqueo de auth-service, sin que el
    // llamador (Bets) conozca la existencia de auth-service.
    const lock = await this.authClient.getLockStatus(userId);
    return {
      active: doc.active,
      tier: doc.tier,
      locked: lock.locked,
      locked_until: lock.locked_until,
    };
  }

  private async findOrFail(userId: string): Promise<UserDocument> {
    if (!isValidObjectId(userId)) {
      throw new NotFoundException('Usuario no encontrado.');
    }
    const doc = await this.userModel.findById(userId).exec();
    if (!doc) {
      throw new NotFoundException('Usuario no encontrado.');
    }
    return doc;
  }

  private isDuplicateKey(err: unknown): boolean {
    return (
      typeof err === 'object' &&
      err !== null &&
      (err as { code?: number }).code === 11000
    );
  }
}
