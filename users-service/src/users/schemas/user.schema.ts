import { Prop, Schema, SchemaFactory } from '@nestjs/mongoose';
import { HydratedDocument } from 'mongoose';

export enum Role {
  USER = 'USER',
  ADMIN = 'ADMIN',
}

export type UserDocument = HydratedDocument<User>;

/**
 * Documento `User` equivalente al del monolito (colección `users`): mismos campos
 * y semántica, contra la base propia de este servicio.
 */
@Schema({ collection: 'users' })
export class User {
  @Prop({ required: true, unique: true })
  username: string;

  @Prop({ required: true, unique: true })
  email: string;

  @Prop({ required: true })
  hashed_password: string;

  @Prop({ required: true, enum: Role, default: Role.USER })
  role: Role;

  @Prop({ default: true })
  active: boolean;

  @Prop({ default: 'standard' })
  tier: string;

  @Prop({ default: () => new Date() })
  created_at: Date;

  @Prop({ default: 0 })
  failed_login_attempts: number;

  @Prop({ type: Date, default: null })
  locked_until: Date | null;
}

export const UserSchema = SchemaFactory.createForClass(User);
