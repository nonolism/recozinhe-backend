BEGIN;
--
-- Create model Category
--
CREATE TABLE "apirecozinhe_category" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "timestamp_create" datetime NOT NULL, "timestamp_update" datetime NOT NULL, "name" varchar(50) NOT NULL UNIQUE, "slug" varchar(50) NOT NULL UNIQUE);
--
-- Create model Ingredient
--
CREATE TABLE "apirecozinhe_ingredient" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "timestamp_create" datetime NOT NULL, "timestamp_update" datetime NOT NULL, "name" varchar(100) NOT NULL UNIQUE);
--
-- Create model User
--
CREATE TABLE "apirecozinhe_user" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "password" varchar(128) NOT NULL, "last_login" datetime NULL, "is_superuser" bool NOT NULL, "username" varchar(150) NOT NULL UNIQUE, "first_name" varchar(150) NOT NULL, "last_name" varchar(150) NOT NULL, "email" varchar(254) NOT NULL, "is_staff" bool NOT NULL, "is_active" bool NOT NULL, "date_joined" datetime NOT NULL, "timestamp_create" datetime NOT NULL, "timestamp_update" datetime NOT NULL, "avatar" varchar(100) NULL, "monthly_goal_kg" decimal NOT NULL);
CREATE TABLE "apirecozinhe_user_groups" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "user_id" bigint NOT NULL REFERENCES "apirecozinhe_user" ("id") DEFERRABLE INITIALLY DEFERRED, "group_id" integer NOT NULL REFERENCES "auth_group" ("id") DEFERRABLE INITIALLY DEFERRED);
CREATE TABLE "apirecozinhe_user_user_permissions" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "user_id" bigint NOT NULL REFERENCES "apirecozinhe_user" ("id") DEFERRABLE INITIALLY DEFERRED, "permission_id" integer NOT NULL REFERENCES "auth_permission" ("id") DEFERRABLE INITIALLY DEFERRED);
--
-- Create model Photo
--
CREATE TABLE "apirecozinhe_photo" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "timestamp_create" datetime NOT NULL, "timestamp_update" datetime NOT NULL, "image" varchar(100) NOT NULL, "source" varchar(10) NOT NULL, "status" varchar(15) NOT NULL, "food_part" varchar(100) NOT NULL, "condition" varchar(150) NOT NULL, "confidence" smallint unsigned NULL CHECK ("confidence" >= 0), "estimated_weight_g" integer unsigned NULL CHECK ("estimated_weight_g" >= 0), "ai_message" varchar(300) NOT NULL, "identified_ingredient_id" bigint NULL REFERENCES "apirecozinhe_ingredient" ("id") DEFERRABLE INITIALLY DEFERRED, "user_id" bigint NOT NULL REFERENCES "apirecozinhe_user" ("id") DEFERRABLE INITIALLY DEFERRED);
--
-- Create model Recipe
--
CREATE TABLE "apirecozinhe_recipe" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "timestamp_create" datetime NOT NULL, "timestamp_update" datetime NOT NULL, "title" varchar(150) NOT NULL, "description" varchar(300) NOT NULL, "image" varchar(100) NULL, "prep_time_minutes" integer unsigned NOT NULL CHECK ("prep_time_minutes" >= 0), "difficulty" varchar(10) NOT NULL, "preparation" text NOT NULL, "estimated_saved_kg" decimal NOT NULL, "source" varchar(10) NOT NULL, "category_id" bigint NOT NULL REFERENCES "apirecozinhe_category" ("id") DEFERRABLE INITIALLY DEFERRED, "created_from_photo_id" bigint NULL REFERENCES "apirecozinhe_photo" ("id") DEFERRABLE INITIALLY DEFERRED);
CREATE TABLE "apirecozinhe_recipe_key_ingredients" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "recipe_id" bigint NOT NULL REFERENCES "apirecozinhe_recipe" ("id") DEFERRABLE INITIALLY DEFERRED, "ingredient_id" bigint NOT NULL REFERENCES "apirecozinhe_ingredient" ("id") DEFERRABLE INITIALLY DEFERRED);
--
-- Add field suggested_recipes to photo
--
CREATE TABLE "apirecozinhe_photo_suggested_recipes" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "photo_id" bigint NOT NULL REFERENCES "apirecozinhe_photo" ("id") DEFERRABLE INITIALLY DEFERRED, "recipe_id" bigint NOT NULL REFERENCES "apirecozinhe_recipe" ("id") DEFERRABLE INITIALLY DEFERRED);
--
-- Create model RecipeIngredient
--
CREATE TABLE "apirecozinhe_recipeingredient" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "timestamp_create" datetime NOT NULL, "timestamp_update" datetime NOT NULL, "description" varchar(200) NOT NULL, "order" integer unsigned NOT NULL CHECK ("order" >= 0), "recipe_id" bigint NOT NULL REFERENCES "apirecozinhe_recipe" ("id") DEFERRABLE INITIALLY DEFERRED);
--
-- Create model ReuseTip
--
CREATE TABLE "apirecozinhe_reusetip" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "timestamp_create" datetime NOT NULL, "timestamp_update" datetime NOT NULL, "title" varchar(120) NOT NULL, "description" text NOT NULL, "photo_id" bigint NOT NULL REFERENCES "apirecozinhe_photo" ("id") DEFERRABLE INITIALLY DEFERRED);
--
-- Create model Reuse
--
CREATE TABLE "apirecozinhe_reuse" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "timestamp_create" datetime NOT NULL, "timestamp_update" datetime NOT NULL, "saved_kg" decimal NOT NULL, "reused_at" date NOT NULL, "photo_id" bigint NULL REFERENCES "apirecozinhe_photo" ("id") DEFERRABLE INITIALLY DEFERRED, "recipe_id" bigint NULL REFERENCES "apirecozinhe_recipe" ("id") DEFERRABLE INITIALLY DEFERRED, "user_id" bigint NOT NULL REFERENCES "apirecozinhe_user" ("id") DEFERRABLE INITIALLY DEFERRED, "tip_id" bigint NULL REFERENCES "apirecozinhe_reusetip" ("id") DEFERRABLE INITIALLY DEFERRED);
CREATE UNIQUE INDEX "apirecozinhe_user_groups_user_id_group_id_4802ed59_uniq" ON "apirecozinhe_user_groups" ("user_id", "group_id");
CREATE INDEX "apirecozinhe_user_groups_user_id_1612ed7b" ON "apirecozinhe_user_groups" ("user_id");
CREATE INDEX "apirecozinhe_user_groups_group_id_20ad2a6a" ON "apirecozinhe_user_groups" ("group_id");
CREATE UNIQUE INDEX "apirecozinhe_user_user_permissions_user_id_permission_id_fd022df0_uniq" ON "apirecozinhe_user_user_permissions" ("user_id", "permission_id");
CREATE INDEX "apirecozinhe_user_user_permissions_user_id_1eb114fb" ON "apirecozinhe_user_user_permissions" ("user_id");
CREATE INDEX "apirecozinhe_user_user_permissions_permission_id_0ff0661d" ON "apirecozinhe_user_user_permissions" ("permission_id");
CREATE INDEX "apirecozinhe_photo_identified_ingredient_id_35c0ce2d" ON "apirecozinhe_photo" ("identified_ingredient_id");
CREATE INDEX "apirecozinhe_photo_user_id_fb9e0aa3" ON "apirecozinhe_photo" ("user_id");
CREATE INDEX "apirecozinhe_recipe_category_id_976a3ce2" ON "apirecozinhe_recipe" ("category_id");
CREATE INDEX "apirecozinhe_recipe_created_from_photo_id_30fbda35" ON "apirecozinhe_recipe" ("created_from_photo_id");
CREATE UNIQUE INDEX "apirecozinhe_recipe_key_ingredients_recipe_id_ingredient_id_eae0352d_uniq" ON "apirecozinhe_recipe_key_ingredients" ("recipe_id", "ingredient_id");
CREATE INDEX "apirecozinhe_recipe_key_ingredients_recipe_id_3a893bbb" ON "apirecozinhe_recipe_key_ingredients" ("recipe_id");
CREATE INDEX "apirecozinhe_recipe_key_ingredients_ingredient_id_ca4329a3" ON "apirecozinhe_recipe_key_ingredients" ("ingredient_id");
CREATE UNIQUE INDEX "apirecozinhe_photo_suggested_recipes_photo_id_recipe_id_bf8d4f0a_uniq" ON "apirecozinhe_photo_suggested_recipes" ("photo_id", "recipe_id");
CREATE INDEX "apirecozinhe_photo_suggested_recipes_photo_id_1de63c5d" ON "apirecozinhe_photo_suggested_recipes" ("photo_id");
CREATE INDEX "apirecozinhe_photo_suggested_recipes_recipe_id_455bf026" ON "apirecozinhe_photo_suggested_recipes" ("recipe_id");
CREATE INDEX "apirecozinhe_recipeingredient_recipe_id_5c65823f" ON "apirecozinhe_recipeingredient" ("recipe_id");
CREATE INDEX "apirecozinhe_reusetip_photo_id_c0d63ecd" ON "apirecozinhe_reusetip" ("photo_id");
CREATE INDEX "apirecozinhe_reuse_photo_id_afac6682" ON "apirecozinhe_reuse" ("photo_id");
CREATE INDEX "apirecozinhe_reuse_recipe_id_f3ef4f81" ON "apirecozinhe_reuse" ("recipe_id");
CREATE INDEX "apirecozinhe_reuse_user_id_a95fe81e" ON "apirecozinhe_reuse" ("user_id");
CREATE INDEX "apirecozinhe_reuse_tip_id_ea94281d" ON "apirecozinhe_reuse" ("tip_id");
COMMIT;
