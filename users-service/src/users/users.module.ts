import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { UsersController } from './users.controller';
import { UsersMessagesController } from './users.messages.controller';
import { UsersService } from './users.service';
import { AuthClient } from './auth.client';
import { User, UserSchema } from './schemas/user.schema';

@Module({
  imports: [
    MongooseModule.forFeature([{ name: User.name, schema: UserSchema }]),
  ],
  controllers: [UsersController, UsersMessagesController],
  providers: [UsersService, AuthClient],
  exports: [UsersService],
})
export class UsersModule {}
